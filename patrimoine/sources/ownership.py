"""Fresh ownership filings, to see what the followed money did after its last 13F (days, not months, old).

- Form 4 (within 2 business days): trades of officers, directors and owners of more than 10 % of a company. The
  followed funds file them when they own more than 10 % (Berkshire on Occidental, Lennar...). Filed Form 4 give
  the price and the shares owned after the trade.
- Schedule 13D / 13G (13D within 5 business days of crossing 5 %, 13G up to 45 days after the quarter for passive
  holders): the stake of a fund in one company, with its share of the company. XML since December 2024.
- Insiders of the watched companies (Jules's lines, the radar): EDGAR's per-company table of Form 4 transactions,
  one request per company. Open-market purchases (code P) are the signal; sales (S) are often planned (10b5-1)
  or tax driven, and grants and option exercises are left out.
- ARK Invest: holdings of its ETFs, published every day; the daily changes are its trades.
Everything is public and free (SEC fair access: at most 10 requests per second, a contact User-Agent).
"""
from __future__ import annotations

import csv
import io
import logging
import re
import sqlite3
from datetime import date, datetime, timedelta
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
import pandas as pd
import requests

from .. import db
from . import sec13f

log = logging.getLogger(__name__)

FORMS_4 = ("4", "4/A")
FORMS_13 = ("SCHEDULE 13D", "SCHEDULE 13D/A", "SCHEDULE 13G", "SCHEDULE 13G/A")
ARK_CIK = 1697748
ARK_BASE = "https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
ARK_ETFS = {
    "ARKK": "ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKW": "ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    "ARKG": "ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    "ARKQ": "ARK_AUTONOMOUS_TECH._&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
    "ARKF": "ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
    "ARKX": "ARK_SPACE_&_DEFENSE_INNOVATION_ETF_ARKX_HOLDINGS.csv",
}
CODES = {"P": "achat", "S": "vente"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS own_filings (
    accession TEXT PRIMARY KEY,
    cik INTEGER NOT NULL,               -- the followed investor (investors.cik)
    form TEXT NOT NULL,                 -- 4, SCHEDULE 13D, SCHEDULE 13G (and /A)
    filed TEXT NOT NULL,
    event_date TEXT,                    -- trade date (Form 4) or date of the event that required the filing
    issuer_cik INTEGER,
    issuer TEXT,
    ticker TEXT,
    cusip TEXT,
    shares REAL,                        -- held after the filing's last trade (Form 4) or aggregate owned (13D/G)
    pct REAL,                           -- share of the company (13D/G), in %
    bought REAL,                        -- Form 4: shares bought (P) minus sold (S) in the filing
    value_usd REAL,                     -- Form 4: amount of those trades at their prices
    price REAL,                         -- Form 4: average price of the trades
    url TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS own_filings_cik ON own_filings (cik, filed);
CREATE TABLE IF NOT EXISTS insider_trades (
    id TEXT PRIMARY KEY,
    ticker TEXT NOT NULL,
    issuer_cik INTEGER NOT NULL,
    owner TEXT NOT NULL,
    role TEXT,                          -- director, officer: CFO, 10 percent owner...
    tx_date TEXT NOT NULL,
    action TEXT NOT NULL,               -- achat (open-market purchase, P) / vente (S)
    shares REAL NOT NULL,
    owned_after REAL,
    security TEXT
);
CREATE INDEX IF NOT EXISTS insider_trades_ticker ON insider_trades (ticker, tx_date);
CREATE TABLE IF NOT EXISTS ark_holdings (
    date TEXT NOT NULL,
    fund TEXT NOT NULL,
    cusip TEXT NOT NULL,
    ticker TEXT,
    company TEXT,
    shares REAL NOT NULL,
    value_usd REAL,
    PRIMARY KEY (date, fund, cusip)
);
CREATE TABLE IF NOT EXISTS investor_aliases (
    alias_cik INTEGER PRIMARY KEY,      -- another filer whose reports now carry the investor's holdings
    cik INTEGER NOT NULL
);
"""


def init(con: sqlite3.Connection) -> None:
    sec13f.init(con)
    con.executescript(SCHEMA)
    con.commit()


def _num(x: str | None) -> float | None:
    try:
        return float(str(x).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _day(s: str | None) -> str | None:
    """ISO date from 2026-09-23 or 09/23/2026."""
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date().isoformat()
        except ValueError:
            continue
    return None


# ---------- parsers (pure, tested) ----------

def parse_form4(xml: bytes) -> dict:
    """Issuer, open-market trades (P/S) and the shares owned after the last one, from a Form 4 XML."""
    root = ET.fromstring(xml)

    def text(el, path: str) -> str | None:
        node = el.find(path)
        return node.text.strip() if node is not None and node.text else None

    out = {"issuer_cik": int(_num(text(root, "issuer/issuerCik")) or 0) or None,
           "issuer": text(root, "issuer/issuerName"),
           "ticker": re.split(r"[,;/\s]+", (text(root, "issuer/issuerTradingSymbol") or "").upper())[0] or None,
           "trades": []}
    # Holdings after the trades: the last figure of each (security, ownership nature), summed per security; the
    # main security (most shares) is kept, not class A plus class B.
    after: dict[tuple, float] = {}
    for tx in root.iter("nonDerivativeTransaction"):
        code = text(tx, "transactionCoding/transactionCode")
        shares = _num(text(tx, "transactionAmounts/transactionShares/value")) or 0.0
        owned = _num(text(tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"))
        key = (text(tx, "securityTitle/value"), text(tx, "ownershipNature/directOrIndirectOwnership/value"),
               text(tx, "ownershipNature/natureOfOwnership/value"))
        if owned is not None:
            after[key] = owned
        if code not in CODES:
            continue
        out["trades"].append({"date": _day(text(tx, "transactionDate/value")), "action": CODES[code], "shares": shares,
                              "price": _num(text(tx, "transactionAmounts/transactionPricePerShare/value"))})
    per_security: dict[str | None, float] = {}
    for (security, *_), owned in after.items():
        per_security[security] = per_security.get(security, 0.0) + owned
    out["shares"] = max(per_security.values()) if per_security else None
    return out


def parse_schedule13(xml: bytes) -> dict:
    """Issuer, CUSIP, aggregate shares and % of the class from a Schedule 13D or 13G XML (the largest reported
    person: the group total)."""
    root = ET.fromstring(xml)
    vals: dict[str, list[str]] = {}
    for el in root.iter():
        if el.text and el.text.strip():
            vals.setdefault(_local(el.tag), []).append(el.text.strip())

    def first(*tags: str) -> str | None:
        return next((vals[t][0] for t in tags if t in vals), None)

    def most(*tags: str) -> float | None:
        nums = [n for t in tags for n in map(_num, vals.get(t, [])) if n is not None]
        return max(nums) if nums else None

    cik = _num(first("issuerCIK", "issuerCik"))
    return {"issuer": first("issuerName"), "issuer_cik": int(cik) if cik else None,
            "cusip": (first("issuerCusipNumber") or "").upper() or None,
            "event_date": _day(first("dateOfEvent", "eventDateRequiresFilingThisStatement")),
            "shares": most("aggregateAmountOwned", "reportingPersonBeneficiallyOwnedAggregateNumberOfShares"),
            "pct": most("percentOfClass", "classPercent")}


def parse_ark_csv(text: str) -> list[dict]:
    rows = []
    for r in csv.DictReader(io.StringIO(text)):
        day, cusip = _day(r.get("date")), (r.get("cusip") or "").strip().upper()
        shares = _num(r.get("shares"))
        if not day or not cusip or shares is None:
            continue
        rows.append({"date": day, "fund": (r.get("fund") or "").strip(), "cusip": cusip,
                     "ticker": (r.get("ticker") or "").strip().upper() or None, "company": (r.get("company") or "").strip(),
                     "shares": shares, "value_usd": _num((r.get("market value ($)") or "").replace("$", ""))})
    return rows


def parse_insider_table(html: str, ticker: str, issuer_cik: int) -> list[dict]:
    """Open-market purchases and sales from EDGAR's per-company table of insider transactions. Joint filers (a
    fund and its manager) report the same line: kept once."""
    try:
        tables = pd.read_html(io.StringIO(html), match="Transaction Type", flavor="lxml")
    except ValueError:  # no insider transaction
        return []
    try:
        owners = pd.read_html(io.StringIO(html), match="Type of Owner", flavor="lxml")
    except ValueError:
        owners = []
    roles = {}
    for t in owners:
        if t.shape[1] != 4:  # the layout tables around it match too
            continue
        t = t.iloc[1:] if str(t.iloc[0, 0]) == "Owner" else t
        roles.update({str(r[0]): str(r[3]) for r in t.itertuples(index=False)})
    t = max(tables, key=len)
    t.columns = [str(c) for c in t.columns]
    out, seen = [], set()
    for r in t.to_dict("records"):
        code = str(r.get("Transaction Type") or "")[:1]
        if code not in CODES or str(r.get("Form")) not in FORMS_4:
            continue
        day, shares = _day(str(r.get("Transaction Date"))), _num(r.get("Number of Securities Transacted"))
        if not day or not shares:
            continue
        owned = _num(r.get("Number of Securities Owned"))
        key = (day, r.get("Line Number"), shares, owned, r.get("Security Name"))
        if key in seen:
            continue
        seen.add(key)
        owner = str(r.get("Reporting Owner"))
        out.append({"id": f"{ticker}:{day}:{owner}:{r.get('Line Number')}:{shares:.0f}", "ticker": ticker,
                    "issuer_cik": issuer_cik, "owner": owner, "role": roles.get(owner), "tx_date": day,
                    "action": CODES[code], "shares": shares, "owned_after": owned,
                    "security": r.get("Security Name")})
    return out


# ---------- the followed funds' own filings ----------

def _raw_url(cik: int, accession: str, primary: str) -> str:
    """The raw XML behind EDGAR's rendered view (xslF345X06/form4.xml -> form4.xml)."""
    return f"{sec13f.ARCHIVES}/{cik}/{accession.replace('-', '')}/{primary.rsplit('/', 1)[-1]}"


def ciks(con: sqlite3.Connection, cik: int) -> list[int]:
    return [cik] + [r[0] for r in con.execute("SELECT alias_cik FROM investor_aliases WHERE cik = ?", (cik,))]


def find_successor(con: sqlite3.Connection, cik: int, rec: dict) -> int | None:
    """A 13F-NT (notice) means another manager now reports the holdings: follow it (Pershing Square Capital
    Management -> Pershing Square Inc. since mid-2026)."""
    for i, form in enumerate(rec["form"]):
        if form != "13F-NT":
            continue
        url = f"{sec13f.ARCHIVES}/{cik}/{rec['accessionNumber'][i].replace('-', '')}/primary_doc.xml"
        try:
            root = ET.fromstring(sec13f.get(url).content)
        except (requests.RequestException, ParseError):
            return None
        other = next((el for el in root.iter() if _local(el.tag) == "otherManager"), None)
        if other is None:
            return None
        alias = next((int(c.text) for c in other if _local(c.tag) == "cik" and c.text), None)
        if alias and alias != cik:
            con.execute("INSERT OR IGNORE INTO investor_aliases VALUES (?, ?)", (alias, cik))
            con.commit()
        return alias
    return None


def sync_funds(con: sqlite3.Connection, since: str | None = None) -> list[dict]:
    """New Form 4 and Schedule 13D/G of the active followed investors (and their aliases). Returns them."""
    init(con)
    since = since or (date.today() - timedelta(days=400)).isoformat()
    known = {r[0] for r in con.execute("SELECT accession FROM own_filings")}
    new = []
    for cik, name in con.execute("SELECT cik, name FROM investors WHERE active = 1").fetchall():
        for filer in ciks(con, cik):
            try:
                rec = sec13f.get(f"{sec13f.SEC}/submissions/CIK{filer:010d}.json").json()["filings"]["recent"]
            except (requests.RequestException, ValueError, KeyError):
                continue
            if filer == cik:
                find_successor(con, cik, rec)
            for i, form in enumerate(rec["form"]):
                acc, filed = rec["accessionNumber"][i], rec["filingDate"][i]
                if form not in FORMS_4 + FORMS_13 or filed < since or acc in known:
                    continue
                url = _raw_url(filer, acc, rec["primaryDocument"][i])
                try:
                    xml = sec13f.get(url).content
                    row = _filing_row(form, xml)
                except (requests.RequestException, ParseError, KeyError, ValueError) as e:
                    log.warning("%s %s: %s", name, acc, e)
                    continue
                if row is None or row.get("issuer_cik") in (filer, cik):  # nothing traded, or its own shares
                    known.add(acc)
                    continue
                row.update(accession=acc, cik=cik, form=form, filed=filed, url=url)
                con.execute("INSERT OR REPLACE INTO own_filings (accession, cik, form, filed, event_date, issuer_cik,"
                            " issuer, ticker, cusip, shares, pct, bought, value_usd, price, url) VALUES (:accession,"
                            " :cik, :form, :filed, :event_date, :issuer_cik, :issuer, :ticker, :cusip, :shares, :pct,"
                            " :bought, :value_usd, :price, :url)", row)
                con.commit()
                known.add(acc)
                new.append({**row, "name": name})
    _fill_tickers(con)
    return new


def _filing_row(form: str, xml: bytes) -> dict | None:
    if form in FORMS_4:
        f = parse_form4(xml)
        if not f["trades"]:
            return None  # grants, exercises, gifts: not a market move
        signed = [(t["shares"] if t["action"] == "achat" else -t["shares"], t["price"]) for t in f["trades"]]
        priced = [(s, p) for s, p in signed if p]
        value = sum(s * p for s, p in priced) if priced else None
        vol = sum(abs(s) for s, _ in priced)
        return {"event_date": max(t["date"] for t in f["trades"] if t["date"]), "issuer_cik": f["issuer_cik"],
                "issuer": f["issuer"], "ticker": f["ticker"], "cusip": None, "shares": f["shares"], "pct": None,
                "bought": sum(s for s, _ in signed), "value_usd": value,
                "price": sum(abs(s) * p for s, p in priced) / vol if vol else None}
    s = parse_schedule13(xml)
    return {**s, "ticker": None, "bought": None, "value_usd": None, "price": None}


# ---------- company tickers ----------

def sec_tickers(con: sqlite3.Connection) -> dict[str, int]:
    """{ticker: company CIK} from the SEC's list, refreshed once a week."""
    cached = db.get_meta(con, "sec_tickers")
    if cached and cached.get("at", "") >= (date.today() - timedelta(days=7)).isoformat():
        return cached["map"]
    try:
        data = sec13f.get("https://www.sec.gov/files/company_tickers.json").json()
    except (requests.RequestException, ValueError):
        return (cached or {}).get("map", {})
    m = {v["ticker"].upper(): int(v["cik_str"]) for v in data.values()}
    db.set_meta(con, "sec_tickers", {"at": date.today().isoformat(), "map": m})
    con.commit()
    return m


def _fill_tickers(con: sqlite3.Connection) -> None:
    """13D/G carry the company's CIK, not its ticker."""
    rows = con.execute("SELECT DISTINCT issuer_cik FROM own_filings WHERE ticker IS NULL AND issuer_cik IS NOT NULL"
                       ).fetchall()
    if not rows:
        return
    by_cik: dict[int, str] = {}
    for t, c in sec_tickers(con).items():
        if c not in by_cik or len(t) < len(by_cik[c]):  # the plain share class (GOOGL over GOOGL-like variants)
            by_cik[c] = t
    for (c,) in rows:
        if c in by_cik:
            con.execute("UPDATE own_filings SET ticker = ? WHERE issuer_cik = ? AND ticker IS NULL", (by_cik[c], c))
    con.commit()


# ---------- insiders of watched companies ----------

def sync_insiders(con: sqlite3.Connection, tickers: list[str]) -> list[dict]:
    """Open-market trades of the insiders of ``tickers`` (US companies filing with the SEC). Returns new ones."""
    init(con)
    cik_of = sec_tickers(con)
    known = {r[0] for r in con.execute("SELECT id FROM insider_trades")}
    new = []
    for t in dict.fromkeys(x.upper().replace(".", "-") for x in tickers if x):
        cik = cik_of.get(t) or cik_of.get(t.replace("-", "."))
        if not cik:
            continue
        try:
            html = sec13f.get("https://www.sec.gov/cgi-bin/own-disp",
                              params={"action": "getissuer", "CIK": f"{cik:010d}"}).text
        except requests.RequestException as e:
            log.warning("insiders %s: %s", t, e)
            continue
        rows = [r for r in parse_insider_table(html, t.replace("-", "."), cik) if r["id"] not in known]
        con.executemany("INSERT OR IGNORE INTO insider_trades VALUES (:id, :ticker, :issuer_cik, :owner, :role,"
                        " :tx_date, :action, :shares, :owned_after, :security)", rows)
        con.commit()
        known.update(r["id"] for r in rows)
        new += rows
    db.set_meta(con, "last_insider_check", db.now_iso())
    con.commit()
    return new


# ---------- ARK daily holdings ----------

def sync_ark(con: sqlite3.Connection) -> list[dict]:
    """Today's holdings of ARK's ETFs; returns the trades against the previous stored day (shares changed by more
    than 1 %, lines added or removed), fund by fund."""
    init(con)
    got = []
    for etf, name in ARK_ETFS.items():
        try:
            r = requests.get(ARK_BASE + name, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
            r.raise_for_status()
        except requests.RequestException as e:
            log.warning("ARK %s: %s", etf, e)
            continue
        got += parse_ark_csv(r.text)
    if not got:
        return []
    day = max(x["date"] for x in got)
    seen = con.execute("SELECT 1 FROM ark_holdings WHERE date = ? LIMIT 1", (day,)).fetchone()
    con.executemany("INSERT OR REPLACE INTO ark_holdings VALUES (:date, :fund, :cusip, :ticker, :company, :shares,"
                    " :value_usd)", [x for x in got if x["date"] == day])
    con.commit()
    return [] if seen else ark_trades(con, day)  # weekends and holidays: same file as the day before


def ark_trades(con: sqlite3.Connection, day: str | None = None) -> list[dict]:
    """Changes between ``day`` (the latest by default) and the stored day before, per ETF and stock."""
    days = [r[0] for r in con.execute("SELECT DISTINCT date FROM ark_holdings ORDER BY date DESC LIMIT 60")]
    if day:
        days = [d for d in days if d <= day]
    if len(days) < 2:
        return []
    h = pd.read_sql_query("SELECT * FROM ark_holdings WHERE date IN (?, ?)", con, params=(days[0], days[1]))
    cur, prev = h[h.date == days[0]], h[h.date == days[1]]
    m = cur.merge(prev, on=["fund", "cusip"], how="outer", suffixes=("", "_prev"))
    m[["shares", "shares_prev"]] = m[["shares", "shares_prev"]].fillna(0.0)
    m["ticker"] = m.ticker.fillna(m.ticker_prev)
    m["company"] = m.company.fillna(m.company_prev)
    px = (m.value_usd / m.shares.where(m.shares > 0)).fillna(m.value_usd_prev / m.shares_prev.where(m.shares_prev > 0))
    m["delta"] = m.shares - m.shares_prev
    m["value_usd"] = m.delta * px
    moved = m[(m.delta.abs() > 0.01 * m[["shares", "shares_prev"]].max(axis=1))]
    out = []
    for r in moved.itertuples():
        kind = "nouvelle" if not r.shares_prev else "vendue" if not r.shares else "renforcée" if r.delta > 0 else "allégée"
        out.append({"date": days[0], "since": days[1], "fund": r.fund, "ticker": r.ticker, "company": r.company,
                    "cusip": r.cusip, "change": kind, "shares": r.shares, "delta": r.delta,
                    "value_usd": None if pd.isna(r.value_usd) else float(r.value_usd)})
    return out


def ark_holdings(con: sqlite3.Connection) -> pd.DataFrame:
    """ARK's latest daily holdings, all ETFs together, per stock."""
    init(con)
    h = pd.read_sql_query("SELECT * FROM ark_holdings WHERE date = (SELECT MAX(date) FROM ark_holdings)", con)
    if h.empty:
        return h
    return h.groupby("cusip", as_index=False).agg(date=("date", "first"), ticker=("ticker", "first"),
                                                  company=("company", "first"), shares=("shares", "sum"),
                                                  value_usd=("value_usd", "sum"))


# ---------- everything, for the daily sync ----------

def sync(con: sqlite3.Connection, watch: list[str]) -> dict:
    res = {"funds": [], "insiders": [], "ark": [], "errors": []}
    for key, step in (("funds", lambda: sync_funds(con)), ("ark", lambda: sync_ark(con)),
                      ("insiders", lambda: sync_insiders(con, watch))):
        try:
            res[key] = step()
        except Exception as e:  # noqa: BLE001 - one source down must not stop the others
            log.exception("ownership %s", key)
            res["errors"].append(f"{key} : {e}")
    db.set_meta(con, "last_ownership_check", db.now_iso())
    con.commit()
    return res


def cusip_ticker(con: sqlite3.Connection, cusip: str | None) -> str | None:
    if not cusip:
        return None
    row = con.execute("SELECT ticker FROM cusip_map WHERE ticker IS NOT NULL AND (cusip = ? OR substr(cusip, 1, 6) = ?)"
                      " ORDER BY cusip = ? DESC LIMIT 1", (cusip, cusip[:6], cusip)).fetchone()
    return row[0] if row else None

