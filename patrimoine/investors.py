"""What well-known investors hold and changed, from their 13F filings (see sources.sec13f)."""
from __future__ import annotations

import sqlite3

import pandas as pd


SUFFIXES = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "NV", "N", "V", "SA", "AG", "SE",
            "HLDGS", "HLDG", "HOLDINGS", "HOLDING", "GROUP", "THE", "CL", "A", "B", "C", "NEW", "DEL", "COM"}


def company(issuer: str) -> str:
    """Issuer name without legal suffixes, so 'NVIDIA Corp' and 'NVIDIA CORPORATION' match."""
    import re

    words = re.sub(r"[^A-Z0-9 ]", " ", (issuer or "").upper()).split()
    kept = [w for w in words if w not in SUFFIXES]
    return " ".join(kept) or " ".join(words)


def _filings(con: sqlite3.Connection) -> pd.DataFrame:
    """One filing per investor and quarter: the latest (an amendment restating the table wins)."""
    f = pd.read_sql_query("SELECT f.*, i.name, i.manager, i.style FROM f13_filings f JOIN investors i USING (cik)"
                          " WHERE i.active = 1", con)
    if f.empty:
        return f
    return f.sort_values("filed").groupby(["cik", "period"], as_index=False).last().sort_values("period")


def _holdings(con: sqlite3.Connection, accession: str) -> pd.DataFrame:
    h = pd.read_sql_query(
        "SELECT h.cusip, h.issuer, h.put_call, h.value_usd, h.shares, m.ticker FROM f13_holdings h"
        " LEFT JOIN cusip_map m USING (cusip) WHERE accession = ?", con, params=(accession,))
    h["weight"] = h.value_usd / h.value_usd.sum() if not h.empty else 0.0
    return h.sort_values("value_usd", ascending=False)


def overview(con: sqlite3.Connection) -> pd.DataFrame:
    f = _filings(con)
    if f.empty:
        return f
    rows = []
    for cik, g in f.groupby("cik"):
        last = g.iloc[-1]
        h = _holdings(con, last.accession)
        stock = h[h.put_call == ""]
        rows.append({"cik": cik, "name": last["name"], "manager": last.manager, "style": last["style"],
                     "period": last.period, "filed": last.filed, "total_usd": last.total_usd,
                     "positions": len(stock), "top10": stock.weight.head(10).sum(),
                     "top3": ", ".join((stock.ticker.fillna(stock.issuer)).head(3))})
    return pd.DataFrame(rows).sort_values("total_usd", ascending=False)


def portfolio(con: sqlite3.Connection, cik: int) -> tuple[pd.DataFrame, dict]:
    """Latest holdings with the change since the previous quarter (new, increased, reduced, sold)."""
    f = _filings(con)
    f = f[f.cik == cik]
    if f.empty:
        return pd.DataFrame(), {}
    last = f.iloc[-1]
    cur = _holdings(con, last.accession)
    prev = _holdings(con, f.iloc[-2].accession) if len(f) > 1 else cur.iloc[0:0]
    key = ["cusip", "put_call"]
    m = cur.merge(prev[key + ["shares", "value_usd", "weight"]], on=key, how="outer", suffixes=("", "_prev"))
    m["issuer"] = m.issuer.fillna(m.cusip)
    for c in ("shares", "value_usd", "weight", "shares_prev", "value_usd_prev", "weight_prev"):
        m[c] = m[c].fillna(0.0)
    sold = m.shares == 0
    new = m.shares_prev == 0
    m["change"] = "="
    m.loc[new, "change"] = "nouvelle"
    m.loc[sold, "change"] = "vendue"
    change = (m.shares / m.shares_prev.where(m.shares_prev > 0) - 1)
    m["shares_change"] = change
    m.loc[~new & ~sold & (change > 0.02), "change"] = "renforcée"
    m.loc[~new & ~sold & (change < -0.02), "change"] = "allégée"
    if sold.any():  # sold lines keep their last known name and ticker
        names = prev.set_index(key)[["issuer", "ticker"]]
        for i in m[sold].index:
            k = (m.at[i, "cusip"], m.at[i, "put_call"])
            if k in names.index:
                m.at[i, "issuer"], m.at[i, "ticker"] = names.loc[k].issuer, names.loc[k].ticker
    meta = {"name": last["name"], "manager": last.manager, "style": last["style"], "period": last.period,
            "filed": last.filed, "total_usd": last.total_usd, "previous_period": f.iloc[-2].period if len(f) > 1 else None}
    return m.sort_values(["value_usd", "value_usd_prev"], ascending=False), meta


def history(con: sqlite3.Connection, cik: int) -> pd.DataFrame:
    """Weight of each of the investor's current top holdings over the filed quarters."""
    f = _filings(con)
    f = f[f.cik == cik]
    frames = []
    for r in f.itertuples():
        h = _holdings(con, r.accession)
        h = h[h.put_call == ""]
        frames.append(h.assign(period=r.period)[["period", "cusip", "issuer", "ticker", "weight", "value_usd"]])
    return pd.concat(frames) if frames else pd.DataFrame()


def consensus(con: sqlite3.Connection, min_holders: int = 2) -> pd.DataFrame:
    """Stocks held by several of the followed investors in their latest filing, with who bought or sold."""
    f = _filings(con)
    if f.empty:
        return f
    rows = []
    for cik, g in f.groupby("cik"):
        m, meta = portfolio(con, cik)
        m = m[m.put_call == ""]
        for r in m.itertuples():
            rows.append({"cusip": r.cusip, "issuer": r.issuer, "ticker": r.ticker, "investor": meta["name"],
                         "weight": r.weight, "change": r.change, "value_usd": r.value_usd})
    d = pd.DataFrame(rows)
    # One company, several share classes (Alphabet A and C): group on the issuer name, not the CUSIP.
    d["company"] = d.issuer.map(company)
    held = d[d.change != "vendue"]
    g = held.groupby("company").agg(
        issuer=("issuer", "first"), ticker=("ticker", "first"), cusip=("cusip", "first"),
        holders=("investor", "nunique"),
        investors=("investor", lambda s: ", ".join(sorted(set(s)))), avg_weight=("weight", "mean"),
        max_weight=("weight", "max"), value_usd=("value_usd", "sum"))
    moves = d.groupby(["company", "investor"]).change.agg(lambda s: next(
        (c for c in ("nouvelle", "renforcée", "allégée", "vendue") if c in set(s)), "=")).reset_index()
    moves = moves.groupby("company").change.agg(
        buyers=lambda s: int(s.isin(["nouvelle", "renforcée"]).sum()),
        trimmers=lambda s: int((s == "allégée").sum()),
        sold_out=lambda s: int((s == "vendue").sum()))
    moves["sellers"] = moves.trimmers + moves.sold_out
    g = g.join(moves)
    return g[g.holders >= min_holders].sort_values(["holders", "value_usd"], ascending=False).reset_index()


def overlap(con: sqlite3.Connection, my_names: list[str], my_tickers: list[str]) -> pd.DataFrame:
    """Followed investors' latest positions in the same companies as Jules (matched by ticker or name)."""
    c = consensus(con, min_holders=1)
    if c.empty:
        return c
    tick = {t.upper() for t in my_tickers if t}
    words = [n.split("(")[0].strip().upper() for n in my_names if n]
    hit = c.ticker.fillna("").str.upper().isin(tick) | c.issuer.str.upper().apply(
        lambda s: any(w and (w in s or s.startswith(w)) for w in words))
    return c[hit]


# ---------- how copying a fund's 13F would have done ----------

PERF_SCHEMA = """
CREATE TABLE IF NOT EXISTS f13_perf (
    accession TEXT PRIMARY KEY,
    cik INTEGER NOT NULL,
    period TEXT NOT NULL,
    start TEXT NOT NULL,                -- filing date: the first day the basket was public
    until TEXT NOT NULL,                -- next filing date, or the last close for the latest one
    ret REAL,                           -- weighted return of the top holdings over [start, until]
    bench_ret REAL,                     -- S&P 500 (SPY) over the same days
    coverage REAL                       -- share of the filing's stock value priced
);
"""


def update_performance(con: sqlite3.Connection, top: int = 25) -> int:
    """Return of each filing's top ``top`` stock lines, held from the day it was filed to the next filing (or
    today), next to the S&P 500. It is what copying the fund on each 13F would have earned, before costs."""
    from datetime import date

    from .prices import change, closes
    from .sources import sec13f

    con.executescript(PERF_SCHEMA)
    f = _filings(con).sort_values(["cik", "period"])
    if f.empty:
        return 0
    baskets = {}
    for r in f.itertuples():
        h = _holdings(con, r.accession)
        baskets[r.accession] = h[h.put_call == ""].head(top)
    sec13f.map_cusips(con, [c for b in baskets.values() for c in b.cusip])
    for acc, b in baskets.items():  # tickers found by map_cusips
        baskets[acc] = _holdings(con, acc).query("put_call == ''").head(top)
    tickers = sorted({t for b in baskets.values() for t in b.ticker.dropna()} | {"SPY"})
    px = closes(tickers, f.filed.min())
    if px.empty:
        return 0
    last = px.index[-1].date().isoformat()
    n = 0
    for cik, g in f.groupby("cik"):
        g = g.reset_index(drop=True)
        for i, r in g.iterrows():
            until = g.filed[i + 1] if i + 1 < len(g) else last
            b = baskets[r.accession]
            rets = [(w, change(px, t, r.filed, until)) for t, w in zip(b.ticker, b.value_usd) if isinstance(t, str)]
            rets = [(w, x) for w, x in rets if x is not None]
            total = b.value_usd.sum()
            if not rets or not total:
                continue
            w = sum(x[0] for x in rets)
            con.execute("INSERT OR REPLACE INTO f13_perf VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (r.accession, int(cik), r.period, r.filed, until, sum(a * x for a, x in rets) / w,
                         change(px, "SPY", r.filed, until), w / total))
            n += 1
    con.commit()
    return n


def performance(con: sqlite3.Connection) -> pd.DataFrame:
    """Per fund: chained return of copying its 13F since its oldest stored filing, the S&P 500 over the same
    time, the latest quarter, and how much of each basket was priced."""
    con.executescript(PERF_SCHEMA)
    p = pd.read_sql_query("SELECT p.*, i.name, i.manager, i.style FROM f13_perf p JOIN investors i USING (cik)"
                          " WHERE i.active = 1 ORDER BY p.start", con)
    if p.empty:
        return p
    rows = []
    for cik, g in p.groupby("cik"):
        days = (pd.Timestamp(g.until.iloc[-1]) - pd.Timestamp(g.start.iloc[0])).days or 1
        ret = (1 + g.ret).prod() - 1
        bench = (1 + g.bench_ret.fillna(0)).prod() - 1
        rows.append({"cik": cik, "name": g.name.iloc[0], "manager": g.manager.iloc[0], "style": g["style"].iloc[0],
                     "since": g.start.iloc[0], "days": days, "ret": ret, "bench": bench, "excess": ret - bench,
                     "annual": (1 + ret) ** (365.25 / days) - 1 if days > 180 else None,
                     "last_quarter": g.ret.iloc[-1], "coverage": g.coverage.mean()})
    return pd.DataFrame(rows).sort_values("excess", ascending=False)
