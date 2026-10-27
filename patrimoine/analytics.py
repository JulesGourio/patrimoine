"""Portfolio and spending statistics for the dashboard and the MCP server.

Vocabulary (also shown in the dashboard):
- PMP (prix moyen pondéré): average price paid per share, buying fees included; a sale does not change it.
- Plus-value latente: current value minus the cost of what is still held (not taxed until sold).
- Plus-value réalisée: sale proceeds minus the cost of the shares sold.
- TWR (time-weighted return): the performance of the investments themselves, neutral to when money was
  added or withdrawn; the right figure to compare with an index.
- TRI (money-weighted return, XIRR): the annual return of *your* money, given when you actually invested it.
"""
from __future__ import annotations

import math
import sqlite3
from collections import defaultdict
from datetime import date

import pandas as pd

from . import portfolio

INVESTED = ("tr_cto", "tr_pea")
MIN_BASE = 1000.0
BENCHMARKS = {"MSCI World": "IWDA.AS", "S&P 500": "CSPX.AS", "CAC 40": "^FCHI", "Nasdaq 100": "EQQQ.DE"}


# ---------- returns ----------

def xirr(flows: list[tuple[date, float]], guess: float = 0.1) -> float | None:
    """Annual rate r such that sum(cf / (1 + r) ** years) = 0. Money in is negative, money out positive."""
    flows = [(d, v) for d, v in flows if v]
    if len(flows) < 2 or all(v >= 0 for _, v in flows) or all(v <= 0 for _, v in flows):
        return None
    t0 = min(d for d, _ in flows)
    years = [((d - t0).days / 365.25, v) for d, v in flows]

    def npv(r: float) -> float:
        return sum(v / (1 + r) ** t for t, v in years)

    lo, hi = -0.9999, 10.0
    if npv(lo) * npv(hi) > 0:
        return None
    for _ in range(200):  # bisection: slow but never diverges
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
        if hi - lo < 1e-7:
            break
    return (lo + hi) / 2


def security_flows(con: sqlite3.Connection, accounts: tuple[str, ...] = INVESTED) -> pd.Series:
    """Money put into securities per day (buys and gifts positive, sales negative), EUR."""
    out: dict[str, float] = defaultdict(float)
    for r in con.execute("SELECT date, flow, amount_cents, COALESCE(holding_account_id, account_id) acc FROM transactions"
                         " WHERE flow IN ('achat_titre', 'vente_titre', 'saveback', 'titres_offerts')"):
        if r["acc"] not in accounts:
            continue
        v = abs(r["amount_cents"]) / 100
        out[r["date"]] += -v if r["flow"] == "vente_titre" else v
    s = pd.Series(out, dtype=float)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def invested_series(con: sqlite3.Connection, accounts: tuple[str, ...] = INVESTED) -> pd.DataFrame:
    """Daily market value, net money put in, cumulated gain, and the time-weighted index (base 100)."""
    v = pd.read_sql_query(
        "SELECT date, SUM(securities_cents) / 100.0 AS value, SUM(cost_cents) / 100.0 AS cost,"
        " SUM(realised_cents) / 100.0 AS realised FROM valuations WHERE account_id IN (%s) GROUP BY date ORDER BY date"
        % ",".join("?" * len(accounts)), con, params=accounts, parse_dates=["date"]).set_index("date")
    if v.empty:
        return v
    # The valuations table starts with the oldest bank history (2016); investing started later. Before the first
    # day with securities, there is nothing to measure (and annualising over those years would dilute returns).
    started = v.index[(v.value > 0) | (v.cost > 0)]
    if len(started):
        v = v[v.index >= started[0]]
    flows = security_flows(con, accounts).reindex(v.index, fill_value=0.0)
    v["flow"] = flows
    v["net_invested"] = flows.cumsum()
    v["gain"] = v.value - v.net_invested
    # Daily return with the day's flow at the close: r = (V_t - F_t) / V_{t-1} - 1.
    prev = v.value.shift(1)
    # While the portfolio is tiny (a few hundred euros of turbos in 2024), one trade swings the index by
    # tens of percent: the index only starts once there is MIN_BASE euros invested.
    r = ((v.value - v.flow) / prev - 1).where(prev >= MIN_BASE)
    r = r.clip(-0.5, 0.5).fillna(0.0)
    v["twr_index"] = 100 * (1 + r).cumprod()
    v["drawdown"] = v.twr_index / v.twr_index.cummax() - 1
    return v


def stats(v: pd.DataFrame, con: sqlite3.Connection | None = None) -> dict[str, float | None]:
    if v.empty:
        return {}
    idx = v.twr_index
    days = (idx.index[-1] - idx.index[0]).days or 1
    ret = idx.pct_change().dropna()
    ret = ret[ret != 0]

    def since(d: pd.Timestamp) -> float | None:
        past = idx[idx.index <= d]
        return idx.iloc[-1] / past.iloc[-1] - 1 if len(past) else None

    end = idx.index[-1]
    out = {
        "twr_total": idx.iloc[-1] / 100 - 1,
        "twr_annuel": (idx.iloc[-1] / 100) ** (365.25 / days) - 1 if days > 180 else None,
        "twr_ytd": since(pd.Timestamp(end.year - 1, 12, 31)),
        "twr_1an": since(end - pd.Timedelta(days=365)),
        "twr_1m": since(end - pd.Timedelta(days=30)),
        "volatilite": ret.std() * math.sqrt(252) if len(ret) > 20 else None,
        "pire_baisse": v.drawdown.min(),
        "baisse_actuelle": v.drawdown.iloc[-1],
        "gain_total": v.gain.iloc[-1],
        "net_investi": v.net_invested.iloc[-1],
        "valeur": v.value.iloc[-1],
    }
    flows = [(d.date(), -f) for d, f in v.flow.items() if f]
    flows.append((end.date(), v.value.iloc[-1]))
    out["tri"] = xirr(flows)
    return out


def benchmark(con: sqlite3.Connection, v: pd.DataFrame, symbol: str) -> pd.Series | None:
    """What the same buys and sales would be worth if each had gone into ``symbol`` instead (EUR)."""
    from .prices import history, to_eur

    if v.empty:
        return None
    s, currency = history(symbol, v.index[0].date())
    s = to_eur(s, currency, v.index[0].date()) if not s.empty else None
    if s is None or s.empty:
        return None
    px = s.reindex(v.index.union(s.index)).ffill().reindex(v.index).bfill()
    units = (v.flow / px).cumsum()
    return (units * px).rename(symbol)


# ---------- lines ----------

def lines(con: sqlite3.Connection) -> pd.DataFrame:
    """Every security ever held on Trade Republic: invested, received, current value, gain, TRI, holding time."""
    names = dict(con.execute("SELECT isin, name FROM instruments"))
    book, prices = portfolio.replay(con)
    today = pd.Timestamp.today().normalize()
    cf: dict[tuple[str, str], list[tuple[date, float]]] = defaultdict(list)
    first: dict[tuple[str, str], str] = {}
    for r in con.execute("SELECT date, flow, amount_cents, isin, COALESCE(holding_account_id, account_id) acc"
                         " FROM transactions WHERE isin IS NOT NULL AND flow IN"
                         " ('achat_titre', 'vente_titre', 'saveback', 'titres_offerts', 'dividende') ORDER BY date"):
        key = (r["acc"], r["isin"])
        first.setdefault(key, r["date"])
        v = abs(r["amount_cents"]) / 100
        cf[key].append((date.fromisoformat(r["date"]), v if r["flow"] in ("vente_titre", "dividende") else -v))
    rows = []
    for key, flows in cf.items():
        acc, isin = key
        line = book.lines.get(key)
        qty = line.quantity if line else 0.0
        price = prices.get(isin, today) if qty > 1e-6 else None
        value = qty * price if price else 0.0
        put = -sum(v for _, v in flows if v < 0)
        got = sum(v for _, v in flows if v > 0)
        rows.append({
            "account": {"tr_cto": "Compte-titres", "tr_pea": "PEA", "peg_airbus": "PEG Airbus"}.get(acc, acc), "isin": isin,
            "name": names.get(isin) or isin, "open": qty > 1e-6, "invested": put, "received": got, "value": value,
            "gain": value + got - put, "gain_pct": (value + got - put) / put if put else None,
            "tri": xirr(flows + [(today.date(), value)]) if (value or got) else None,
            "since": pd.Timestamp(first[key]), "days": (today - pd.Timestamp(first[key])).days,
            "kind": kind_of(names.get(isin) or ""),
        })
    return pd.DataFrame(rows).sort_values("gain", ascending=False) if rows else pd.DataFrame()


def kind_of(name: str) -> str:
    from .prices import CRYPTO_NAMES

    n = name.lower()
    if name.strip().upper() in CRYPTO_NAMES:
        return "Crypto"
    if n.startswith(("long", "short")):
        return "Turbo / warrant"
    if any(k in n for k in ("2x", "3x", "lev")):
        return "ETF à levier"
    if any(k in n for k in ("(acc)", "(dist)", "etf", "msci", "s&p", "ftse", "core ")):
        return "ETF"
    return "Action"


REGIONS = [("korea", "Corée"), ("china", "Chine"), ("cac", "France"), ("airbus", "Europe"), ("s&p", "États-Unis"),
           ("nasdaq", "États-Unis"), ("usa", "États-Unis"), ("msci usa", "États-Unis"), ("xiaomi", "Chine"),
           ("gold", "Matières premières"), ("silver", "Matières premières"), ("coffee", "Matières premières"),
           ("rare earth", "Monde (thématique)"), ("space", "Monde (thématique)"), ("defense", "Monde (thématique)")]


def region_of(name: str) -> str:
    n = name.lower()
    return next((r for k, r in REGIONS if k in n), "Autre")


# ---------- spending ----------

def recurring(spending: pd.DataFrame, min_months: int = 3) -> pd.DataFrame:
    """Merchants paid in at least ``min_months`` distinct months with a steady amount: subscriptions, rent…"""
    if spending.empty:
        return pd.DataFrame()
    sp = spending[spending.amount > 0]
    g = sp.groupby("merchant").agg(months=("month", "nunique"), median=("amount", "median"), std=("amount", "std"),
                                   last=("date", "max"), category=("category", "first"), n=("amount", "size"))
    g = g[(g.months >= min_months) & (g.n <= g.months * 1.5) & ((g["std"].fillna(0) / g["median"]) < 0.25)]
    g = g[g["last"] >= pd.Timestamp.today() - pd.Timedelta(days=45)]  # still running
    g["annual"] = g["median"] * 12
    return g.sort_values("annual", ascending=False).reset_index()


def monthly_balance(con: sqlite3.Connection) -> pd.DataFrame:
    """Per month: income, spending (fees included), savings and savings rate.

    Refunds (friends paying back their share, health insurance) are netted off spending rather than counted
    as income: otherwise a shared dinner paid by Jules would inflate both sides and the savings rate.
    Windfalls (inheritance, gifts) are kept apart in ``heritage``: neither income nor savings.
    """
    from .categories import REFUNDS, WINDFALLS

    f = pd.read_sql_query("SELECT date, flow, amount_cents, COALESCE(category_override, category) AS category"
                          " FROM transactions WHERE flow IN ('revenu','depense','frais','interets','dividende')",
                          con, parse_dates=["date"])
    f["month"] = f.date.dt.to_period("M").dt.to_timestamp()
    f.loc[(f.flow == "revenu") & f.category.isin(REFUNDS), "flow"] = "remboursement"
    f.loc[(f.flow == "revenu") & (f.category == "Salaire"), "flow"] = "salaire"
    f.loc[(f.flow == "revenu") & f.category.isin(WINDFALLS), "flow"] = "heritage"
    p = f.pivot_table(index="month", columns="flow", values="amount_cents", aggfunc="sum", fill_value=0) / 100
    col = lambda c: p[c] if c in p else pd.Series(0.0, index=p.index)  # noqa: E731
    out = pd.DataFrame({"revenus": col("salaire") + col("revenu") + col("interets") + col("dividende"),
                        "depenses": -(col("depense") + col("frais")) - col("remboursement")})
    out["salaire"] = col("salaire")
    out["remboursements"] = col("remboursement")
    out["heritage"] = col("heritage")
    out["epargne"] = out.revenus - out.depenses
    out["taux"] = (out.epargne / out.revenus).where(out.revenus > 0)
    return out
