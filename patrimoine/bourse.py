"""Données de l'écran Bourse : une seule réponse pour « tous les comptes » et pour chaque compte de placement.

Rien n'est recalculé ici qui existe déjà : valeur et montant investi viennent de `analytics.invested_series`
(table `valuations`), les lignes de `queries.positions`, le TWR de l'indice `analytics.stats`.
Montants en euros, rendements en fractions (0,05 = 5 %). Un champ que la base ne permet pas de calculer vaut `None`
(ou est absent pour une dimension de répartition) : jamais d'estimation inventée.
"""
from __future__ import annotations

import math
import sqlite3
import time
from collections import defaultdict
from typing import Any

import numpy as np
import pandas as pd

from . import analytics, db, portfolio, prices as _prices, queries

PERIODES = ["1J", "1S", "1M", "3M", "YTD", "1A", "MAX"]
MAX_POINTS = 90
MAX_POINTS_JOUR = 96
TOLERANCE_JOUR = 0.02  # écart accepté entre la série du jour et la valeur de la base avant d'y renoncer
TYPES = {"action": "Actions", "etf": "ETF", "crypto": "Crypto", "obligation": "Obligations", "derive": "Dérivés"}


# ---------- comptes ----------

def comptes_de_placement(con: sqlite3.Connection, book: portfolio.Book | None = None) -> list[str]:
    """Identifiants des comptes qui portent des positions (table `positions` et lignes rejouées depuis les
    opérations). Seul point d'entrée de cette liste : à remplacer le jour où les comptes seront configurables."""
    ids = {r[0] for r in con.execute("SELECT account_id FROM positions WHERE quantity > 0")}
    if book is not None:
        ids |= {acc for (acc, _), line in book.lines.items() if line.quantity > 1e-6}
    return sorted(ids)


def libelle_compte(con: sqlite3.Connection, account_id: str) -> str:
    """Libellé d'affichage : table `queries.ACCOUNT_LABELS` (liste fixe, héritée) puis nom du compte en base."""
    label = queries.account_labels(con).get(account_id)
    if label:
        return label
    row = con.execute("SELECT name FROM accounts WHERE id = ?", (account_id,)).fetchone()
    return row[0] if row and row[0] else account_id


# ---------- indice de référence ----------

_INDICE: dict[tuple, tuple[float, pd.Series | None]] = {}
_TTL = 3600.0
_TTL_ECHEC = 600.0


def cours_indice(symbole: str, depuis: pd.Timestamp) -> pd.Series | None:
    """Clôtures quotidiennes de l'indice en euros, ou None (pas de réseau, symbole inconnu). Gardées en mémoire
    une heure (dix minutes après un échec) pour ne pas relancer le réseau à chaque ouverture de l'écran."""
    from . import prices

    key = (symbole, depuis.date())
    hit = _INDICE.get(key)
    if hit and time.monotonic() < hit[0]:
        return hit[1]
    s: pd.Series | None = None
    try:
        raw, currency = prices.history(symbole, depuis.date())
        s = prices.to_eur(raw, currency, depuis.date()) if not raw.empty else None
        if s is not None and s.empty:
            s = None
    except Exception:  # noqa: BLE001 - pas de réseau, Yahoo indisponible
        s = None
    _INDICE[key] = (time.monotonic() + (_TTL if s is not None else _TTL_ECHEC), s)
    return s


# ---------- outils de séries ----------

def _f(x: Any, nd: int = 4) -> float | None:
    if x is None:
        return None
    x = float(x)
    return None if math.isnan(x) or math.isinf(x) else round(x, nd)


def _echantillon(n: int, k: int = MAX_POINTS) -> list[int]:
    if n <= k:
        return list(range(n))
    step = (n - 1) / (k - 1)
    return sorted({round(i * step) for i in range(k)})


def _points(s: pd.Series, pos: list[int], nd: int = 2) -> list[list]:
    return [[s.index[i].date().isoformat(), _f(s.iloc[i], nd)] for i in pos]


def _debut(label: str, end: pd.Timestamp, first: pd.Timestamp) -> pd.Timestamp:
    return {"1S": end - pd.Timedelta(days=7), "1M": end - pd.DateOffset(months=1),
            "3M": end - pd.DateOffset(months=3), "YTD": pd.Timestamp(end.year - 1, 12, 31),
            "1A": end - pd.DateOffset(years=1), "MAX": first}[label]


def _asof(s: pd.Series, d: pd.Timestamp) -> float | None:
    """Dernière valeur à la date d ou avant ; None si la série commence après d."""
    past = s[s.index <= d]
    return float(past.iloc[-1]) if len(past) else None


def _vol_1an(idx: pd.Series) -> float | None:
    r = idx[idx.index >= idx.index[-1] - pd.Timedelta(days=365)].pct_change().dropna()
    r = r[r != 0]
    return float(r.std() * math.sqrt(252)) if len(r) > 20 else None



# ---------- séance du jour (période 1J) ----------

class Seance:
    """Cours à pas fin de la séance du jour (ou de la dernière séance), par titre, sur une grille commune."""

    def __init__(self, jour: Any, grille: list[pd.Timestamp], prix: dict[str, np.ndarray], veille: dict[str, float],
                 brut: dict[str, pd.Series]):
        # brut : les cours propres à chaque titre (heure de Paris), pour la fiche d'un titre ; prix : sur la grille commune
        self.jour, self.grille, self.prix, self.veille, self.brut = jour, grille, prix, veille, brut


def rafraichir_seance(con: sqlite3.Connection, isins: list[str]) -> None:
    """Va chercher les cours du jour manquants ou vieux de plus de 15 minutes pendant la séance. Sans effet sur le
    jeu fictif ; ne lève jamais (hors ligne : on garde ce qui est stocké)."""
    try:
        if db.get_meta(con, "demo") or not isins:
            return
        _prices.update_intraday(con, isins)
    except Exception:  # noqa: BLE001
        pass


def charger_seance(con: sqlite3.Connection, px: portfolio.Prices) -> Seance | None:
    """La séance la plus récente stockée dans `prices_intraday`, ou None (rien de stocké, ou plus ancienne que le
    dernier cours quotidien : on ne mélange pas un cours du jour avec une séance périmée)."""
    from zoneinfo import ZoneInfo

    paris = ZoneInfo(_prices.PARIS)
    try:
        rows = con.execute("SELECT isin, ts, close FROM prices_intraday ORDER BY isin, ts").fetchall()
    except sqlite3.OperationalError:  # base ouverte en lecture seule sans la table
        return None
    brut: dict[str, dict[pd.Timestamp, float]] = defaultdict(dict)
    for isin, ts, close in rows:
        brut[isin][pd.Timestamp(ts).tz_convert(paris)] = close
    series = {i: pd.Series(d).sort_index() for i, d in brut.items() if d}
    if not series:
        return None
    jour = max(s.index[-1].date() for s in series.values())
    dernier = [px.series[i].index[-1].date() for i in series if i in px.series and len(px.series[i])]
    if dernier and jour < max(dernier):
        return None
    du_jour = {i: s[[d.date() == jour for d in s.index]] for i, s in series.items()}
    du_jour = {i: s for i, s in du_jour.items() if len(s)}
    union = sorted(set().union(*(set(s.index) for s in du_jour.values())))
    pos = _echantillon(len(union), MAX_POINTS_JOUR)
    grille = [union[i] for i in pos]
    prix: dict[str, np.ndarray] = {}
    veille: dict[str, float] = {}
    for isin, s in du_jour.items():
        d = px.series.get(isin)
        avant = d[d.index < pd.Timestamp(jour)] if d is not None else None
        v0 = float(avant.iloc[-1]) if avant is not None and len(avant) else float(s.iloc[0])
        a = s.reindex(pd.DatetimeIndex(union).union(s.index)).ffill().reindex(union).fillna(v0)
        prix[isin] = a.to_numpy()[pos]
        veille[isin] = v0
    return Seance(jour, grille, prix, veille, du_jour)


def _valeurs_jour(ctx: "Contexte", lignes: pd.DataFrame, valeur: float) -> tuple[np.ndarray, float] | None:
    """Valeur des lignes à chaque instant de la séance (quantité × cours à 5 minutes) et valeur à la clôture
    précédente. Un titre sans cours du jour garde sa valeur du moment. La série est recalée pour finir sur `valeur`
    (la valeur de la base) quand l'écart est faible ; trop grand, on renonce (None) plutôt que de déformer."""
    se = ctx.seance
    if se is None:
        return None
    v = np.zeros(len(se.grille))
    base = 0.0
    for r in lignes.itertuples():
        if r.value is None or math.isnan(r.value):
            continue
        px = se.prix.get(r.isin)
        d = ctx.prices.series.get(r.isin)
        if px is None or d is None or not len(d) or r.price is None or math.isnan(r.price):
            v += r.value
            base += r.value
            continue
        f = r.price / float(d.iloc[-1]) if d.iloc[-1] else 1.0
        v += r.quantity * f * px
        base += r.quantity * f * se.veille[r.isin]
    ecart = valeur - float(v[-1])
    if abs(ecart) > TOLERANCE_JOUR * max(valeur, 1.0):
        return None
    return v + ecart, base + ecart


def _stamp(t: pd.Timestamp) -> str:
    return t.strftime("%Y-%m-%dT%H:%M")


def _periode_jour(ctx: "Contexte", par_compte: dict[str, pd.DataFrame]) -> dict | None:
    """Série 1J d'une vue (somme de ses comptes, donc la somme des comptes vaut toujours le total)."""
    se = ctx.seance
    if se is None:
        return None
    total = np.zeros(len(se.grille))
    base = 0.0
    comptes: dict[str, list[list]] = {}
    for acc, va in par_compte.items():
        lg = ctx.pos[ctx.pos["account_id"] == acc] if len(ctx.pos) else ctx.pos
        r = _valeurs_jour(ctx, lg, float(va.value.iloc[-1]))
        if r is None:
            return None
        total += r[0]
        base += r[1]
        comptes[acc] = [[_stamp(t), _f(x, 2)] for t, x in zip(se.grille, r[0])]
    if base <= 0:
        return None
    var = float(total[-1]) - base
    return {
        "depuis": se.jour.isoformat(), "intraday": True, "variation": _f(var, 2), "variation_pct": _f(var / base),
        "cloture_precedente": _f(base, 2),
        "serie": [[_stamp(t), _f(x, 2)] for t, x in zip(se.grille, total)],
        "serie_pct": [[_stamp(t), _f(x / base - 1, 5)] for t, x in zip(se.grille, total)],
        "indice_serie": [], "investi": [], "comptes": comptes,
    }

# ---------- une vue (un compte, ou tous) ----------

class Contexte:
    """Ce qui est lu une fois pour toutes les vues."""

    def __init__(self, con: sqlite3.Connection, indice: str | None = None, rafraichir: bool = True):
        self.con = con
        self.replayed = portfolio.replay(con)
        self.book, self.prices = self.replayed
        self.ids = comptes_de_placement(con, self.book)
        self.series = {a: analytics.invested_series(con, (a,)) for a in self.ids}
        self.series = {a: v for a, v in self.series.items() if not v.empty}
        self.ids = [a for a in self.ids if a in self.series]
        self.pos = queries.positions(con, self.replayed)
        if not self.pos.empty:
            self.pos = self.pos[self.pos["account_id"].isin(self.ids)]
        if rafraichir and len(self.pos):
            rafraichir_seance(con, sorted(set(self.pos["isin"])))
        self.seance = charger_seance(con, self.prices)
        self.nom_indice = next((k for k in analytics.BENCHMARKS if k.lower() == (indice or "").lower()), "MSCI World")
        self.symbole = analytics.BENCHMARKS[self.nom_indice]
        self.kinds = {r[0]: r[1] for r in con.execute("SELECT isin, kind FROM instruments")}
        self.devises = {r[0]: r[1] for r in con.execute("SELECT isin, currency FROM instruments")}
        self.indice: pd.Series | None = None
        if self.series:
            self.fin = max(v.index[-1] for v in self.series.values())
            self.indice = cours_indice(self.symbole, min(v.index[0] for v in self.series.values()) - pd.Timedelta(days=10))
        self.frais = defaultdict(float)
        for r in con.execute("SELECT COALESCE(holding_account_id, account_id) acc, SUM(COALESCE(fees_cents, 0)) c"
                             " FROM transactions WHERE flow IN ('achat_titre', 'vente_titre') GROUP BY acc"):
            self.frais[r[0]] = r[1] / 100
        self.dividendes = self._dividendes()

    def _dividendes(self) -> dict[str, list[tuple[pd.Timestamp, float]]]:
        """Dividendes reçus par compte de placement : compte de détention, sinon compte qui détient le titre."""
        held: dict[str, dict[str, float]] = defaultdict(dict)
        for (acc, isin), line in self.book.lines.items():
            if acc in self.ids and line.quantity > 1e-6:
                held[isin][acc] = line.quantity
        out: dict[str, list] = defaultdict(list)
        for r in self.con.execute("SELECT date, amount_cents, isin, COALESCE(holding_account_id, account_id) acc"
                                  " FROM transactions WHERE flow = 'dividende'"):
            acc = r["acc"] if r["acc"] in self.ids else None
            if acc is None and r["isin"] in held:
                acc = max(held[r["isin"]], key=held[r["isin"]].get)
            if acc:
                out[acc].append((pd.Timestamp(r["date"]), r["amount_cents"] / 100))
        return out


def _variation_jour(ctx: Contexte, lignes: pd.DataFrame, valeur: float) -> dict:
    """Dernier cours contre clôture précédente, pondéré par les quantités (euros, et % de la valeur de la veille)."""
    var, depuis = 0.0, None
    for r in lignes.itertuples():
        s = ctx.prices.series.get(r.isin)
        if s is None or len(s) < 2 or r.price is None or math.isnan(r.price):
            continue
        factor = r.price / float(s.iloc[-1]) if s.iloc[-1] else 1.0
        var += r.quantity * (float(s.iloc[-1]) - float(s.iloc[-2])) * factor
        depuis = s.index[-2] if depuis is None else max(depuis, s.index[-2])
    if depuis is None:
        return {"variation": None, "variation_pct": None, "depuis": None}
    veille = valeur - var
    return {"variation": _f(var, 2), "variation_pct": _f(var / veille) if veille > 0 else None,
            "depuis": depuis.date().isoformat()}


def _periodes(ctx: Contexte, v: pd.DataFrame, par_compte: dict[str, pd.DataFrame], lignes: pd.DataFrame,
              avec_investi: bool) -> dict:
    out: dict[str, dict] = {}
    idx_ret = ctx.indice
    for label in PERIODES:
        if label == "1J":
            j = _variation_jour(ctx, lignes, float(v.value.iloc[-1]))
            ind = None
            if idx_ret is not None and len(idx_ret) >= 2:
                ind = _f(idx_ret.iloc[-1] / idx_ret.iloc[-2] - 1)
            jour = _periode_jour(ctx, par_compte)
            if jour is not None:
                out[label] = {**jour, "indice_pct": ind}
            else:
                out[label] = {**j, "indice_pct": ind, "intraday": False, "serie": [], "serie_pct": [],
                              "indice_serie": [], "investi": [], "comptes": {}}
            continue
        d0 = _debut(label, v.index[-1], v.index[0])
        base_date = v.index[v.index <= d0][-1] if (v.index <= d0).any() else v.index[0]
        w = v[v.index >= base_date]
        base_idx = float(w.twr_index.iloc[0])
        twr = float(w.twr_index.iloc[-1]) / base_idx - 1 if base_idx else None
        flows = float(w.flow.iloc[1:].sum())
        var = float(w.value.iloc[-1] - w.value.iloc[0] - flows)
        pos = _echantillon(len(w))
        ind_serie: list[list] = []
        ind_pct = None
        if idx_ret is not None:
            aligned = idx_ret.reindex(idx_ret.index.union(w.index)).ffill().reindex(w.index)
            if aligned.notna().all() and float(aligned.iloc[0]) > 0:
                rel = aligned / float(aligned.iloc[0]) - 1
                ind_pct = _f(rel.iloc[-1])
                ind_serie = _points(rel, pos, 5)
        comptes = {}
        for acc, va in par_compte.items():
            comptes[acc] = _points(va.value.reindex(va.index.union(w.index)).ffill().reindex(w.index).fillna(0.0), pos)
        out[label] = {
            "depuis": w.index[0].date().isoformat(), "intraday": True,
            "variation": _f(var, 2), "variation_pct": _f(twr), "indice_pct": ind_pct,
            "serie": _points(w.value, pos), "serie_pct": _points(w.twr_index / base_idx - 1, pos, 5),
            "indice_serie": ind_serie, "investi": _points(w.net_invested, pos) if avec_investi else [],
            "comptes": comptes,
        }
    return out


def _rendements_mensuels(v: pd.DataFrame) -> list[dict]:
    idx = v.twr_index
    moved = idx[idx != 100.0]
    if moved.empty:
        return []
    mois = idx.resample("ME").last()
    prev = mois.shift(1)
    prev.iloc[0] = float(idx.iloc[0])
    ret = (mois / prev - 1)
    ret = ret[ret.index >= moved.index[0].to_period("M").to_timestamp("M")]
    return [{"annee": int(d.year), "mois": int(d.month), "rendement": _f(r)} for d, r in ret.items()]


def _lignes(ctx: Contexte, pos: pd.DataFrame) -> list[dict]:
    fin = ctx.fin
    total = float(pos["value"].sum()) if len(pos) else 0.0
    out = []
    for r in pos.itertuples():
        value = None if r.value is None or math.isnan(r.value) else float(r.value)
        s = ctx.prices.series.get(r.isin)
        var: dict[str, dict] = {}
        for label in PERIODES:
            pct = None
            if label == "MAX":
                pct = None if math.isnan(r.gain_pct) else float(r.gain_pct)
            elif s is not None and len(s) >= 2:
                if label == "1J":
                    base = float(s.iloc[-2])
                else:
                    d0 = _debut(label, fin, fin)
                    base = _asof(s, d0) if d0 >= s.index[0] else None
                pct = float(s.iloc[-1]) / base - 1 if base else None
            eur = value - value / (1 + pct) if pct is not None and value is not None and pct > -1 else None
            var[label] = {"pct": _f(pct), "eur": _f(eur, 2)}
        gain = None if math.isnan(r.gain) else float(r.gain)
        kind = ctx.kinds.get(r.isin)
        out.append({
            "isin": r.isin, "nom": r.name, "compte": r.account_id, "compte_nom": r.account, "quantite": _f(r.quantity, 6),
            "valeur": _f(value, 2), "poids": _f(value / total) if value is not None and total else None,
            "plus_value": _f(gain, 2), "plus_value_pct": _f(r.gain_pct), "variation": var,
            "type": TYPES.get(kind) or analytics.kind_of(r.name or ""), "devise": ctx.devises.get(r.isin) or None,
        })
    return out


def _repartition(lignes: list[dict]) -> dict[str, list[dict]]:
    total = sum(x["valeur"] or 0 for x in lignes)
    out: dict[str, list[dict]] = {}
    for dim, key in (("compte", "compte_nom"), ("type", "type"), ("devise", "devise")):
        groups: dict[str, float] = defaultdict(float)
        for x in lignes:
            if x.get(key) and x["valeur"]:
                groups[x[key]] += x["valeur"]
        if groups and total:
            out[dim] = [{"nom": k, "valeur": _f(g, 2), "poids": _f(g / total)}
                        for k, g in sorted(groups.items(), key=lambda kv: -kv[1])]
    return out


def _dividendes_12m(ctx: Contexte, ids: list[str], valeur: float, cout: float | None) -> dict:
    fin = ctx.fin
    debut = (fin - pd.DateOffset(months=11)).to_period("M")
    mois = [debut + i for i in range(12)]
    par_mois = {str(m): 0.0 for m in mois}
    for acc in ids:
        for d, amount in ctx.dividendes.get(acc, []):
            if str(d.to_period("M")) in par_mois:
                par_mois[str(d.to_period("M"))] += amount
    total = sum(par_mois.values())
    return {"total": _f(total, 2), "par_mois": [{"mois": k, "montant": _f(x, 2)} for k, x in par_mois.items()],
            "rendement_valeur": _f(total / valeur) if valeur else None,
            "rendement_achat": _f(total / cout) if cout else None}


def _vue(ctx: Contexte, vid: str, nom: str, ids: list[str]) -> dict:
    v = analytics.invested_series(ctx.con, tuple(ids)) if len(ids) > 1 else ctx.series[ids[0]]
    pos = ctx.pos[ctx.pos["account_id"].isin(ids)] if len(ctx.pos) else ctx.pos
    # Coût connu : un compte dont ni le coût des lignes ni les versements ne sont en base (PEG saisi à la main)
    # n'a ni montant investi ni plus-value ; il reste compté dans la valeur.
    connus = [a for a in ids if (ctx.series[a].cost.iloc[-1] > 0 or ctx.series[a].net_invested.iloc[-1] > 0
                                 or ctx.series[a].value.iloc[-1] <= 0)]
    complet = len(connus) == len(ids)
    valeur = sum(float(ctx.series[a].value.iloc[-1]) for a in ids)
    investi = sum(float(ctx.series[a].net_invested.iloc[-1]) for a in connus) if connus else None
    cout = sum(float(ctx.series[a].cost.iloc[-1]) for a in connus) if connus else None
    latente = sum(float(ctx.series[a].value.iloc[-1] - ctx.series[a].cost.iloc[-1]) for a in connus) if connus else None
    realisee = sum(float(ctx.series[a].realised.iloc[-1]) for a in ids)
    divs = sum(x for a in ids for _, x in ctx.dividendes.get(a, []))
    frais = sum(ctx.frais[a] for a in ids)
    gain = latente + realisee + divs if latente is not None else None
    st = analytics.stats(v)
    ind = ctx.indice
    ind_stats = None
    if ind is not None and len(ind) > 20:
        days = (v.index[-1] - v.index[0]).days or 1
        ind_v = ind[ind.index >= v.index[0] - pd.Timedelta(days=5)]
        ann = (float(ind_v.iloc[-1]) / float(ind_v.iloc[0])) ** (365.25 / days) - 1 if days > 180 and len(ind_v) > 1 else None
        ind_stats = {"rendement_annualise": _f(ann), "volatilite": _f(_vol_1an(ind))}
    vol = _vol_1an(v.twr_index)
    lignes = _lignes(ctx, pos)
    par_compte = {a: ctx.series[a] for a in ids}
    return {
        "id": vid, "nom": nom, "nb_comptes": len(ids), "nb_lignes": len(lignes), "cout_connu": complet,
        "valeur": _f(valeur, 2), "investi": _f(investi, 2), "plus_value_latente": _f(latente, 2),
        "plus_value_realisee": _f(realisee, 2), "dividendes": _f(divs, 2), "frais": _f(frais, 2),
        "gain_total": _f(gain, 2), "gain_total_pct": _f(gain / investi) if gain is not None and investi else None,
        "rendement_annualise": _f(st.get("twr_annuel")), "volatilite": _f(vol),
        "plus_forte_baisse": _f(st.get("pire_baisse")), "indice": ind_stats,
        "periodes": _periodes(ctx, v, par_compte, pos, avec_investi=complet),
        "rendements_mensuels": _rendements_mensuels(v),
        "positions": lignes, "repartition": _repartition(lignes),
        "dividendes_12m": _dividendes_12m(ctx, ids, valeur, cout),
    }


def donnees(con: sqlite3.Connection, indice: str | None = None, rafraichir: bool = True) -> dict:
    ctx = Contexte(con, indice, rafraichir)
    if not ctx.ids:
        return {"comptes": [], "tous": None, "par_compte": {}, "note": "Aucune position détenue."}
    labels = {a: libelle_compte(con, a) for a in ctx.ids}
    ordre = sorted(ctx.ids, key=lambda a: -float(ctx.series[a].value.iloc[-1]))
    return {
        "date": ctx.fin.date().isoformat(), "periodes": PERIODES,
        "indice": {"nom": ctx.nom_indice, "symbole": ctx.symbole, "disponible": ctx.indice is not None},
        "comptes": [{"id": a, "nom": labels[a]} for a in ordre],
        "tous": _vue(ctx, "tous", "Tous les comptes", ordre),
        "par_compte": {a: _vue(ctx, a, labels[a], [a]) for a in ordre},
    }
