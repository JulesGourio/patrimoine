"""The radar: stocks the followed smart money is buying, at a glance.

Signals, per US ticker:
- members of Congress: purchases in the last 90 days (trade date), the selected members (politicians.auto_follow)
  counting more than the others; sales count against;
- funds: new or increased lines in their latest 13F, funds that beat the S&P 500 when copied counting more;
- trend: price change over 1, 3 and 6 months and distance to the 52-week high (Yahoo);
- analysts: consensus rating and mean target price (Yahoo).
The score only ranks what to look at first. Everything here is public, late (up to 45 days for members, up to
4.5 months for 13F) and says nothing about the price paid: a list of ideas to research, never a buy signal.

"Chez toi": how much of each stock Jules already owns through his ETFs (their top 10 lines, from the US ETF
tracking the same index) or directly.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import date, timedelta

import pandas as pd

from . import db, investors, politicians, queries

log = logging.getLogger(__name__)

# Jules's lines -> (US listing whose top holdings stand for the fund's, leverage) or a direct US ticker.
PROXIES = {
    "FR0011550185": ("SPY", 1.0),       # S&P 500
    "FR0010342592": ("QQQ", 2.0),       # Nasdaq 100 x2
    "IE00BHZRR030": ("EWY", 1.0),       # FTSE Korea
    "IE000YU9K6K2": ("UFO", 1.0),       # space
    "IE000KHX9DX6": ("REMX", 1.0),      # rare earths and strategic metals
}
DIRECT = {"NL0000235190": "EADSY"}      # Airbus (US ADR)
# Share classes of one company count as one stock.
ALIASES = {"GOOG": "GOOGL", "BRK.A": "BRK.B", "BRK-B": "BRK.B", "FOX": "FOXA", "NWS": "NWSA", "LBTYK": "LBTYA"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS radar (
    ticker TEXT PRIMARY KEY,
    data TEXT NOT NULL                  -- JSON row, see build()
);
"""


def exposure(con: sqlite3.Connection) -> dict[str, dict]:
    """{US ticker: {"eur": value Jules holds through his lines, "via": [line names]}}."""
    import yfinance as yf

    pos = queries.positions(con)
    out: dict[str, dict] = {}

    def add(ticker: str, eur: float, via: str) -> None:
        e = out.setdefault(ticker, {"eur": 0.0, "via": []})
        e["eur"] += eur
        if via not in e["via"]:
            e["via"].append(via)

    for r in pos.itertuples():
        if not r.value:
            continue
        if r.isin in DIRECT:
            add(DIRECT[r.isin], r.value, r.name)
        if r.isin in PROXIES:
            proxy, lev = PROXIES[r.isin]
            try:
                top = yf.Ticker(proxy).funds_data.top_holdings
            except Exception as e:  # noqa: BLE001
                log.warning("ETF %s: %s", proxy, e)
                continue
            for t, w in top["Holding Percent"].items():
                add(ALIASES.get(str(t), str(t)), r.value * float(w) * lev, r.name)
    return out


def _congress_signals(con: sqlite3.Connection, days: int) -> pd.DataFrame:
    t = politicians.trades(con, since=(date.today() - timedelta(days=days)).isoformat())
    if t.empty:
        return pd.DataFrame()
    t = t[t.ticker.notna() & t.asset_type.isin(["action", "option"])]
    t = t.assign(ticker=t.ticker.replace(ALIASES))
    buy = t.action == "achat"
    sell = t.action.str.startswith("vente")
    g = pd.DataFrame({
        "cg_buyers": t[buy].groupby("ticker").politician_id.nunique(),
        "cg_sel_buyers": t[buy & (t.followed == 1)].groupby("ticker").politician_id.nunique(),
        "cg_sellers": t[sell].groupby("ticker").politician_id.nunique(),
        "cg_bought": t[buy].groupby("ticker").amount_mid.sum(),
        "cg_who": t[buy].groupby("ticker").name.agg(lambda s: ", ".join(sorted(set(s)))),
        "cg_sel_who": t[buy & (t.followed == 1)].groupby("ticker").name.agg(lambda s: ", ".join(sorted(set(s)))),
        "cg_name": t.groupby("ticker").asset.first(),
    })
    return g


def _fund_signals(con: sqlite3.Connection) -> pd.DataFrame:
    perf = investors.performance(con)
    good = set(perf[perf.excess > 0].cik) if not perf.empty else set()
    rows = []
    for cik, name in con.execute("SELECT cik, name FROM investors WHERE active = 1").fetchall():
        m, _ = investors.portfolio(con, cik)
        if m.empty:
            continue
        m = m[(m.put_call == "") & m.ticker.notna()]
        for r in m.itertuples():
            rows.append({"ticker": r.ticker, "fund": name, "good": cik in good, "change": r.change,
                         "weight": r.weight, "issuer": r.issuer})
    if not rows:
        return pd.DataFrame()
    d = pd.DataFrame(rows)
    d["ticker"] = d.ticker.replace(ALIASES)
    buy = d.change.isin(["nouvelle", "renforcée"])
    sell = d.change.isin(["allégée", "vendue"])
    held = d.change != "vendue"
    return pd.DataFrame({
        "fd_buyers": d[buy].groupby("ticker").fund.nunique(),
        "fd_good_buyers": d[buy & d.good].groupby("ticker").fund.nunique(),
        "fd_sellers": d[sell].groupby("ticker").fund.nunique(),
        "fd_holders": d[held].groupby("ticker").fund.nunique(),
        "fd_max_weight": d[held].groupby("ticker").weight.max(),
        "fd_who": d[buy].groupby("ticker").fund.agg(lambda s: ", ".join(sorted(set(s)))),
        "fd_name": d.groupby("ticker").issuer.first(),
    })


def clean_name(names: pd.Series) -> pd.Series:
    """Company names as disclosed ("NVIDIA Corporation - Common Stock (NVDA)") without the share class noise."""
    return (names.astype("string").str.replace(r"\s*-?\s*(Class [A-Z] )?(Common|Ordinary) (Stock|Shares).*$", "",
                                               regex=True, case=False)
            .str.replace(r"\s*\(.*$", "", regex=True).str.strip())


def _pct(x: float) -> str:
    return f"{x:+.0%}".replace(".", ",")


def build(con: sqlite3.Connection, days: int = 90, keep: int = 40) -> pd.DataFrame:
    """Compute and store the radar (a few minutes: prices and analyst data from Yahoo)."""
    import yfinance as yf

    from .prices import closes

    con.executescript(SCHEMA)
    s = _congress_signals(con, days).join(_fund_signals(con), how="outer")
    if s.empty:
        return s
    num = [c for c in s.columns if not c.endswith(("who", "name"))]
    s[num] = s[num].fillna(0.0)
    s["base"] = (3 * s.cg_sel_buyers + (s.cg_buyers - s.cg_sel_buyers) - 0.5 * s.cg_sellers
                 + 2 * s.fd_good_buyers + (s.fd_buyers - s.fd_good_buyers) - 0.5 * s.fd_sellers + 0.3 * s.fd_holders)
    s = s[s.base > 0].sort_values("base", ascending=False).head(keep * 2)
    s = s[~s.index.str.contains(r"[^A-Z.\-]", regex=True)]  # US tickers only

    px = closes(list(s.index) + ["SPY"], date.today() - timedelta(days=380))
    today = px.index[-1] if not px.empty else pd.Timestamp.today()

    def ret(t: str, days_back: int) -> float | None:
        if t not in px or px[t].dropna().empty:
            return None
        c = px[t].dropna()
        past = c[c.index <= today - pd.Timedelta(days=days_back)]
        return float(c.iloc[-1] / past.iloc[-1] - 1) if len(past) else None

    for col, n in (("r1m", 30), ("r3m", 91), ("r6m", 182), ("r1y", 365)):
        s[col] = [ret(t, n) for t in s.index]
    s["from_high"] = [float(px[t].dropna().iloc[-1] / px[t].dropna().max() - 1)
                      if t in px and not px[t].dropna().empty else None for t in s.index]
    spy3 = ret("SPY", 91) or 0.0
    s["trend"] = [(1 if (r3 or 0) > spy3 else -0.5 if r3 is not None and r3 < -0.15 else 0)
                  + (0.5 if fh is not None and fh > -0.1 else 0) for r3, fh in zip(s.r3m, s.from_high)]
    s["score"] = s.base + s.trend
    s = s.sort_values("score", ascending=False).head(keep)

    info_cols = {"shortName": "name", "sector": "sector", "industry": "industry", "recommendationMean": "rating",
                 "recommendationKey": "rating_key", "targetMeanPrice": "target", "currentPrice": "price",
                 "numberOfAnalystOpinions": "analysts", "marketCap": "market_cap"}
    infos = []
    for t in s.index:
        try:
            i = yf.Ticker(t.replace(".", "-")).info
        except Exception:  # noqa: BLE001
            i = {}
        infos.append({v: i.get(k) for k, v in info_cols.items()})
    s = s.join(pd.DataFrame(infos, index=s.index))
    s["upside"] = [(tg / p - 1) if tg and p else None for tg, p in zip(s.target, s.price)]
    s["score"] += [(1 if r and r <= 2 else 0) + (0.5 if u and u > 0.15 else 0) for r, u in zip(s.rating, s.upside)]

    mine = exposure(con)
    s["mine_eur"] = [mine.get(t, {}).get("eur", 0.0) for t in s.index]
    s["mine_via"] = [", ".join(mine.get(t, {}).get("via", [])) for t in s.index]
    s["name"] = s.name.fillna(clean_name(s.fd_name.fillna(s.cg_name)))
    s["why"] = [_why(r) for r in s.itertuples()]
    s = s.sort_values("score", ascending=False)
    con.execute("DELETE FROM radar")
    con.executemany("INSERT INTO radar VALUES (?, ?)",
                    [(t, json.dumps({k: (None if isinstance(v, float) and v != v else v) for k, v in row.items()},
                                    default=str)) for t, row in s.reset_index(names="ticker").set_index("ticker")
                     .to_dict("index").items()])
    db.set_meta(con, "radar_at", db.now_iso())
    con.commit()
    return load(con)


def _why(r) -> str:
    parts = []
    if r.cg_sel_buyers:
        parts.append(f"achat d'élus suivis ({r.cg_sel_who})")
    elif r.cg_buyers:
        parts.append(f"{int(r.cg_buyers)} élu(s) achètent")
    if r.fd_buyers:
        names = (r.fd_who or "").split(", ")
        who = ", ".join(names[:4]) + (f" et {len(names) - 4} autres" if len(names) > 4 else "")
        parts.append(f"{int(r.fd_buyers)} fonds achètent ou renforcent ({who})")
    if r.fd_holders and not r.fd_buyers:
        parts.append(f"détenu par {int(r.fd_holders)} fonds suivis")
    if r.r3m is not None:
        parts.append(f"{_pct(r.r3m)} sur 3 mois")
    if r.rating:
        parts.append(f"analystes {r.rating:.1f}/5".replace(".", ",") + (f", objectif {_pct(r.upside)}" if r.upside else ""))
    if r.cg_sellers or r.fd_sellers:
        parts.append(f"mais {int(r.cg_sellers + r.fd_sellers)} vendeur(s)")
    return " · ".join(parts)


def load(con: sqlite3.Connection) -> pd.DataFrame:
    con.executescript(SCHEMA)
    rows = [dict(json.loads(d), ticker=t) for t, d in con.execute("SELECT ticker, data FROM radar")]
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)


def selling(con: sqlite3.Connection, days: int = 90) -> pd.DataFrame:
    """What the followed money is getting out of: sellers minus buyers, members and funds together."""
    s = _congress_signals(con, days).join(_fund_signals(con), how="outer")
    if s.empty:
        return s
    num = [c for c in s.columns if not c.endswith(("who", "name"))]
    s[num] = s[num].fillna(0.0)
    s["net"] = (s.cg_sellers + s.fd_sellers) - (s.cg_buyers + s.fd_buyers)
    s["name"] = clean_name(s.fd_name.fillna(s.cg_name))
    return s[s.net >= 2].sort_values("net", ascending=False).reset_index(names="ticker")


def detail(con: sqlite3.Connection, ticker: str) -> dict:
    """Everything followed money did on one stock: members' trades (2 years) and the funds' latest lines."""
    alias = {k for k, v in ALIASES.items() if v == ticker} | {ticker}
    t = politicians.trades(con, since=(date.today() - timedelta(days=730)).isoformat())
    t = t[t.ticker.isin(alias)] if not t.empty else t
    rows = []
    for cik, name in con.execute("SELECT cik, name FROM investors WHERE active = 1").fetchall():
        m, meta = investors.portfolio(con, cik)
        if m.empty:
            continue
        hit = m[m.ticker.isin(alias) & (m.put_call == "")]
        for r in hit.itertuples():
            rows.append({"fund": name, "manager": meta.get("manager"), "period": meta.get("period"), "change": r.change,
                         "weight": r.weight, "weight_prev": r.weight_prev, "value_usd": r.value_usd,
                         "shares_change": r.shares_change})
    funds = pd.DataFrame(rows)
    return {"trades": t, "funds": funds.sort_values("weight", ascending=False) if not funds.empty else funds}
