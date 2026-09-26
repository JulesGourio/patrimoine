"""Form 13F holdings of well-known investors, from SEC EDGAR (public, free, needs a contact User-Agent).

A 13F lists the US-listed long positions (and listed options) of managers above $100M, as of each quarter
end, filed up to 45 days later: it is a delayed, partial view (no shorts, no cash, no non-US shares).
Values are in dollars (since 2023).
"""
from __future__ import annotations

import re
import sqlite3
import time
from xml.etree.ElementTree import ParseError

import defusedxml.ElementTree as ET
from typing import Any

import requests

from .. import db

HEADERS = {"User-Agent": "Patrimoine perso ju.gourio@gmail.com"}
SEC = "https://data.sec.gov"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data"

# Default list: varied styles (value, macro, activist, tech growth, deep value).
INVESTORS = [
    (1067983, "Berkshire Hathaway", "Warren Buffett", "value, long terme"),
    (1536411, "Duquesne Family Office", "Stanley Druckenmiller", "macro, tech"),
    (1336528, "Pershing Square", "Bill Ackman", "concentré, activiste"),
    (1656456, "Appaloosa", "David Tepper", "opportuniste"),
    (1709323, "Himalaya Capital", "Li Lu", "value, Asie"),
    (1061768, "Baupost Group", "Seth Klarman", "deep value"),
    (1040273, "Third Point", "Dan Loeb", "événementiel, activiste"),
    (1167483, "Tiger Global", "Chase Coleman", "croissance tech"),
    (1135730, "Coatue", "Philippe Laffont", "croissance tech"),
    (1061165, "Lone Pine", "Stephen Mandel", "croissance qualité"),
    (1697748, "ARK Invest", "Cathie Wood", "innovation disruptive"),
    (1350694, "Bridgewater", "Ray Dalio", "macro, très diversifié"),
    (1649339, "Scion Asset Management", "Michael Burry", "contrarian (ne dépose plus depuis fin 2025)"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS investors (
    cik INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    manager TEXT,
    style TEXT,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS f13_filings (
    accession TEXT PRIMARY KEY,
    cik INTEGER NOT NULL REFERENCES investors(cik),
    period TEXT NOT NULL,               -- quarter end the holdings are as of
    filed TEXT NOT NULL,
    form TEXT NOT NULL,                 -- 13F-HR or 13F-HR/A
    total_usd REAL,
    positions INTEGER
);
CREATE TABLE IF NOT EXISTS f13_holdings (
    accession TEXT NOT NULL REFERENCES f13_filings(accession),
    cusip TEXT NOT NULL,
    issuer TEXT,
    title TEXT,
    put_call TEXT NOT NULL DEFAULT '',  -- '' for shares, PUT / CALL for options
    value_usd REAL NOT NULL,
    shares REAL,
    PRIMARY KEY (accession, cusip, put_call)
);
CREATE TABLE IF NOT EXISTS cusip_map (
    cusip TEXT PRIMARY KEY,
    ticker TEXT,
    name TEXT
);
"""


def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.executemany("INSERT OR IGNORE INTO investors (cik, name, manager, style) VALUES (?, ?, ?, ?)", INVESTORS)
    con.commit()


def get(url: str, **kw: Any) -> requests.Response:
    time.sleep(0.12)  # SEC fair access: at most 10 requests per second
    r = requests.get(url, headers=HEADERS, timeout=60, **kw)
    r.raise_for_status()
    return r


def filings(cik: int, limit: int = 8) -> list[dict]:
    """Latest 13F-HR filings (amendments that restate the whole table included), newest first."""
    rec = get(f"{SEC}/submissions/CIK{cik:010d}.json").json()["filings"]["recent"]
    out = []
    for i, form in enumerate(rec["form"]):
        if form in ("13F-HR", "13F-HR/A"):
            out.append({"accession": rec["accessionNumber"][i], "period": rec["reportDate"][i],
                        "filed": rec["filingDate"][i], "form": form, "primary": rec["primaryDocument"][i]})
    return out[:limit]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def holdings(cik: int, accession: str) -> list[dict]:
    """Rows of the filing's information table, merged per (CUSIP, put/call)."""
    folder = f"{ARCHIVES}/{cik}/{accession.replace('-', '')}"
    items = get(f"{folder}/index.json").json()["directory"]["item"]
    xmls = [i["name"] for i in items if i["name"].lower().endswith(".xml") and i["name"] != "primary_doc.xml"]
    rows: dict[tuple[str, str], dict] = {}
    for name in xmls:
        root = ET.fromstring(get(f"{folder}/{name}").content)
        for info in root.iter():
            if _local(info.tag) != "infoTable":
                continue
            f = {_local(c.tag): c for c in info}
            amt = {_local(c.tag): c.text for c in f["shrsOrPrnAmt"]} if "shrsOrPrnAmt" in f else {}
            key = ((f["cusip"].text or "").strip().upper(), (f["putCall"].text or "").upper() if "putCall" in f else "")
            row = rows.setdefault(key, {"cusip": key[0], "put_call": key[1], "issuer": f["nameOfIssuer"].text,
                                        "title": f["titleOfClass"].text if "titleOfClass" in f else None,
                                        "value_usd": 0.0, "shares": 0.0})
            row["value_usd"] += float(f["value"].text or 0)
            row["shares"] += float(amt.get("sshPrnamt") or 0)
    out = list(rows.values())
    # Some filers still report values in thousands of dollars: a median price per share under $1 gives it away.
    per_share = sorted(r["value_usd"] / r["shares"] for r in out if r["shares"] and not r["put_call"])
    if per_share and per_share[len(per_share) // 2] < 1:
        for r in out:
            r["value_usd"] *= 1000
    return out


def sync(con: sqlite3.Connection, per_investor: int = 6) -> list[dict]:
    """Fetch the filings we do not have yet. Returns the new ones (for notifications)."""
    init(con)
    known = {r[0] for r in con.execute("SELECT accession FROM f13_filings")}
    new = []
    for cik, name in con.execute("SELECT cik, name FROM investors WHERE active = 1").fetchall():
        try:
            fl = filings(cik, per_investor)
        except requests.RequestException:
            continue
        for f in reversed(fl):
            if f["accession"] in known:
                continue
            try:
                rows = holdings(cik, f["accession"])
            except (requests.RequestException, ParseError, KeyError):
                continue
            total = sum(r["value_usd"] for r in rows)
            con.execute("INSERT OR REPLACE INTO f13_filings VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f["accession"], cik, f["period"], f["filed"], f["form"], total, len(rows)))
            con.executemany(
                "INSERT OR REPLACE INTO f13_holdings VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(f["accession"], r["cusip"], r["issuer"], r["title"], r["put_call"], r["value_usd"], r["shares"])
                 for r in rows])
            con.commit()
            new.append({"cik": cik, "name": name, **f, "total_usd": total, "positions": len(rows)})
    db.set_meta(con, "last_13f_check", db.now_iso())
    con.commit()
    return new


def map_cusips(con: sqlite3.Connection, cusips: list[str]) -> None:
    """CUSIP -> ticker through OpenFIGI (free, 10 ids per request without a key); cached forever."""
    have = {r[0] for r in con.execute("SELECT cusip FROM cusip_map")}
    todo = [c for c in dict.fromkeys(cusips) if c not in have]
    for i in range(0, len(todo), 10):
        batch = todo[i:i + 10]
        try:
            r = requests.post("https://api.openfigi.com/v3/mapping", timeout=30,
                              json=[{"idType": "ID_CUSIP", "idValue": c, "exchCode": "US"} for c in batch])
            if r.status_code == 429:
                time.sleep(7)
                continue
            answers = r.json()
        except (requests.RequestException, ValueError):
            break
        for c, a in zip(batch, answers):
            data = (a or {}).get("data") or [{}]
            con.execute("INSERT OR REPLACE INTO cusip_map VALUES (?, ?, ?)",
                        (c, data[0].get("ticker"), data[0].get("name")))
        con.commit()
        time.sleep(2.5)  # 25 requests per minute without a key


def search(name: str) -> list[dict]:
    """Find a 13F filer's CIK by name, through EDGAR full-text company search."""
    r = get("https://efts.sec.gov/LATEST/search-index", params={"keysTyped": name, "forms": "13F-HR"})
    hits = r.json().get("hits", {}).get("hits", [])
    out = []
    for h in hits[:10]:
        src = h.get("_source", {})
        cik = re.sub(r"\D", "", str(h.get("_id", "")))
        out.append({"cik": int(cik) if cik else None, "name": src.get("entity") or src.get("display_names")})
    return out
