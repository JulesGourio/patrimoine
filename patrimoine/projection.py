"""Projection Monte-Carlo du patrimoine : calcul pur (numpy), sans pandas ni affichage.

Chaque scénario tire au hasard le rendement mensuel des actions (log-normal, moyenne et volatilité données) ;
la poche sûre (livrets) rend un taux fixe. L'épargne mensuelle grandit chaque année. Graine fixe : même
entrée, même résultat. Montants en euros (flottants) en entrée ; les sorties sont arrondies à l'euro.
"""
from __future__ import annotations

from datetime import date

import numpy as np

SEED = 7
SCENARIOS = 2000
LEVER_SCENARIOS = 500
MAX_POINTS = 120


def _adds(monthly: float, growth_pct: float, months: int) -> np.ndarray:
    return np.array([monthly * (1 + growth_pct / 100) ** (m // 12) for m in range(months)])


def simulate(risky0: float, safe0: float, share: float, monthly: float, growth_pct: float, mu: float, vol: float,
             safe_rate: float, months: int, n: int) -> np.ndarray:
    """Valeur totale de chaque scénario à chaque mois, forme (n, months + 1). Taux en fraction (0.07)."""
    rng = np.random.default_rng(SEED)
    m_mu, m_vol = np.log(1 + mu) / 12, vol / np.sqrt(12)
    r_risky = np.exp(rng.normal(m_mu - m_vol ** 2 / 2, m_vol, (n, months))) - 1
    r_safe = (1 + safe_rate) ** (1 / 12) - 1
    total = risky0 + safe0
    risky = np.full(n, total * share)
    safe = np.full(n, total * (1 - share))
    path = np.empty((n, months + 1))
    path[:, 0] = risky + safe
    adds = _adds(monthly, growth_pct, months)
    for m in range(months):
        risky = risky * (1 + r_risky[:, m]) + adds[m] * share
        safe = safe * (1 + r_safe) + adds[m] * (1 - share)
        path[:, m + 1] = risky + safe
    return path


def _month_label(start: date, i: int) -> str:
    k = start.year * 12 + start.month - 1 + i
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def _eur(x: float) -> int:
    return int(round(float(x)))


def project(risky0: float, safe0: float, *, horizon_ans: int, monthly: float, growth_pct: float, goal: float,
            share_pct: float, mu_pct: float, vol_pct: float, safe_pct: float, inflation_pct: float,
            start: date | None = None) -> dict:
    """Projection complète (voir l'outil `projection` de `api` pour la description des champs)."""
    start = (start or date.today()).replace(day=1)
    total0 = risky0 + safe0
    share, mu, vol, safe_rate, inflation = share_pct / 100, mu_pct / 100, vol_pct / 100, safe_pct / 100, inflation_pct / 100
    months = int(horizon_ans) * 12
    path = simulate(risky0, safe0, share, monthly, growth_pct, mu, vol, safe_rate, months, SCENARIOS)
    deflate = (1 + inflation) ** (np.arange(months + 1) / 12)
    q = {p: np.percentile(path, p, axis=0) for p in (10, 25, 50, 75, 90)}
    adds = _adds(monthly, growth_pct, months)
    cum_paid = total0 + np.concatenate([[0.0], np.cumsum(adds)])
    paid = float(cum_paid[-1])
    final = path[:, -1]
    med = float(np.median(final))

    reach = hit = None
    if goal:
        reach = float((path >= goal).any(axis=1).mean())
        idx = np.nonzero(q[50] >= goal)[0]
        hit = _month_label(start, int(idx[0])) if len(idx) else None

    def median_with(monthly_=monthly, share_=share, mu_=mu) -> float:
        p = simulate(risky0, safe0, share_, monthly_, growth_pct, mu_, vol, safe_rate, months, LEVER_SCENARIOS)
        return float(np.median(p[:, -1]))

    ref = median_with()
    levers = [("Épargner 200 € de plus par mois", median_with(monthly_=monthly + 200) - ref),
              ("Épargner 200 € de moins par mois", median_with(monthly_=max(monthly - 200, 0)) - ref),
              ("10 points de plus en actions", median_with(share_=min(share + 0.1, 1)) - ref),
              ("10 points de moins en actions", median_with(share_=max(share - 0.1, 0)) - ref),
              ("Rendement actions +1 point", median_with(mu_=mu + 0.01) - ref),
              ("Rendement actions −1 point", median_with(mu_=mu - 0.01) - ref)]

    if months + 1 <= MAX_POINTS:
        keep = np.arange(months + 1)
    else:
        keep = np.unique(np.linspace(0, months, MAX_POINTS).round().astype(int))
    serie: dict = {"dates": [_month_label(start, int(i)) for i in keep]}
    for p in (10, 25, 50, 75, 90):
        serie[f"p{p}"] = [_eur(q[p][i]) for i in keep]
    serie["mediane_reelle"] = [_eur(q[50][i] / deflate[i]) for i in keep]
    serie["verse"] = [_eur(cum_paid[i]) for i in keep]

    return {
        "depart": {"total": _eur(total0), "risque": _eur(risky0), "sur": _eur(safe0)},
        "hypotheses": {"horizon_ans": int(horizon_ans), "epargne_mensuelle": _eur(monthly),
                       "hausse_epargne_pct": growth_pct, "objectif_eur": _eur(goal), "part_actions_pct": share_pct,
                       "rendement_actions_pct": mu_pct, "volatilite_pct": vol_pct,
                       "rendement_livrets_pct": safe_pct, "inflation_pct": inflation_pct},
        "final": {"mediane": _eur(med), "p10": _eur(q[10][-1]), "p90": _eur(q[90][-1]),
                  "mediane_reelle": _eur(med / deflate[-1]), "p10_reel": _eur(q[10][-1] / deflate[-1]),
                  "p90_reel": _eur(q[90][-1] / deflate[-1])},
        "verse": _eur(paid),
        "gains_medians": _eur(med - paid),
        "objectif": {"montant": _eur(goal), "chance": reach, "mois_median": hit} if goal else None,
        "serie": serie,
        "leviers": [{"levier": name, "effet": _eur(v)} for name, v in sorted(levers, key=lambda x: x[1])],
        "note": "Scénarios aléatoires (2000, graine fixe) : issues plausibles, pas une promesse. Avant impôts.",
    }
