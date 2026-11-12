"""Cartes prépayées et comptes tenus à la main (titres-restaurant Edenred, Swile, cantine, carte cadeau, Navigo…).

Un compte de type ``prepaye`` est créé par l'utilisateur ; il compte dans le patrimoine (liquidités). Ses opérations :

- un crédit (versement de l'employeur) est un REVENU, catégorie « Titres-restaurant » ;
- un paiement par carte est une DÉPENSE normale : catégorie par vendeur (règles de ``categories.py``), vendeur
  renommable comme les autres (``merchant_names``) ;
- un recalage de solde est une ligne ``interne`` (« Ajustement de solde ») : ni revenu ni dépense, le solde
  calculé retombe sur ce que l'appli du fournisseur affiche.

Les identifiants d'opérations sont des empreintes (date, libellé, montant, compte, rang) : réimporter le même
texte ne crée rien de nouveau. Pas de réseau ici ; le connecteur automatique est dans ``sources/edenred.py``.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from . import db
from .categories import TITRES_RESTAURANT
from .sources.tr_parse import Row

KIND = "prepaye"
CREDIT_WORDS = ("credit", "versement", "alimentation", "rechargement", "recharge", "dotation", "abondement",
                "employeur", "remboursement carte")
MONTHS = {"janv": 1, "janvier": 1, "fevr": 2, "fev": 2, "fevrier": 2, "mars": 3, "avr": 4, "avril": 4, "mai": 5,
          "juin": 6, "juil": 7, "juillet": 7, "aout": 8, "sept": 9, "septembre": 9, "oct": 10, "octobre": 10,
          "nov": 11, "novembre": 11, "dec": 12, "decembre": 12}


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", _ascii(name).lower()).strip("_") or "carte"


def _cents(euros: str | float | int) -> int:
    """Euros (nombre ou texte « 1 234,56 ») en centimes entiers."""
    if isinstance(euros, str):
        euros = _amount(euros)
    return int((Decimal(str(euros)) * 100).quantize(Decimal(1)))


def _amount(text: str) -> Decimal:
    t = re.sub(r"[\s  €]|EUR", "", text.replace("−", "-").replace("–", "-"))
    sign = -1 if t.startswith("-") else 1
    t = t.lstrip("+-")
    if "," in t and "." in t:  # le dernier séparateur est la virgule décimale
        dec = "," if t.rfind(",") > t.rfind(".") else "."
        t = t.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in t:
        t = t.replace(",", ".")
    elif t.count(".") > 1 or re.fullmatch(r"\d{1,3}\.\d{3}", t):  # 1.234 : milliers
        t = t.replace(".", "")
    try:
        return sign * Decimal(t)
    except InvalidOperation:
        raise ValueError(f"montant illisible : {text!r}") from None


# ---------- comptes ----------

def card_ids(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT id, name FROM accounts WHERE kind = ? AND active = 1 ORDER BY name", (KIND,)).fetchall()


def resolve(con: sqlite3.Connection, carte: str) -> str:
    """Identifiant d'une carte à partir de son id, de son nom ou d'un bout de nom. ValueError sinon."""
    q = (carte or "").strip().lower()
    cards = card_ids(con)
    if not q:
        raise ValueError("carte manquante")
    exact = [c["id"] for c in cards if q in (c["id"].lower(), c["name"].lower())]
    found = exact or [c["id"] for c in cards if q in c["name"].lower() or q in c["id"].lower()]
    if not found:
        raise ValueError(f"carte inconnue : {carte} (cartes : {', '.join(c['name'] for c in cards) or 'aucune'})")
    if len(found) > 1:
        raise ValueError(f"carte ambiguë : {carte} ({', '.join(found)})")
    return found[0]


def create(con: sqlite3.Connection, nom: str, solde_initial: float | str = 0, today: str | None = None) -> dict:
    nom = " ".join((nom or "").split())[:60]
    if not nom:
        raise ValueError("nom manquant")
    if any(c["name"].lower() == nom.lower() for c in card_ids(con)):
        raise ValueError(f"la carte « {nom} » existe déjà")
    base = "prepaye_" + _slug(nom)
    acc, n = base, 1
    while con.execute("SELECT 1 FROM accounts WHERE id = ?", (acc,)).fetchone():
        n += 1
        acc = f"{base}_{n}"
    con.execute("INSERT INTO accounts (id, institution, name, kind, source) VALUES (?, ?, ?, ?, 'manuel')",
                (acc, nom, nom, KIND))
    cents = _cents(solde_initial)
    if cents:
        adjust(con, acc, cents, today or date.today().isoformat(), "Solde initial")
    con.commit()
    return {"id": acc, "nom": nom}


# ---------- opérations ----------

def _tx_id(account: str, day: str, label: str, cents: int, rank: int) -> str:
    key = f"{day}|{label}|{cents}|{account}|{rank}"
    return "carte:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]


def _row(con: sqlite3.Connection, account: str, day: str, label: str, cents: int, rank: int, kind: str) -> Row:
    """Ligne prête à importer : crédit = revenu, paiement = dépense, ajustement = interne."""
    name = con.execute("SELECT name FROM accounts WHERE id = ?", (account,)).fetchone()["name"]
    flow, event, who = {
        "credit": ("revenu", "CARTE_CREDIT", f"{TITRES_RESTAURANT} {name}"),
        "paiement": ("depense", "CARTE_PAIEMENT", label),
        "ajustement": ("interne", "CARTE_AJUSTEMENT", f"{name} (ajustement)"),
    }[kind]
    return Row(id=_tx_id(account, day, label, cents, rank), account_id=account, date=day, amount_cents=cents,
               flow=flow, event_type=event, label=label, counterparty=who,
               raw={"source": "carte", "timestamp": f"{day}T12:00:00.000+0000"})


def _raw(r: Row) -> str:
    return json.dumps(r.raw, ensure_ascii=False, separators=(",", ":"))


def _check_day(day: str) -> str:
    try:
        return date.fromisoformat((day or "").strip()).isoformat()
    except ValueError:
        raise ValueError(f"date invalide : {day!r} (format AAAA-MM-JJ)") from None


def add_operation(con: sqlite3.Connection, account: str, day: str, amount: float | str, label: str,
                  kind: str = "paiement", allow_duplicate: bool = False) -> dict:
    """Une opération saisie à la main. Un paiement est toujours négatif et un crédit positif, quel que soit le signe
    donné. Une opération identique déjà présente (même jour, libellé, montant) n'est pas ajoutée deux fois, sauf
    ``allow_duplicate`` (deux cafés au même prix le même jour)."""
    from . import sync

    if kind not in ("paiement", "credit"):
        raise ValueError("type : « paiement » ou « credit »")
    day = _check_day(day)
    label = " ".join((label or "").split())[:120]
    if not label:
        raise ValueError("libellé manquant")
    cents = abs(_cents(amount))
    if not cents:
        raise ValueError("montant nul")
    cents = cents if kind == "credit" else -cents
    rank = 0
    while con.execute("SELECT 1 FROM transactions WHERE id = ?", (_tx_id(account, day, label, cents, rank),)).fetchone():
        if not allow_duplicate:
            return {"ajoutee": False, "deja_presente": True, "id": _tx_id(account, day, label, cents, rank)}
        rank += 1
    row = _row(con, account, day, label, cents, rank, kind)
    sync.import_rows(con, [row], _raw)
    con.commit()
    return {"ajoutee": True, "deja_presente": False, "id": row.id}


def balance_at(con: sqlite3.Connection, account: str, day: str | None = None) -> int:
    """Solde calculé en centimes (somme des lignes jusqu'à ``day`` inclus, toutes si vide)."""
    q, args = "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE account_id = ?", [account]
    if day:
        q += " AND date <= ?"
        args.append(day)
    return int(con.execute(q, args).fetchone()[0])


def adjust(con: sqlite3.Connection, account: str, target_cents: int, day: str, label: str = "Ajustement de solde"
           ) -> int:
    """Ajoute la ligne ``interne`` qui amène le solde à ``target_cents`` au ``day``. Retourne l'écart en centimes
    (0 : rien à faire, aucune ligne)."""
    from . import sync

    delta = target_cents - balance_at(con, account, day)
    if not delta:
        return 0
    rank = con.execute("SELECT COUNT(*) FROM transactions WHERE account_id = ? AND date = ? AND event_type ="
                       " 'CARTE_AJUSTEMENT'", (account, day)).fetchone()[0]
    sync.import_rows(con, [_row(con, account, day, label, delta, rank, "ajustement")], _raw)
    con.commit()
    return delta


def set_balance(con: sqlite3.Connection, account: str, amount: float | str, day: str = "") -> dict:
    day = _check_day(day) if day else date.today().isoformat()
    target = _cents(amount)
    before = balance_at(con, account, day)
    delta = adjust(con, account, target, day)
    return {"date": day, "solde_avant": before / 100, "solde": target / 100, "ecart": delta / 100,
            "ajustement": bool(delta)}


def summary(con: sqlite3.Connection, today: date | None = None) -> list[dict]:
    """Une entrée par carte : solde calculé, dernier mouvement, crédit mensuel moyen, ancienneté de la saisie."""
    today = today or date.today()
    out = []
    for c in card_ids(con):
        acc = c["id"]
        last = con.execute("SELECT MAX(date) FROM transactions WHERE account_id = ? AND event_type IN"
                           " ('CARTE_PAIEMENT', 'CARTE_CREDIT')", (acc,)).fetchone()[0]
        touched = con.execute("SELECT MAX(date), MAX(imported_at) FROM transactions WHERE account_id = ?",
                              (acc,)).fetchone()
        since = (today - timedelta(days=365)).isoformat()
        months = [r[0] for r in con.execute(
            "SELECT SUM(amount_cents) FROM transactions WHERE account_id = ? AND event_type = 'CARTE_CREDIT'"
            " AND date >= ? GROUP BY substr(date, 1, 7)", (acc, since))]
        ref = None
        if touched[1]:
            ref = datetime.fromisoformat(touched[1]).date()
        elif touched[0]:
            ref = date.fromisoformat(touched[0])
        out.append({
            "id": acc, "nom": c["name"], "solde": balance_at(con, acc) / 100, "dernier_mouvement": last,
            "credit_mensuel_moyen": round(sum(months) / len(months) / 100, 2) if months else None,
            "jours_depuis_maj": (today - ref).days if ref else None,
            "operations": con.execute("SELECT COUNT(*) FROM transactions WHERE account_id = ?", (acc,)).fetchone()[0],
        })
    return out


# ---------- import d'un copier-coller ----------

_DATE_ISO = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
_DATE_FR = re.compile(r"(?<![\d.,])(\d{1,2})[/.](\d{1,2})[/.](\d{2,4})(?![\d,])")
_DATE_TXT = re.compile(r"(?<!\d)(\d{1,2})\s+([A-Za-zéûèôÉ]+)\.?\s+(\d{4})(?!\d)")
_DATE_SHORT = re.compile(r"(?<![\d.,/])(\d{1,2})/(\d{1,2})(?![\d/,])")
_AMOUNT = re.compile(r"(?<![\w.,])([+\-−–])?\s*(\d[\d   ]*(?:[.,]\d{1,2})?)\s*(€|EUR\b)?")
_SEPARATORS = re.compile(r"\s*[;\t|]\s*")


def _find_date(line: str, today: date) -> tuple[str, tuple[int, int]] | None:
    """(date ISO, position dans la ligne) de la première date reconnue, ou None. ValueError si elle n'existe pas."""
    for rx, kind in ((_DATE_ISO, "iso"), (_DATE_FR, "fr"), (_DATE_TXT, "txt"), (_DATE_SHORT, "short")):
        m = rx.search(line)
        if not m:
            continue
        a, b, c = (m.groups() + (None,))[:3]
        if kind == "iso":
            y, mo, d = int(a), int(b), int(c)
        elif kind == "fr":
            y, mo, d = int(c), int(b), int(a)
            y += 2000 if y < 100 else 0
        elif kind == "txt":
            mo = MONTHS.get(_ascii(b).lower())
            if not mo:
                continue
            y, d = int(c), int(a)
        else:
            d, mo, y = int(a), int(b), today.year
        try:
            found = date(y, mo, d)
        except ValueError:
            raise ValueError("date invalide") from None
        if kind == "short" and found > today:
            found = date(y - 1, mo, d)
        return found.isoformat(), m.span()
    return None


def parse_text(texte: str, today: date | None = None) -> tuple[list[dict], list[dict]]:
    """Lignes reconnues et lignes ignorées d'un copier-coller de l'appli du fournisseur ou d'un CSV
    ``date;libellé;montant``. Chaque ligne reconnue : {ligne, date, libelle, montant (centimes, signé), type}. Les
    ignorées : {ligne, texte, raison}. Séparateurs ; , tabulation ; dates JJ/MM/AAAA, AAAA-MM-JJ, « 12 nov. 2026 » ;
    montants avec virgule ou point, espaces de milliers, signe, € facultatif. Sans signe : crédit si le libellé
    l'indique (crédit, versement, rechargement…), sinon paiement."""
    today = today or date.today()
    good: list[dict] = []
    bad: list[dict] = []
    for n, raw in enumerate((texte or "").splitlines(), 1):
        line = raw.strip()
        if not line:
            continue

        def skip(reason: str, n=n, raw=raw) -> None:
            bad.append({"ligne": n, "texte": raw.strip()[:120], "raison": reason})

        try:
            found = _find_date(line, today)
        except ValueError as e:
            skip(str(e))
            continue
        if not found:
            skip("pas de date (en-tête ou ligne parasite)" if re.search(r"date|libell|montant", line, re.I)
                 else "pas de date")
            continue
        day, (i, j) = found
        rest = line[:i] + " " + line[j:]
        candidates = [m for m in _AMOUNT.finditer(rest) if m.group(1) or m.group(3) or re.search(r"[.,]\d", m.group(2))]
        if not candidates:
            skip("pas de montant")
            continue
        m = next((c for c in candidates if c.group(1)), candidates[0])
        try:
            value = _amount((m.group(1) or "") + m.group(2))
        except ValueError as e:
            skip(str(e))
            continue
        if value == 0:
            skip("montant nul")
            continue
        label = rest[:m.start()] + " " + rest[m.end():]
        label = " ".join(_SEPARATORS.sub(" ", label).replace("€", " ").split()).strip(" ,;-:")
        if not label:
            skip("pas de libellé")
            continue
        if m.group(1):
            credit = value > 0
        else:
            credit = any(w in _ascii(label).lower() for w in CREDIT_WORDS)
        good.append({"ligne": n, "date": day, "libelle": label[:120], "type": "credit" if credit else "paiement",
                     "montant": abs(_cents(value)) * (1 if credit else -1)})
    return good, bad


def import_text(con: sqlite3.Connection, account: str, texte: str, preview: bool = False,
                today: date | None = None) -> dict:
    """Importe (ou prévisualise) un copier-coller. Idempotent : une ligne déjà présente n'est pas recréée. Deux
    lignes identiques dans le texte reçoivent un rang différent, donc restent deux opérations."""
    from . import sync

    good, bad = parse_text(texte, today)
    seen: dict[tuple, int] = {}
    rows: list[Row] = []
    for g in good:
        key = (g["date"], g["libelle"], g["montant"])
        rank = seen[key] = seen.get(key, -1) + 1
        rows.append(_row(con, account, g["date"], g["libelle"], g["montant"], rank, g["type"]))
    known = {r[0] for r in con.execute(
        f"SELECT id FROM transactions WHERE id IN ({','.join('?' * len(rows))})", [r.id for r in rows])} if rows else set()
    new = [r for r in rows if r.id not in known]
    if not preview and new:
        sync.import_rows(con, new, _raw)
        con.commit()
    out_lines = [{**g, "montant": g["montant"] / 100, "nouvelle": r.id not in known} for g, r in zip(good, rows)]
    return {
        "ecrit": not preview, "lignes": out_lines, "ignorees": bad, "nouvelles": len(new),
        "deja_presentes": len(rows) - len(new),
        "paiements": sum(-g["montant"] for g in good if g["type"] == "paiement") / 100,
        "credits": sum(g["montant"] for g in good if g["type"] == "credit") / 100,
    }
