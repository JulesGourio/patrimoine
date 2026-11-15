"""Données de la fiche d'un titre : une seule réponse (outil `titre`) pour l'écran « fiche titre » de l'appli.

Cours en euros sur l'échelle d'aujourd'hui, séries par période (1J à cours de séance quand ils sont stockés, voir
`prices.update_intraday`), position détenue (par compte), variations, dividendes et opérations.
Montants en euros, variations en fractions (0,05 = 5 %). Un champ que la base ne permet pas de calculer vaut `None` :
jamais d'estimation inventée.
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd

from . import bourse, portfolio, queries

PERIODES = ["1J", "1S", "1M", "3M", "YTD", "1A", "MAX"]
VARIATIONS = ["1J", "1S", "1M", "3M", "YTD", "1A"]
MAX_POINTS = 120
TOLERANCE_JOUR = 0.02
OPERATIONS_MAX = 200
SENS_TITRES = ("achat_titre", "saveback", "vente_titre", "titres_offerts", "transfert_titres")


def resoudre_isin(con: sqlite3.Connection, ident: str) -> str:
    """ISIN d'un identifiant : l'ISIN lui-même, ou le symbole Yahoo d'un titre connu."""
    if len(ident) == 12 and ident[:2].isalpha() and ident[2:].isalnum():
        return ident
    row = con.execute("SELECT isin FROM instruments WHERE symbol = ?", (ident,)).fetchone()
    return row["isin"] if row else ident


def operations(txs: list[sqlite3.Row], isin: str, later_splits: list[tuple[pd.Timestamp, float]]) -> list[dict]:
    """Achats et ventes d'un titre (saveback compris) : date, sens, quantité, prix net de frais, montant payé ou
    reçu, frais. Quantités et prix sont ramenés à l'échelle d'aujourd'hui (division par les regroupements ou
    divisions postérieurs)."""
    out = []
    for r in txs:
        if r["isin"] != isin or not r["quantity"] or r["flow"] not in SENS_TITRES:
            continue
        fees = (r["fees_cents"] or 0) / 100
        value = abs(r["amount_cents"]) / 100
        sale = r["flow"] == "vente_titre"
        if value == 0 and r["flow"] in ("titres_offerts", "transfert_titres"):
            continue
        ratio = math.prod(x for d, x in later_splits if d > pd.Timestamp(r["date"])) or 1.0
        out.append({"date": r["date"], "sens": "vente" if sale else "achat", "quantite": r["quantity"] * ratio,
                    "prix": (value + fees if sale else value - fees) / r["quantity"] / ratio,
                    "montant": value, "frais": fees})
    return out


def _periodes_cours(sc: pd.Series, seance: bourse.Seance | None, isin: str, cours: float | None) -> dict[str, dict]:
    """Par période : série de cours [[date, prix]], variation du cours en fraction et en euros par titre.
    `complet` est faux quand l'historique est plus court que la période."""
    out: dict[str, dict] = {}
    vide = {"intraday": False, "depuis": None, "serie": [], "pct": None, "eur": None, "complet": False}
    if sc is None or len(sc) == 0:
        return {p: dict(vide) for p in PERIODES}
    fin = sc.index[-1]
    for label in PERIODES:
        if label == "1J":
            out[label] = _jour(sc, seance, isin, cours)
            continue
        d0 = bourse._debut(label, fin, sc.index[0])
        complet = d0 >= sc.index[0]
        base_date = sc.index[sc.index <= d0][-1] if (sc.index <= d0).any() else sc.index[0]
        w = sc[sc.index >= base_date]
        base = float(w.iloc[0])
        pos = bourse._echantillon(len(w), MAX_POINTS)
        out[label] = {
            "intraday": len(w) >= 2, "depuis": w.index[0].date().isoformat(), "complet": bool(complet),
            "serie": [[w.index[i].date().isoformat(), bourse._f(w.iloc[i], 4)] for i in pos],
            "pct": bourse._f(float(w.iloc[-1]) / base - 1) if base else None,
            "eur": bourse._f(float(w.iloc[-1]) - base, 4),
        }
    return out


def _jour(sc: pd.Series, seance: bourse.Seance | None, isin: str, cours: float | None) -> dict:
    """Période 1J : cours de séance s'il y en a (dernier point recalé sur le cours courant), sinon seulement la
    variation entre les deux dernières clôtures."""
    if seance is not None and isin in seance.brut and cours:
        brut = seance.brut[isin]
        pos = bourse._echantillon(len(brut), bourse.MAX_POINTS_JOUR)
        px = brut.to_numpy(dtype=float)[pos].copy()
        # séance plus récente que la dernière clôture quotidienne : `cours` est la clôture de la veille, le dernier
        # cours de séance fait foi (le recaler dessus donnerait une variation nulle)
        plus_recente = len(sc) and seance.jour > sc.index[-1].date()
        if len(px) >= 2 and (plus_recente or abs(px[-1] - cours) <= TOLERANCE_JOUR * cours):
            if not plus_recente:
                px[-1] = cours
            base = seance.veille[isin]
            return {
                "intraday": True, "depuis": seance.jour.isoformat(), "complet": True, "base": bourse._f(base, 4),
                "serie": [[bourse._stamp(brut.index[i]), bourse._f(x, 4)] for i, x in zip(pos, px)],
                "pct": bourse._f(px[-1] / base - 1) if base else None, "eur": bourse._f(px[-1] - base, 4),
            }
    if len(sc) >= 2:
        base = float(sc.iloc[-2])
        return {"intraday": False, "depuis": sc.index[-2].date().isoformat(), "complet": True, "serie": [],
                "pct": bourse._f(float(sc.iloc[-1]) / base - 1) if base else None,
                "eur": bourse._f(float(sc.iloc[-1]) - base, 4)}
    return {"intraday": False, "depuis": None, "serie": [], "pct": None, "eur": None, "complet": False}


def _risque(sc: pd.Series) -> dict:
    """Volatilité annualisée et plus forte baisse du cours sur un an (None sans assez d'historique)."""
    w = sc[sc.index >= sc.index[-1] - pd.Timedelta(days=365)]
    r = w.pct_change().dropna()
    r = r[r != 0]
    vol = float(r.std() * math.sqrt(252)) if len(r) > 20 else None
    dd = float((w / w.cummax() - 1).min()) if len(w) > 20 else None
    return {"volatilite": bourse._f(vol), "plus_forte_baisse": bourse._f(dd)}


def donnees(con: sqlite3.Connection, ident: str, rafraichir: bool = True) -> dict:
    isin = resoudre_isin(con, ident)
    txs = portfolio.rows(con)
    replayed = portfolio.replay(con)
    book, px = replayed
    inst = con.execute("SELECT name, symbol, kind, currency FROM instruments WHERE isin = ?", (isin,)).fetchone()
    s = px.series.get(isin)
    sc = None
    if s is not None and len(s):
        sc = s * (px.factors[isin][-1][1] if px.factors.get(isin) else 1.0)
    pos_all = queries.positions(con, replayed)
    mine = pos_all[pos_all["isin"] == isin] if len(pos_all) else pos_all
    detenu = len(mine) > 0
    if rafraichir and (detenu or sc is not None):
        bourse.rafraichir_seance(con, [isin])
    seance = bourse.charger_seance(con, px)
    cours = (float(mine["price"].dropna().iloc[0]) if detenu and mine["price"].notna().any()
             else (float(sc.iloc[-1]) if sc is not None else None))
    periodes = _periodes_cours(sc, seance, isin, cours)

    later_splits = sorted((d, r) for (i, d), r in px.split_ratio.items() if i == isin)
    ops = sorted(operations(txs, isin, later_splits), key=lambda o: o["date"])
    divs = [{"date": r["date"], "montant": r["amount_cents"] / 100} for r in txs
            if r["isin"] == isin and r["flow"] == "dividende" and r["amount_cents"]]
    divs.sort(key=lambda d: d["date"])
    dividendes = None
    if divs:
        dividendes = {"total": bourse._f(sum(d["montant"] for d in divs), 2), "nb": len(divs),
                      "dernier": divs[-1]}
    toutes = sorted(
        list(ops) + [{"date": d["date"], "sens": "dividende", "quantite": None,
                                                    "prix": None, "montant": d["montant"], "frais": None} for d in divs],
        key=lambda o: o["date"], reverse=True)

    position = None
    pmp = None
    if detenu:
        total_pf = float(pos_all["value"].sum())
        valeur = float(mine["value"].sum())
        qte = float(mine["quantity"].sum())
        connus = mine[mine["cost"].notna()]
        investi = float(connus["cost"].sum()) if len(connus) else None
        pv = float((connus["value"] - connus["cost"]).sum()) if len(connus) else None
        pmp = float(connus["cost"].sum() / connus["quantity"].sum()) if len(connus) and connus["quantity"].sum() > 1e-9 else None
        eur_jour = periodes["1J"]["eur"]
        comptes = []
        for r in mine.itertuples():
            ok = not math.isnan(r.cost)
            comptes.append({
                "id": r.account_id, "nom": bourse.libelle_compte(con, r.account_id), "quantite": bourse._f(r.quantity, 6),
                "valeur": bourse._f(r.value, 2), "pmp": bourse._f(r.unit_cost, 4) if ok else None,
                "investi": bourse._f(r.cost, 2) if ok else None, "plus_value": bourse._f(r.gain, 2) if ok else None,
                "plus_value_pct": bourse._f(r.gain_pct) if ok else None,
            })
        position = {
            "valeur": bourse._f(valeur, 2), "quantite": bourse._f(qte, 6), "pmp": bourse._f(pmp, 4),
            "investi": bourse._f(investi, 2), "plus_value": bourse._f(pv, 2),
            "plus_value_pct": bourse._f(pv / investi) if pv is not None and investi else None,
            "variation_jour": bourse._f(eur_jour * qte, 2) if eur_jour is not None else None,
            "poids": bourse._f(valeur / total_pf) if total_pf else None,
            "comptes": sorted(comptes, key=lambda c: -(c["valeur"] or 0)),
        }
    kind = inst["kind"] if inst else None
    return {
        "isin": isin, "symbole": inst["symbol"] if inst else None, "nom": (inst["name"] if inst else None) or isin,
        "type": bourse.TYPES.get(kind) or (analytics_kind(inst["name"]) if inst else None),
        "devise": inst["currency"] if inst else None, "detenu": detenu,
        "cours": bourse._f(cours, 4), "date": sc.index[-1].date().isoformat() if sc is not None else None,
        "pmp": bourse._f(pmp, 4), "periodes": periodes,
        "variations": {p: {"pct": (periodes[p]["pct"] if periodes[p]["complet"] else None),
                           "eur": (periodes[p]["eur"] if periodes[p]["complet"] else None)} for p in VARIATIONS},
        "risque": _risque(sc) if sc is not None and len(sc) > 1 else {"volatilite": None, "plus_forte_baisse": None},
        "position": position, "dividendes": dividendes,
        "operations": toutes[:OPERATIONS_MAX], "nb_operations": len(toutes),
    }


def analytics_kind(name: str | None) -> str | None:
    from . import analytics

    return analytics.kind_of(name or "")
