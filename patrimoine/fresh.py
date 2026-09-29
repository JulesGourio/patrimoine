"""What the followed money did since its last 13F, from the fast filings (see sources.ownership).

- fund_moves: the followed funds' Form 4 and Schedule 13D/13G, each compared with the previous known stake (the
  previous filing on that company, or the latest 13F line), plus ARK's daily ETF trades;
- current_positions: a fund's latest 13F, updated with those filings (an estimate: only the lines a filing
  touched move, the others are as of the quarter end);
- insider_signals: open-market purchases and sales by the officers and directors of the watched companies;
- feed: all of it, with the new 13F and members of Congress, in one list sorted by publication date.
Every row says how old it is and how the price moved since, so an idea already in the price shows.
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta

import pandas as pd

from . import db, investors
from .sources import ownership

FORM_LABEL = {"4": "Form 4", "4/A": "Form 4", "SCHEDULE 13D": "13D", "SCHEDULE 13D/A": "13D",
              "SCHEDULE 13G": "13G", "SCHEDULE 13G/A": "13G"}
ALIASES = {"GOOG": "GOOGL", "BRK.A": "BRK.B", "BRK-B": "BRK.B", "FOX": "FOXA", "NWS": "NWSA", "LBTYK": "LBTYA"}
INSIDER_MIN_USD = 25_000  # below that, a purchase is an employee plan or a token gesture


def _norm(t: str | None) -> str | None:
    """US ticker as the radar writes it (BRK.B), or None for what is not one (foreign codes, '2618', 'GRMN UN')."""
    if not isinstance(t, str) or not t:
        return None
    t = t.strip().upper().replace("-", ".").replace("/", ".")
    if not re.fullmatch(r"[A-Z]{1,5}(\.[A-Z])?", t):
        return None
    return ALIASES.get(t, t)


def _closes(tickers: list[str], start) -> pd.DataFrame:
    from .prices import closes

    tickers = sorted({t for t in tickers if t})
    return closes(tickers, start) if tickers else pd.DataFrame()


def _since(px: pd.DataFrame, ticker: str | None, start) -> float | None:
    from .prices import change

    if not ticker or px.empty or start is None or pd.isna(start):
        return None
    return change(px, ticker, start)


def _close_on(px: pd.DataFrame, ticker: str | None, day) -> float | None:
    if not ticker or ticker not in px:
        return None
    s = px[ticker].dropna()
    s = s[s.index <= pd.Timestamp(day)] if day else s
    return float(s.iloc[-1]) if len(s) else None


# ---------- the followed funds ----------

def _last_13f(con: sqlite3.Connection) -> dict[int, pd.DataFrame]:
    f = investors._filings(con)
    out = {}
    for cik, g in f.groupby("cik"):
        h = investors._holdings(con, g.iloc[-1].accession)
        out[int(cik)] = h[h.put_call == ""].assign(period=g.iloc[-1].period)
    return out


def fund_moves(con: sqlite3.Connection, days: int = 120, prices: bool = True) -> pd.DataFrame:
    """Form 4 and 13D/13G of the followed funds filed in the last ``days``, newest first, with the change against
    the previous known stake and the price change since the event."""
    ownership.init(con)
    since = (date.today() - timedelta(days=days)).isoformat()
    f = pd.read_sql_query("SELECT o.*, i.name, i.manager FROM own_filings o JOIN investors i USING (cik)"
                          " WHERE i.active = 1 ORDER BY o.filed, o.accession", con)
    if f.empty:
        return f
    # An original and its amendment filed together: keep the last.
    f = f.drop_duplicates(["cik", "issuer_cik", "filed"], keep="last")
    f["kind"] = f.form.map(FORM_LABEL)
    f["ticker"] = f.ticker.map(_norm)
    last13 = _last_13f(con)
    rows = []
    prev_stake: dict[tuple, float] = {}
    for r in f.itertuples():
        key = (r.cik, r.issuer_cik or r.ticker)
        before = prev_stake.get(key)
        source = "déclaration précédente"
        if before is None:
            h = last13.get(r.cik)
            if h is not None and not h.empty:
                cusip = r.cusip if isinstance(r.cusip, str) else ""
                hit = h[h.cusip.str[:6] == cusip[:6]] if cusip else h.iloc[0:0]
                if hit.empty and r.ticker:
                    hit = h[h.ticker.map(_norm) == r.ticker]
                if not hit.empty:
                    before, source = float(hit.shares.sum()), f"13F au {hit.period.iloc[0]}"
        if r.kind == "Form 4":
            delta = r.bought
            action = "achat" if (r.bought or 0) > 0 else "vente"
        else:
            delta = (r.shares - before) if (r.shares is not None and before is not None) else None
            if before is None:
                action = "nouvelle participation" if (r.pct or 0) >= 5 else "participation déclarée"
            elif r.shares is not None and r.shares > before * 1.02:
                action = "renforcée"
            elif r.shares is not None and r.shares < before * 0.98:
                action = "allégée" if (r.pct or 0) >= 5 else "passée sous 5 %"
            else:
                action = "inchangée"
        if r.shares is not None:
            prev_stake[key] = r.shares
        rows.append({"accession": r.accession, "filed": r.filed, "event_date": r.event_date or r.filed, "cik": r.cik,
                     "fund": r.name,
                     "manager": r.manager, "kind": r.kind, "form": r.form, "ticker": r.ticker, "issuer": r.issuer,
                     "action": action, "shares": r.shares, "delta": delta, "before": before, "before_source": source,
                     "pct": r.pct, "value_usd": r.value_usd, "price": r.price, "url": r.url})
    m = pd.DataFrame(rows)
    m = m[m.filed >= since].copy()
    if m.empty:
        return m
    if prices:
        px = _closes(list(m.ticker.dropna()), min(m.event_date))
        m["since"] = [_since(px, t, d) for t, d in zip(m.ticker, m.event_date)]
        # 13D/G have no price: value the change at the close of the event day.
        m["value_usd"] = [v if pd.notna(v) else (d * p if d is not None and pd.notna(d) and p else None)
                          for v, d, p in zip(m.value_usd, m.delta, [_close_on(px, t, e) for t, e in
                                                                  zip(m.ticker, m.event_date)])]
    m["age"] = (pd.Timestamp.today().normalize() - pd.to_datetime(m.filed)).dt.days
    return m.sort_values(["filed", "event_date"], ascending=False).reset_index(drop=True)


def ark_moves(con: sqlite3.Connection, days: int = 30, min_usd: float = 1e6) -> pd.DataFrame:
    """ARK's daily ETF trades over the stored days (all ETFs of a day summed per stock)."""
    ownership.init(con)
    stored = [r[0] for r in con.execute("SELECT DISTINCT date FROM ark_holdings WHERE date >= ? ORDER BY date",
                                        ((date.today() - timedelta(days=days)).isoformat(),))]
    rows = [t for d in stored[1:] for t in ownership.ark_trades(con, d)]
    if not rows:
        return pd.DataFrame()
    t = pd.DataFrame(rows)
    g = t.groupby(["date", "ticker"], as_index=False).agg(
        company=("company", "first"), delta=("delta", "sum"), value_usd=("value_usd", "sum"),
        etfs=("fund", lambda s: ", ".join(sorted(set(s)))), change=("change", "first"))
    g["action"] = g.delta.map(lambda d: "achat" if d > 0 else "vente")
    g["ticker"] = g.ticker.map(_norm)
    return g[g.value_usd.abs() >= min_usd].sort_values(["date", "value_usd"], ascending=[False, False])


def current_positions(con: sqlite3.Connection, cik: int) -> tuple[pd.DataFrame, dict]:
    """The fund's latest 13F stock lines, with each line's shares and value brought up to date by the filings
    made since the quarter end (ARK: its ETFs' holdings of the last stored day)."""
    m, meta = investors.portfolio(con, cik)
    if m.empty:
        return m, meta
    base = m[(m.put_call == "") & (m.change != "vendue")][["cusip", "issuer", "ticker", "shares", "value_usd",
                                                             "weight"]].copy()
    base["ticker"] = base.ticker.map(_norm)
    base = base.rename(columns={"shares": "shares_13f", "value_usd": "value_13f", "weight": "weight_13f"})
    base["shares_now"], base["source"], base["as_of"] = base.shares_13f, "13F", meta["period"]
    extra = []
    if cik == ownership.ARK_CIK:
        ark = ownership.ark_holdings(con)
        if not ark.empty and ark.date.iloc[0] > meta["filed"]:
            ark["ticker"] = ark.ticker.map(_norm)
            idx = {c[:6]: i for i, c in zip(base.index, base.cusip)}
            base["shares_now"], base["source"], base["as_of"] = 0.0, "ETF ARK", ark.date.iloc[0]
            for r in ark.itertuples():
                i = idx.get(r.cusip[:6])
                if i is not None:
                    base.at[i, "shares_now"] = base.at[i, "shares_now"] + r.shares
                else:
                    extra.append({"cusip": r.cusip, "issuer": r.company, "ticker": r.ticker, "shares_13f": 0.0,
                                  "value_13f": 0.0, "weight_13f": 0.0, "shares_now": r.shares, "source": "ETF ARK",
                                  "as_of": r.date})
            meta["note"] = ("Positions des ETF d'ARK du jour : ils représentent l'essentiel mais pas la totalité de "
                            "ce qu'ARK déclare dans son 13F (mandats et fonds non cotés en plus).")
    moves = fund_moves(con, days=400, prices=False)
    moves = moves[(moves.cik == cik) & (moves.event_date > meta["period"]) & moves.shares.notna()] \
        if not moves.empty else moves
    for r in moves.sort_values("event_date").itertuples():
        hit = base.index[base.ticker == r.ticker] if r.ticker else []
        if len(hit):
            i = hit[0]
            if r.event_date <= str(base.at[i, "as_of"]):  # ARK's daily holdings are newer
                continue
            base.at[i, "shares_now"], base.at[i, "source"], base.at[i, "as_of"] = r.shares, r.kind, r.event_date
        else:
            same = [e for e in extra if e["ticker"] == r.ticker]
            if same:
                same[0].update(shares_now=r.shares, source=r.kind, as_of=r.event_date)
            else:
                extra.append({"cusip": None, "issuer": r.issuer, "ticker": r.ticker, "shares_13f": 0.0,
                              "value_13f": 0.0, "weight_13f": 0.0, "shares_now": r.shares, "source": r.kind,
                              "as_of": r.event_date})
    p = pd.concat([base, pd.DataFrame(extra)], ignore_index=True) if extra else base
    px = _closes(list(p.ticker.dropna()) + ["SPY"], meta["period"])
    last = {t: _close_on(px, t, None) for t in p.ticker.dropna().unique()}
    unit = (p.value_13f / p.shares_13f.where(p.shares_13f > 0))
    p["price_now"] = p.ticker.map(last)
    p["since_13f"] = [_since(px, t, meta["period"]) for t in p.ticker]
    # Value today: shares now at the last close; a line without a price keeps its 13F price per share.
    p["value_now"] = p.shares_now * p.price_now.fillna(unit)
    p["value_now"] = p.value_now.fillna(p.value_13f)
    p["weight_now"] = p.value_now / p.value_now.sum()
    p["moved"] = p.source != "13F"
    meta["spy_since"] = _since(px, "SPY", meta["period"])
    meta["updated_lines"] = int(p.moved.sum())
    meta["last_update"] = p.as_of.max()
    return p[p.shares_now > 0].sort_values("value_now", ascending=False).reset_index(drop=True), meta


# ---------- insiders ----------

def insider_trades(con: sqlite3.Connection, days: int = 90, ticker: str | None = None) -> pd.DataFrame:
    ownership.init(con)
    q = "SELECT * FROM insider_trades WHERE tx_date >= ?"
    params: list = [(date.today() - timedelta(days=days)).isoformat()]
    if ticker:
        q += " AND ticker = ?"
        params.append(ticker)
    t = pd.read_sql_query(q + " ORDER BY tx_date DESC", con, params=params)
    if t.empty:
        return t
    px = _closes(list(t.ticker.unique()), t.tx_date.min())
    t["price"] = [_close_on(px, k, d) for k, d in zip(t.ticker, t.tx_date)]
    t["value_usd"] = t.shares * t.price
    t["since"] = [_since(px, k, d) for k, d in zip(t.ticker, t.tx_date)]
    t["ticker"] = t.ticker.map(_norm)
    # Many insiders buying the same day is an employee plan (TSMC), not conviction.
    per_day = t[t.action == "achat"].groupby(["ticker", "tx_date"]).owner.nunique()
    plan = set(per_day[per_day >= 5].index)
    t["plan"] = [(k, d) in plan and a == "achat" for k, d, a in zip(t.ticker, t.tx_date, t.action)]
    # Funds above 10 % are followed through their own filings (fund_moves), not as insiders.
    t["holder"] = t.role.fillna("").str.fullmatch(r"10 percent owner")
    return t[~t.plan]


def insider_days(t: pd.DataFrame) -> pd.DataFrame:
    """One row per company, day and side: who, how much in total."""
    if t.empty:
        return t
    return t.groupby(["ticker", "tx_date", "action"], as_index=False).agg(
        value_usd=("value_usd", "sum"), owners=("owner", "nunique"),
        who=("owner", lambda s: ", ".join(o.title() for o in dict.fromkeys(s))),
        role=("role", lambda s: ", ".join(dict.fromkeys(_role(r) for r in s))), since=("since", "first"),
        holder=("holder", "all")).sort_values(["tx_date", "value_usd"], ascending=False)


def insider_signals(con: sqlite3.Connection, days: int = 90, trades: pd.DataFrame | None = None) -> pd.DataFrame:
    """Per ticker: how many insiders bought on the market (at least 25 k$ each), for how much, and who; sellers."""
    t = insider_trades(con, days) if trades is None else trades
    if t.empty:
        return pd.DataFrame()
    per = t.groupby(["ticker", "owner", "action"], as_index=False).agg(
        value_usd=("value_usd", "sum"), role=("role", "first"), last=("tx_date", "max"))
    per = per[~per.role.fillna("").str.fullmatch(r"10 percent owner")]
    buy = per[(per.action == "achat") & (per.value_usd >= INSIDER_MIN_USD)]
    sell = per[per.action == "vente"]

    def who(g: pd.DataFrame) -> str:
        return ", ".join(f"{o.title()} ({_role(r)})" for o, r in zip(g.owner, g.role))

    out = pd.DataFrame({
        "in_buyers": buy.groupby("ticker").owner.nunique(),
        "in_bought": buy.groupby("ticker").value_usd.sum(),
        "in_who": buy.groupby("ticker")[["owner", "role"]].apply(who),
        "in_last_buy": buy.groupby("ticker")["last"].max(),
        "in_sellers": sell.groupby("ticker").owner.nunique(),
        "in_sold": sell.groupby("ticker").value_usd.sum(),
    })
    return out


def _role(role: str | None) -> str:
    r = role if isinstance(role, str) else ""
    if "officer:" in r:
        title = r.split("officer:", 1)[1].split(",")[0].strip()
        return title if title.lower() not in ("see remarks", "please see remarks") else "dirigeant"
    if "director" in r:
        return "administrateur"
    return "actionnaire > 10 %" if "10 percent" in r else r or "?"


# ---------- the watch list for the insiders ----------

def watchlist(con: sqlite3.Connection, limit: int = 120) -> list[str]:
    """US stocks whose insiders are worth watching: Jules's exposure (direct and through his ETFs' top lines), the
    radar, the followed funds' fresh filings, and the stocks held by at least three followed funds."""
    from . import radar

    tickers: list[str] = []
    tickers += list((db.get_meta(con, "exposure") or {}).keys())
    r = radar.load(con)
    if not r.empty:
        tickers += list(r.ticker)
    m = fund_moves(con, days=120, prices=False)
    if not m.empty:
        tickers += list(m.ticker.dropna())
    c = investors.consensus(con, 3)
    if not c.empty:
        tickers += list(c.ticker.dropna().head(40))
    out = [t for t in dict.fromkeys(_norm(t) for t in tickers) if t and t.replace(".", "").isalpha()]
    return out[:limit]


# ---------- the feed ----------

def feed(con: sqlite3.Connection, days: int = 30) -> pd.DataFrame:
    """Everything the followed money published in the last ``days``, newest first: date (publication), kind,
    who, ticker, name, what (in words), value_usd, since (price change since the operation), link, mine (Jules
    holds it, directly or through his ETFs), followed (a followed fund or member of Congress)."""
    from . import politicians

    since = (date.today() - timedelta(days=days)).isoformat()
    mine = db.get_meta(con, "exposure") or {}
    rows = []

    for r in fund_moves(con, days).itertuples():
        if r.action == "inchangée":
            continue
        what = r.action
        if r.kind == "Form 4" and pd.notna(r.value_usd):
            what += f" de {_usd(abs(r.value_usd))}" + (f" à {r.price:,.2f} $".replace(",", " ").replace(".", ",")
                                                       if pd.notna(r.price) else "")
        elif r.pct is not None and pd.notna(r.pct):
            what += f" · {r.pct:.1f} % de la société".replace(".", ",")
            if r.delta is not None and pd.notna(r.delta) and r.before:
                what += f" ({r.delta / r.before:+.0%} vs {r.before_source})".replace(".", ",")
        rows.append({"date": r.filed, "op_date": r.event_date, "kind": r.kind, "who": r.fund, "ticker": r.ticker,
                     "name": r.issuer, "what": what, "value_usd": r.value_usd, "since": getattr(r, "since", None),
                     "link": r.url, "followed": True})

    a = ark_moves(con, days)
    if not a.empty:
        px = _closes(list(a.ticker.dropna()), a.date.min())
        for r in a.itertuples():
            rows.append({"date": r.date, "op_date": r.date, "kind": "ARK (jour)", "who": "ARK Invest",
                         "ticker": r.ticker, "name": r.company,
                         "what": f"{r.change} ({r.etfs}) · {_usd(abs(r.value_usd))}", "value_usd": r.value_usd,
                         "since": _since(px, r.ticker, r.date), "link": None, "followed": True})

    f = investors._filings(con)
    f = f[f.filed >= since] if not f.empty else f
    for r in f.itertuples():
        m, _ = investors.portfolio(con, r.cik)
        m = m[m.put_call == ""]
        mv = m[m.change.isin(["nouvelle", "vendue"])]
        top = ", ".join(f"{x.ticker or x.issuer} ({x.change})" for x in
                        mv.assign(v=mv[["value_usd", "value_usd_prev"]].max(axis=1))
                        .sort_values("v", ascending=False).head(4).itertuples())
        rows.append({"date": r.filed, "op_date": r.period, "kind": "13F", "who": r.name, "ticker": None,
                     "name": f"{len(m[m.change != 'vendue'])} lignes au {r.period}",
                     "what": f"{(m.change == 'nouvelle').sum()} nouvelles, {(m.change == 'vendue').sum()} vendues"
                             + (f" : {top}" if top else ""), "value_usd": r.total_usd, "since": None,
                     "link": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={r.cik}&type=13F",
                     "followed": True})

    t = politicians.trades(con, since=(date.today() - timedelta(days=days + 120)).isoformat())
    if not t.empty:
        t = t[(t.filed >= since) & t.asset_type.isin(["action", "option"])]
        t = t.assign(ticker=t.ticker.map(_norm))
        keep = (t.followed == 1) | (t.amount_min >= 250_000) | (t.ticker.isin(list(mine)) & (t.amount_min >= 50_000))
        for r in t[keep].itertuples():
            amount = (f"{_usd(r.amount_min)}–{_usd(r.amount_max)}" if pd.notna(r.amount_max)
                      else f"plus de {_usd(r.amount_min)}")
            rows.append({"date": r.filed, "op_date": r.tx_date, "kind": "Élu", "who": r.name, "ticker": r.ticker,
                         "name": r.asset, "what": f"{r.action}{' (option)' if r.asset_type == 'option' else ''}"
                                                  f" · {amount} · déclaré {int(r.delay_days)} j après"
                         if pd.notna(r.delay_days) else f"{r.action} · {amount}",
                         "value_usd": r.amount_mid, "since": r.ret, "link": None, "followed": bool(r.followed)})

    it = insider_days(insider_trades(con, days))
    if not it.empty:
        it = it[~it.holder]  # 10 % holders: the funds' own Form 4 rows say it already
        it = it[((it.action == "achat") & (it.value_usd >= 100_000)) |
                ((it.action == "vente") & (it.value_usd >= 5_000_000) & it.ticker.isin(list(mine)))]
        for r in it.itertuples():
            n = f"{r.owners} dirigeants" if r.owners > 1 else r.who
            rows.append({"date": r.tx_date, "op_date": r.tx_date, "kind": "Dirigeants", "who": n,
                         "ticker": r.ticker, "name": r.role if r.owners == 1 else r.who,
                         "what": f"{r.action} de {_usd(r.value_usd)} sur le marché", "value_usd": r.value_usd,
                         "since": r.since, "link": None, "followed": False})

    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows)
    out["mine"] = out.ticker.isin(list(mine))
    out["mine_eur"] = out.ticker.map(lambda k: (mine.get(k) or {}).get("eur", 0.0) if k else 0.0)
    out["age"] = (pd.Timestamp.today().normalize() - pd.to_datetime(out.date)).dt.days
    return out.sort_values(["date", "value_usd"], ascending=[False, False], na_position="last").reset_index(drop=True)


def _usd(x: float | None) -> str:
    if x is None or pd.isna(x):
        return "?"
    x = float(x)
    if x >= 1e9:
        return f"{x / 1e9:.1f} Md$".replace(".", ",")
    return f"{x / 1e6:.1f} M$".replace(".", ",") if x >= 1e6 else f"{x / 1e3:.0f} k$"


# ---------- how old each source is ----------

def sources_status(con: sqlite3.Connection) -> pd.DataFrame:
    """Per source: the date of its latest information, how many days old that is, and the legal delay."""
    ownership.init(con)
    today = pd.Timestamp.today().normalize()

    def one(sql: str, params: tuple = ()) -> str | None:
        row = con.execute(sql, params).fetchone()
        return row[0] if row and row[0] else None

    rows = []
    period = one("SELECT MAX(period) FROM f13_filings f JOIN investors i USING (cik) WHERE i.active = 1")
    filed = one("SELECT MAX(filed) FROM f13_filings f JOIN investors i USING (cik) WHERE i.active = 1")
    rows.append({"source": "13F des fonds", "latest": period, "published": filed,
                 "rule": "trimestriel, jusqu'à 45 jours après la fin du trimestre",
                 "covers": "tout le portefeuille coté aux États-Unis"})
    for label, forms, rule, covers in (
            ("Form 4 des fonds", ("4", "4/A"), "2 jours ouvrés", "sociétés dont le fonds a plus de 10 %"),
            ("13D / 13G des fonds", ("SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A"),
             "13D : 5 jours ouvrés ; 13G : 45 jours après le trimestre", "participations de plus de 5 %")):
        q = ",".join("?" * len(forms))
        rows.append({"source": label, "latest": one(f"SELECT MAX(event_date) FROM own_filings WHERE form IN ({q})",
                                                    forms),
                     "published": one(f"SELECT MAX(filed) FROM own_filings WHERE form IN ({q})", forms),
                     "rule": rule, "covers": covers})
    ark = one("SELECT MAX(date) FROM ark_holdings")
    rows.append({"source": "ETF d'ARK", "latest": ark, "published": ark, "rule": "chaque jour de bourse",
                 "covers": "toutes les lignes des 6 ETF d'ARK"})
    ins = one("SELECT MAX(tx_date) FROM insider_trades")
    rows.append({"source": "Dirigeants (Form 4)", "latest": ins, "published": ins, "rule": "2 jours ouvrés",
                 "covers": "achats et ventes des dirigeants des titres surveillés"})
    cg = one("SELECT MAX(tx_date) FROM congress_trades WHERE tx_date <= filed")
    cgf = one("SELECT MAX(filed) FROM congress_trades")
    rows.append({"source": "Élus du Congrès", "latest": cg, "published": cgf, "rule": "45 jours après l'opération",
                 "covers": "comptes des élus et de leur famille"})
    d = pd.DataFrame(rows)
    d["age"] = [(today - pd.Timestamp(x)).days if x else None for x in d.latest]
    d["checked"] = [db.get_meta(con, k) for k in ("last_13f_check", "last_ownership_check", "last_ownership_check",
                                                   "last_ownership_check", "last_insider_check",
                                                   "last_congress_check")]
    return d
