"""What well-known investors hold and changed, from their 13F filings (see sources.sec13f)."""
from __future__ import annotations

import sqlite3

import pandas as pd


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
    d["company"] = d.issuer.str.upper().str.replace(r"[^A-Z0-9 ]", "", regex=True).str.strip()
    held = d[d.change != "vendue"]
    g = held.groupby("company").agg(
        issuer=("issuer", "first"), ticker=("ticker", "first"), cusip=("cusip", "first"),
        holders=("investor", "nunique"),
        investors=("investor", lambda s: ", ".join(sorted(s))), avg_weight=("weight", "mean"),
        max_weight=("weight", "max"), value_usd=("value_usd", "sum"))
    moves = d.groupby(["company", "investor"]).change.agg(lambda s: next(
        (c for c in ("nouvelle", "renforcée", "allégée", "vendue") if c in set(s)), "=")).reset_index()
    moves = moves.groupby("company").change.agg(
        buyers=lambda s: int(s.isin(["nouvelle", "renforcée"]).sum()),
        sellers=lambda s: int(s.isin(["vendue", "allégée"]).sum()))
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
