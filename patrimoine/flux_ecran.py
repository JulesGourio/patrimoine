"""Données de l'écran Flux (revenus et dépenses) : tout ce que la maquette montre en plus de `flux` et
`depenses_operations`. Montants en euros (la base garde des centimes entiers), fractions pour les taux."""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from . import analytics, queries


def _mois_fenetre(fin: pd.Timestamp, n: int) -> pd.DatetimeIndex:
    return pd.date_range(end=fin, periods=n, freq="MS")


def _salaire(bal: pd.DataFrame) -> dict:
    """Dernier salaire et sa variation : comparé au dernier niveau différent de plus de 1 %, depuis le premier mois au
    niveau actuel."""
    s = bal["salaire"][bal["salaire"] > 0]
    if s.empty:
        return {"montant": None, "evolution": None, "depuis": None}
    actuel = float(s.iloc[-1])
    depuis = s.index[-1]
    for m, v in s.iloc[:-1][::-1].items():
        if abs(v - actuel) > 0.01 * actuel:
            return {"montant": actuel, "evolution": actuel / float(v) - 1, "depuis": depuis.strftime("%Y-%m")}
        depuis = m
    return {"montant": actuel, "evolution": None, "depuis": None}


def donnees(con: sqlite3.Connection, mois: int = 13, aujourdhui: date | None = None) -> dict:
    """Par mois (les `mois` derniers, le mois courant compris) : revenus par source (salaire, primes, placements,
    autres), dépenses nettes des remboursements, épargne, taux (nul tant que le mois est incomplet), part investie,
    charges fixes (dépenses récurrentes mensuelles) et dépenses courantes ; indicateurs sur 12 mois complets ;
    prélèvements récurrents encore attendus ce mois-ci."""
    today = pd.Timestamp(aujourdhui or date.today()).normalize()
    ref = queries.data_date(con)
    fin = today.to_period("M").to_timestamp()
    bal = analytics.monthly_balance(con)
    flux = queries.flows_by_month(con)
    sp = queries.spending(con)
    rec = analytics.recurring(sp)
    fixes = set(rec["merchant"]) if not rec.empty else set()

    tous = pd.date_range(end=fin, periods=max(mois, 25), freq="MS")
    bal = bal.reindex(tous, fill_value=0.0)
    flux = flux.reindex(tous, fill_value=0.0)
    col = lambda c: flux[c] if c in flux else pd.Series(0.0, index=tous)  # noqa: E731
    bal["placements"] = col("interets") + col("dividende")
    bal["autres"] = (bal.revenus - bal.salaire - bal.primes - bal.placements).clip(lower=0)
    bal["investi"] = (-(col("achat_titre") + col("vente_titre"))).clip(lower=0)
    bal["charges_fixes"] = sp[sp.merchant.isin(fixes)].groupby("month")["amount"].sum().reindex(tous, fill_value=0.0)
    # Même règle que `synthese` et l'accueil : un mois est complet s'il est fini à la date des données (une base plus
    # ancienne que le mois n'en couvre pas la fin).
    bal["partiel"] = ~bal.index.isin(queries.complete_months(bal, ref).index)
    # Le premier mois d'activité compte pour du vide avant lui : pas de taux ni de moyenne sur ces mois-là.
    actifs = (bal.revenus != 0) | (bal.depenses != 0)
    debut = bal.index[actifs].min() if actifs.any() else None
    bal["vide"] = True if debut is None else bal.index < debut

    lignes = []
    for m, r in bal.iloc[-mois:].iterrows():
        fixes_m = min(float(r.charges_fixes), max(float(r.depenses), 0.0))
        taux = None if r.partiel or r.vide or r.revenus <= 0 else float(r.taux)
        lignes.append({
            "mois": m.strftime("%Y-%m"), "revenus": float(r.revenus), "salaire": float(r.salaire), "primes": float(r.primes),
            "placements": float(r.placements), "autres": float(r.autres), "depenses": float(r.depenses),
            "epargne": float(r.epargne), "taux": taux, "investi": float(r.investi) + 0.0,
            "remboursements": float(r.remboursements) + 0.0, "charges_fixes": fixes_m,
            "depenses_courantes": float(r.depenses) - fixes_m, "partiel": bool(r.partiel), "vide": bool(r.vide),
        })

    complets = bal[~bal.partiel & ~bal.vide]
    d12, p12 = complets.tail(12), complets.iloc[-24:-12]
    evolution = float(d12.revenus.sum() / p12.revenus.sum() - 1) if len(d12) == 12 and len(p12) == 12 and p12.revenus.sum() > 0 else None
    taux_moyen = float(d12.epargne.sum() / d12.revenus.sum()) if len(d12) and d12.revenus.sum() > 0 else None
    indicateurs = {
        "taux_moyen_12m": taux_moyen, "mois_comptes": len(d12), "revenus_moyens": float(d12.revenus.mean()) if len(d12) else None,
        "revenus_12m": float(d12.revenus.sum()), "evolution_1an": evolution,
        "placements_12m": float(d12.placements.sum()), "salaire": _salaire(complets),
        "revenus_par_source_12m": {k: float(d12[k].sum()) for k in ("salaire", "primes", "placements", "autres")},
    }

    a_venir = []
    if not rec.empty:
        for r in rec[rec.status == "actif"].itertuples():
            if r.last.to_period("M").to_timestamp() >= fin:
                continue  # déjà prélevé ce mois-ci
            jour = min(r.last.day, (fin + pd.offsets.MonthEnd(0)).day)
            d = (fin + timedelta(days=jour - 1)).date()
            if d < today.date():
                continue  # la date est passée sans prélèvement vu : on ne l'annonce pas
            a_venir.append({"commercant": r.merchant, "date": d.isoformat(), "dans_jours": (d - today.date()).days,
                            "montant": float(r.amount), "categorie": r.category if isinstance(r.category, str) else None})
    a_venir.sort(key=lambda x: x["date"])
    return {"donnees_au": ref.date().isoformat(), "mois": lignes, "indicateurs": indicateurs,
            "a_venir": a_venir, "a_venir_total": round(sum(x["montant"] for x in a_venir), 2)}
