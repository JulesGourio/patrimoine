"""What US members of Congress buy and sell, and how their picks did (see sources.congress).

Performance is an estimate: each disclosed purchase of a listed stock (or of options, judged on the underlying
stock) is valued from the close of its trade date to the last close, next to the S&P 500 over the same days, and
weighted by the middle of its disclosed amount range. Sales are listed, not scored. It says whether a member's
picks beat the index, not what their account earned.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pandas as pd

from .sources import congress

CHAMBERS = {"house": "Chambre", "senate": "Sénat"}


def trades(con: sqlite3.Connection, pid: str | None = None, since: str | None = None) -> pd.DataFrame:
    """Every trade, amendments folded (the same trade filed twice is kept once), newest first."""
    congress.init(con)
    q = ("SELECT t.*, p.name, p.chamber, p.state, p.followed FROM congress_trades t JOIN politicians p"
         " ON p.id = t.politician_id WHERE 1 = 1")
    params: list = []
    if pid:
        q += " AND t.politician_id = ?"
        params.append(pid)
    if since:
        q += " AND COALESCE(t.tx_date, t.filed) >= ?"
        params.append(since)
    df = pd.read_sql_query(q, con, params=params)
    if df.empty:
        return df
    df = df.sort_values("filed").drop_duplicates(
        ["politician_id", "ticker", "asset", "tx_date", "action", "amount_min", "owner"], keep="last")
    df["amount_mid"] = df.amount_min.where(df.amount_max.isna(), (df.amount_min + df.amount_max) / 2)
    df["excess"] = df.ret - df.bench_ret
    df["delay_days"] = (pd.to_datetime(df.filed) - pd.to_datetime(df.tx_date)).dt.days
    df["chamber_label"] = df.chamber.map(CHAMBERS)
    return df.sort_values(["filed", "tx_date"], ascending=False)


def ranking(con: sqlite3.Connection, months: int = 24, min_buys: int = 10) -> pd.DataFrame:
    """Members ranked by how much their stock purchases beat the S&P 500 (amount-weighted), last ``months``."""
    since = (date.today() - timedelta(days=int(months * 30.5))).isoformat()
    t = trades(con, since=since)
    if t.empty:
        return t
    rows = []
    for pid, g in t.groupby("politician_id"):
        buys = g[(g.action == "achat") & g.ret.notna() & g.asset_type.isin(["action", "option"])]
        w = buys.amount_mid.fillna(1000.0)
        rows.append({
            "id": pid, "name": g.name.iloc[0], "chamber": g.chamber_label.iloc[0], "state": g.state.iloc[0],
            "followed": bool(g.followed.iloc[0]), "trades": len(g), "buys": len(buys),
            "sales": int(g.action.str.startswith("vente").sum()),
            "volume": float(g.amount_mid.fillna(0).sum()),
            "ret": float((buys.ret * w).sum() / w.sum()) if len(buys) else None,
            "excess": float((buys.excess * w).sum() / w.sum()) if len(buys) and buys.excess.notna().any() else None,
            "hit_rate": float((buys.excess > 0).mean()) if len(buys) else None,
            "options": float((g.asset_type == "option").mean()),
            # The STOCK Act gives 45 days; later than that, what you see is even older.
            "late": float((g.delay_days > 45).mean()) if g.delay_days.notna().any() else None,
            "delay": float(g.delay_days.median()) if g.delay_days.notna().any() else None,
            "last_trade": g.tx_date.max(), "last_filed": g.filed.max(),
            "top": ", ".join(buys.groupby("ticker").amount_mid.sum().sort_values(ascending=False).head(4).index),
        })
    r = pd.DataFrame(rows)
    ranked = r[r.buys >= min_buys].sort_values("excess", ascending=False)
    rest = r[(r.buys < min_buys) & r.followed]  # followed members stay visible even with few trades
    return pd.concat([ranked, rest], ignore_index=True)


def recent(con: sqlite3.Connection, days: int = 60, followed_only: bool = False) -> pd.DataFrame:
    """Trades filed in the last ``days``."""
    t = trades(con, since=(date.today() - timedelta(days=days + 45)).isoformat())
    if t.empty:
        return t
    t = t[t.filed >= (date.today() - timedelta(days=days)).isoformat()]
    return t[t.followed == 1] if followed_only else t


def consensus(con: sqlite3.Connection, days: int = 90, min_members: int = 2) -> pd.DataFrame:
    """Stocks several members traded in the last ``days`` (trade date): who buys, who sells, estimated amounts."""
    t = trades(con, since=(date.today() - timedelta(days=days)).isoformat())
    if t.empty:
        return t
    t = t[t.ticker.notna() & t.asset_type.isin(["action", "option"])]
    t = t.assign(side=t.action.map(lambda a: "achat" if a == "achat" else "vente" if a.startswith("vente") else None))
    t = t[t.side.notna()]
    g = t.groupby("ticker").agg(
        asset=("asset", "first"), members=("politician_id", "nunique"),
        buyers=("politician_id", lambda s: s[t.loc[s.index, "side"] == "achat"].nunique()),
        sellers=("politician_id", lambda s: s[t.loc[s.index, "side"] == "vente"].nunique()),
        bought=("amount_mid", lambda s: s[t.loc[s.index, "side"] == "achat"].sum()),
        sold=("amount_mid", lambda s: s[t.loc[s.index, "side"] == "vente"].sum()),
        who=("name", lambda s: ", ".join(sorted(set(s)))), last=("tx_date", "max"))
    g = g[g.members >= min_members]
    g["net"] = g.buyers - g.sellers
    return g.sort_values(["buyers", "bought"], ascending=False).reset_index()


def find(con: sqlite3.Connection, name: str) -> list[dict]:
    """Members whose name contains ``name`` (accents and case ignored)."""
    from .categories import normalize

    congress.init(con)
    key = normalize(name).strip()
    return [dict(r) for r in con.execute("SELECT id, name, chamber, state, followed FROM politicians")
            if key in normalize(r["name"])]


def auto_follow(con: sqlite3.Connection, months: int = 24, top: int = 10) -> list[str]:
    """The selection: Pelosi, plus the members whose purchases beat the S&P 500 by 5 points or more with at least
    15 of them, 40 % winners and a filing in the last
    6 months (the best ``top``), then Jules's own choices on top. Returns the followed names."""
    from . import db

    r = ranking(con, months, min_buys=15)
    active = (date.today() - timedelta(days=180)).isoformat()  # still filing: gone members drop out
    good = r[(r.buys >= 15) & (r.excess >= 0.05) & (r.hit_rate >= 0.40) & (r.last_filed >= active)].head(top)         if not r.empty else r
    always = {congress.politician_id(c, last, first) for c, last, first in congress.FOLLOWED}
    manual = db.get_meta(con, "congress_follow_manual") or {}
    chosen = (set(good.id) if not good.empty else set()) | always | {k for k, v in manual.items() if v}
    chosen -= {k for k, v in manual.items() if not v}
    con.execute("UPDATE politicians SET followed = 0")
    con.executemany("UPDATE politicians SET followed = 1 WHERE id = ?", [(i,) for i in chosen])
    con.commit()
    return [r[0] for r in con.execute("SELECT name FROM politicians WHERE followed = 1 ORDER BY name")]
