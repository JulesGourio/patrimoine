"""Données de l'écran Patrimoine (onglet d'accueil) : une seule réponse (outil `accueil_ecran`).

Patrimoine net par type de compte (Placements, Comptes courants, Livrets) sur chaque période, d'où vient la
variation (épargne, marchés, dividendes et intérêts), répartition, indicateurs et liste des comptes avec leur
courbe sur 30 jours. Montants en euros, parts et variations en fractions (0,05 = 5 %). Un champ que la base ne
permet pas de calculer vaut `None`.
"""
from __future__ import annotations

import math
import sqlite3

import pandas as pd

from . import analytics, bourse, portfolio, queries

PERIODES = ["1S", "1M", "3M", "YTD", "1A", "MAX"]
MAX_POINTS = 120
POINTS_COMPTE = 20
JOURS_COMPTE = 30

# Regroupement de l'écran : (id, libellé) ; les groupes de `queries.account_groups` y sont rattachés.
TYPES = [("placements", "Placements"), ("courants", "Comptes courants"), ("livrets", "Livrets")]
TYPE_DU_GROUPE = {"Bourse": "placements", "Épargne salariale": "placements", "Livrets": "livrets", "Liquidités": "courants"}
LIQUIDES = ("courants", "livrets")  # disponible sous 48 h


def _f(x: float | None, nd: int = 2) -> float | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), nd)


def _asof(s: pd.Series, d: pd.Timestamp) -> float | None:
    """Dernière valeur au plus tard à la date `d`, `None` si la série commence après."""
    s = s[s.index <= d]
    return float(s.iloc[-1]) if len(s) else None


def _points(s: pd.Series, pos: list[int]) -> list[list]:
    return [[s.index[i].date().isoformat(), _f(s.iloc[i])] for i in pos]


def _entrees_sans_cout(con: sqlite3.Connection, comptes: set[str], d0: pd.Timestamp, d1: pd.Timestamp) -> float:
    """Valeur, à leur date, des titres entrés sans coût (transfert depuis un autre courtier, actions offertes) dans les
    comptes donnés pendant la période : un apport, pas un gain de marché."""
    rows = con.execute(
        "SELECT date, COALESCE(holding_account_id, account_id) AS acc, isin, quantity FROM transactions"
        " WHERE flow IN ('titres_offerts', 'transfert_titres') AND amount_cents = 0 AND quantity > 0 AND isin IS NOT NULL"
        " AND date > ? AND date <= ?", (d0.date().isoformat(), d1.date().isoformat())).fetchall()
    rows = [r for r in rows if r["acc"] in comptes]
    if not rows:
        return 0.0
    prices = portfolio.replay(con)[1]
    total = 0.0
    for r in rows:
        p = prices.get(r["isin"], pd.Timestamp(r["date"]))
        if p is not None:
            total += r["quantity"] * p
    return total


def _cascade(con: sqlite3.Connection, h: pd.DataFrame, total: pd.Series, d0: pd.Timestamp, d1: pd.Timestamp) -> dict:
    """Variation entre `d0` et `d1` décomposée : marchés (plus-values latentes et réalisées des lignes dont le prix de
    revient est connu aux deux dates), dividendes et intérêts reçus, et le reste, qui est l'épargne et les apports."""
    delta = float(total.loc[d1] - total.loc[d0])
    marches = 0.0
    comptes: set[str] = set()
    for acc, g in h.groupby("account_id"):
        g = g.set_index("date")
        a, b = g[g.index <= d0], g[g.index <= d1]
        if a.empty or b.empty:
            continue
        a, b = a.iloc[-1], b.iloc[-1]
        if (a.securities > 0 and a.cost <= 0) or (b.securities > 0 and b.cost <= 0):
            continue  # prix de revient inconnu : le mouvement reste dans l'épargne plutôt qu'inventé
        marches += (b.securities - b.cost + b.realised) - (a.securities - a.cost + a.realised)
        comptes.add(acc)
    marches -= _entrees_sans_cout(con, comptes, d0, d1)
    ids = sorted(set(h.account_id))
    row = con.execute(
        "SELECT COALESCE(SUM(amount_cents), 0) FROM transactions WHERE flow IN ('interets', 'dividende')"
        f" AND COALESCE(holding_account_id, account_id) IN ({','.join('?' * len(ids))})"
        " AND date > ? AND date <= ?", (*ids, d0.date().isoformat(), d1.date().isoformat())).fetchone()
    revenus = row[0] / 100
    return {"debut": _f(total.loc[d0]), "epargne": _f(delta - marches - revenus), "marches": _f(marches),
            "dividendes": _f(revenus), "fin": _f(total.loc[d1])}


def _indicateurs(con: sqlite3.Connection, disponible: float, total: float, synthese: dict | None) -> dict:
    s = synthese or {}
    ouverture = s.get("pea_ouverture")
    cinq_ans = (pd.Timestamp(ouverture) + pd.DateOffset(years=5)).date().isoformat() if ouverture else None
    bal = analytics.monthly_balance(con)
    full = queries.complete_months(bal, queries.data_date(con)).tail(12)
    depenses = float(full.depenses.mean()) if len(full) else 0.0
    return {
        "taux_epargne": _f(s.get("epargne_pct_revenus"), 4),
        "mois_precaution": _f(disponible / depenses, 1) if depenses > 0 else None,
        "depenses_mensuelles": _f(depenses) if depenses > 0 else None,
        "disponible_48h": _f(disponible), "disponible_part": _f(disponible / total, 4) if total else None,
        "pea_ouverture": ouverture, "pea_5_ans": bool(s.get("pea_5_ans")), "pea_5_ans_date": cinq_ans,
        "apres_impots": _f(s.get("apres_impots")), "impots_latents": _f(s.get("impots_latents")),
    }


def donnees(con: sqlite3.Connection, synthese: dict | None = None) -> dict:
    """Tout l'écran. `synthese` : réponse de l'outil `synthese` (taux d'épargne, impôts latents), `None` ou avec
    `erreur` quand elle manque."""
    h = queries.history(con)
    if h.empty:
        return {"erreur": "historique vide : lancer synchroniser"}
    if synthese is not None and synthese.get("erreur"):
        synthese = None
    groupes = queries.account_groups(con)
    type_de = {a: TYPE_DU_GROUPE.get(groupes.get(lbl), "courants") for a, lbl in h.drop_duplicates("account_id")[["account_id", "account"]].itertuples(index=False)}
    h = h.assign(type=h.account_id.map(type_de))
    par_compte = h.pivot_table(index="date", columns="account_id", values="value", aggfunc="sum").ffill().fillna(0.0)
    par_type = par_compte.T.groupby(type_de).sum().T.reindex(columns=[t for t, _ in TYPES], fill_value=0.0)
    total = par_type.sum(axis=1)
    fin, debut = total.index[-1], total.index[0]
    n_fin = float(total.iloc[-1])
    ids = [t for t, _ in TYPES if float(par_type[t].iloc[-1]) > 0.005]
    nom_type = dict(TYPES)

    periodes: dict[str, dict] = {}
    for label in PERIODES:
        d0 = bourse._debut(label, fin, debut)
        base = total.index[total.index <= d0][-1] if (total.index <= d0).any() else debut
        w = total[total.index >= base]
        pos = bourse._echantillon(len(w))
        v0 = float(w.iloc[0])
        periodes[label] = {
            "depuis": base.date().isoformat(), "complet": bool((total.index <= d0).any()),
            "variation": _f(n_fin - v0), "variation_pct": _f(n_fin / v0 - 1, 4) if v0 > 0 else None,
            "serie": _points(w, pos),
            "types": {t: _points(par_type[t][par_type.index >= base].clip(lower=0), pos) for t in ids},  # aires empilées : jamais sous zéro
            "cascade": _cascade(con, h, total, base, fin),
        }

    # Comptes : valeur du jour, variation sur 30 jours et petite courbe.
    securities = {r[0] for r in con.execute("SELECT DISTINCT account_id FROM positions WHERE quantity > 0")} | {"tr_cto", "tr_pea"}
    libelles = h.drop_duplicates("account_id").set_index("account_id")["account"]
    comptes = []
    d30 = fin - pd.Timedelta(days=JOURS_COMPTE)
    for acc in par_compte.columns:
        s = par_compte[acc]
        valeur = float(s.iloc[-1])
        if abs(valeur) < 0.005:
            continue
        non_nul = s.index[s.abs() > 0.005]
        # Compte ouvert depuis moins de 30 jours : pas de variation (elle ne dirait que le premier versement).
        ancien = _asof(s, d30) if s.index[0] <= d30 and len(non_nul) and non_nul[0] <= d30 else None
        w = s[s.index >= d30]
        pos = bourse._echantillon(len(w), POINTS_COMPTE)
        comptes.append({
            "id": acc, "nom": libelles[acc], "groupe": groupes.get(libelles[acc]), "type": type_de[acc],
            "type_nom": nom_type[type_de[acc]], "valeur": _f(valeur), "part": _f(valeur / n_fin, 4) if n_fin else None,
            "var_30j": _f(valeur - ancien) if ancien is not None else None,
            "var_30j_pct": _f(valeur / ancien - 1, 4) if ancien and ancien > 0 else None,
            "serie_30j": [_f(w.iloc[i]) for i in pos], "titres": acc in securities,
        })
    comptes.sort(key=lambda c: (ids.index(c["type"]) if c["type"] in ids else 9, -c["valeur"]))

    types = [{"id": t, "nom": nom_type[t], "valeur": _f(par_type[t].iloc[-1]),
              "part": _f(float(par_type[t].iloc[-1]) / n_fin, 4) if n_fin else None} for t in ids]
    prepayes = {r[0] for r in con.execute("SELECT id FROM accounts WHERE kind = 'prepaye'")}  # cartes : pas de l'épargne
    disponible = float(sum(par_compte[a].iloc[-1] for a in par_compte.columns
                           if type_de[a] in LIQUIDES and a not in prepayes))
    return {
        "date": fin.date().isoformat(), "nb_comptes": len(comptes), "total": _f(n_fin), "periodes_dispo": PERIODES,
        "types": types, "periodes": periodes, "comptes": comptes,
        "indicateurs": _indicateurs(con, disponible, n_fin, synthese),
        "note": "Épargne = variation moins marchés et dividendes (versements, salaire épargné, retraits) ; lignes sans "
                "prix de revient : leur variation reste dans l'épargne.",
    }
