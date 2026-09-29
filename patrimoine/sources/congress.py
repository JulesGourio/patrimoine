"""Stock trades of US members of Congress, from their official STOCK Act disclosures (public, free).

- House: the Clerk publishes a yearly index of filings (``{year}FD.zip``); each Periodic Transaction Report
  (type ``P``) is a PDF, parsed from its text. Handwritten scans have no text and are only listed.
- Senate: efdsearch.senate.gov, behind an agreement page and a bot shield that only lets browsers through
  (curl_cffi impersonates Chrome's TLS). Electronic reports are HTML tables; paper ones are images.

Trades are disclosed up to 45 days after the fact, as amount ranges ($1,001 - $15,000…), and often belong to
the spouse: a late, coarse view, useful to spot convictions, not to copy in real time.
"""
from __future__ import annotations

import html
import io
import logging
import re
import sqlite3
import time
import zipfile
from datetime import date, datetime, timedelta

import requests

from .. import db

log = logging.getLogger(__name__)

HOUSE = "https://disclosures-clerk.house.gov/public_disc"
SENATE = "https://efdsearch.senate.gov"
HEADERS = {"User-Agent": "Mozilla/5.0 (Patrimoine perso; ju.gourio@gmail.com)"}
FIRST_YEAR = 2025  # history fetched on the first run

# Always in the selection: the most copied member (the "Pelosi tracker"). The rest of the selection is made
# from the data each day: see politicians.auto_follow. (chamber, last name, first name)
FOLLOWED = [
    ("house", "Pelosi", "Nancy"),
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS politicians (
    id TEXT PRIMARY KEY,                -- chamber:LAST FIRST
    chamber TEXT NOT NULL,              -- house / senate
    name TEXT NOT NULL,
    state TEXT,
    followed INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS congress_reports (
    id TEXT PRIMARY KEY,                -- House DocID or Senate report uuid
    chamber TEXT NOT NULL,
    politician_id TEXT NOT NULL REFERENCES politicians(id),
    filed TEXT NOT NULL,
    url TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- electronic / paper
    trades INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS congress_trades (
    id TEXT PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES congress_reports(id),
    politician_id TEXT NOT NULL REFERENCES politicians(id),
    owner TEXT,                         -- Moi, Conjoint, Commun, Enfant
    ticker TEXT,
    asset TEXT NOT NULL,
    asset_type TEXT,                    -- action, option, obligation, fonds, autre
    action TEXT NOT NULL,               -- achat, vente, vente partielle, échange
    tx_date TEXT,
    filed TEXT NOT NULL,
    amount_min REAL,
    amount_max REAL,
    comment TEXT,
    ret REAL,                           -- price change from the trade date to the last close
    bench_ret REAL,                     -- same period for the S&P 500
    price_as_of TEXT
);
CREATE INDEX IF NOT EXISTS congress_trades_pol ON congress_trades (politician_id, tx_date);
"""

OWNERS = {"SP": "Conjoint", "JT": "Commun", "DC": "Enfant", "Self": "Moi", "Spouse": "Conjoint",
          "Joint": "Commun", "Child": "Enfant", "Dependent Child": "Enfant"}
HOUSE_TYPES = {"ST": "action", "OP": "option", "GS": "obligation", "CS": "obligation", "MF": "fonds", "EF": "fonds",
               "OT": "autre"}


def init(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA)
    con.commit()


def _last(last: str) -> str:
    """Family name without what follows a comma or a generational suffix: "McConnell, Jr." -> "McConnell"."""
    last = last.split(",")[0].strip()
    return re.sub(r"\s+(Jr|Sr|II|III|IV)\.?$", "", last, flags=re.I).strip()


def _given(first: str) -> str:
    """First real given name: "A. Mitchell" -> "Mitchell", "Thomas H" -> "Thomas"."""
    tokens = [t for t in first.split(",")[0].replace(".", ". ").split() if t]
    return next((t for t in tokens if len(t) > 2 and not t.endswith(".")), tokens[0] if tokens else "")


def politician_id(chamber: str, last: str, first: str) -> str:
    return f"{chamber}:{_last(last).upper()} {_given(first).upper()}"


def _ensure_politician(con: sqlite3.Connection, chamber: str, last: str, first: str, state: str | None) -> str:
    pid = politician_id(chamber, last, first)
    given, family = _given(first), _last(last)
    if given.isupper() or given.islower():
        given = given.title()
    if family.isupper() or family.islower():
        family = family.title()
    # Followed by default: matched on the chamber and family name ("Ro" and "Rohit" Khanna are the same member).
    followed = any(c == chamber and _last(l).upper() == family.upper() for c, l, _ in FOLLOWED)
    con.execute("INSERT INTO politicians (id, chamber, name, state, followed) VALUES (?, ?, ?, ?, ?)"
                " ON CONFLICT(id) DO UPDATE SET state = COALESCE(excluded.state, state), name = excluded.name",
                (pid, chamber, f"{given} {family}", state, int(followed)))
    return pid


def _amount(text: str) -> tuple[float | None, float | None]:
    nums = [float(n.replace(",", "")) for n in re.findall(r"\$([\d,]+)", text)]
    if not nums:
        return None, None
    if text.strip().lower().startswith("over"):
        return nums[0], None
    return nums[0], nums[-1]


def _day(mdy: str) -> str | None:
    try:
        return datetime.strptime(mdy.strip(), "%m/%d/%Y").date().isoformat()
    except ValueError:
        return None


def _trade_id(report_id: str, n: int) -> str:
    return f"{report_id}#{n}"


# ---------- House ----------

ANCHOR = re.compile(
    r"\[(?P<atype>[A-Z]{2})\]\s+(?P<tx>P|S\s*\(partial\)|S|E)\s+(?P<d1>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<d2>\d{1,2}/\d{1,2}/\d{4})\s+(?P<amt>Over\s+\$[\d,]+|\$[\d,]+(?:\s*-\s*\$[\d,]+)?)")
HEADER = re.compile(r"ID Owner Asset Transaction\s*\nType\s*\nDate Notification\s*\nDate\s*\nAmount Cap\.\s*\n"
                    r"Gains >\s*\n\$200\?\s*\n")
BROKEN = re.compile(r"\s(P|S \(partial\)|S|E)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
                    r"(Over \$[\d,]+|\$[\d,]+(?:\s*-\s*\$[\d,]+)?)\n+([^\[\]\n]*?)\s*\[([A-Z]{2})\]")
BROKEN_AMOUNT = re.compile(r"\s(P|S \(partial\)|S|E)\s+(\d{1,2}/\d{1,2}/\d{4})\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
                           r"(\$[\d,]+)\s*-\n+([^\[\]\n]*?)\s*\[([A-Z]{2})\]\s*(\$[\d,]+)")
# The PDFs drop most letters of their field labels ("F S: New" for "Filing Status: New"): a run of single
# capitals then a colon.
LABEL_LINE = re.compile(r"^[A-Z](?:\s+[A-Z])*\s*:\s*(?P<text>.*)$")
NOISE = re.compile(r"^(ID Owner Asset Transaction|Type|Date Notification|Date|Amount Cap\.|Gains >|\$200\?|"
                   r"Filing ID #\d+|\* For the complete list.*|Asset Owner Transaction.*)$")


def parse_house_pdf(text: str) -> list[dict]:
    """Transactions of one House PTR, from the PDF text."""
    text = text.replace("\x00", "")  # the dropped letters of the field labels come out as NUL characters
    # Each page repeats the column headers; keep the first one only (it marks where the first trade starts).
    parts = HEADER.split(text)
    if len(parts) > 2:
        text = parts[0] + "$200?\n" + "\n".join(parts[1:])
    # A trade cut by a page break puts its type, dates and amount before the end of its asset name:
    # "CrowdStrike - Class A P 08/07/2026 09/04/2026 $1,001 - $15,000\nCommon Stock (CRWD) [ST]".
    text = BROKEN_AMOUNT.sub(r" \5 [\6]\n\1 \2 \3 \4 - \7", text)  # "... $15,001 -" / "... (LAMR) [ST] $50,000"
    text = BROKEN.sub(r" \5 [\6]\n\1 \2 \3 \4", text)
    trades: list[dict] = []
    matches = list(ANCHOR.finditer(text))
    prev_end = 0
    for i, m in enumerate(matches):
        segment = text[prev_end:m.start()]
        if i == 0 and "$200?" in segment:
            segment = segment[segment.rindex("$200?") + 5:]
        asset_lines, comment = [], []
        for line in segment.splitlines():
            line = line.strip()
            if not line or NOISE.match(line):
                continue
            lab = LABEL_LINE.match(line)
            if lab:
                if trades and lab.group("text") and not lab.group("text").startswith(("New", "Amended")):
                    comment.append(lab.group("text"))
                continue
            if comment and not asset_lines and line[:1].islower():
                comment.append(line)  # wrapped description of the previous trade
                continue
            asset_lines.append(line)
        if trades and comment:
            trades[-1]["comment"] = " ".join(comment)[:300]
        asset = " ".join(asset_lines)
        owner = None
        own = re.search(r"(?:^|\s)(SP|JT|DC)\s+(?=[A-Z0-9])", asset)
        if own:
            if own.start() and trades:  # what precedes the owner code is the end of the previous description
                trades[-1]["comment"] = f"{trades[-1]['comment'] or ''} {asset[:own.start()]}".strip()[:300]
            owner, asset = OWNERS[own.group(1)], asset[own.end():]
        tickers = re.findall(r"\(([A-Z][A-Z0-9.\-]{0,7})\)", asset)
        lo, hi = _amount(m.group("amt"))
        tx = m.group("tx").replace(" ", "")
        trades.append({
            "owner": owner or "Moi", "asset": asset.strip()[:200] or "?", "ticker": tickers[-1] if tickers else None,
            "asset_type": HOUSE_TYPES.get(m.group("atype"), "autre"),
            "action": {"P": "achat", "S": "vente", "S(partial)": "vente partielle", "E": "échange"}[tx],
            "tx_date": _day(m.group("d1")), "amount_min": lo, "amount_max": hi, "comment": None,
        })
        prev_end = m.end()
    # Description of the last trade, after the last anchor.
    tail = [LABEL_LINE.match(ln.strip()) for ln in text[prev_end:].splitlines()]
    desc = [t.group("text") for t in tail if t and t.group("text") and not t.group("text").startswith(("New", "Amended"))
            and "CERTIFY" not in t.group("text")]
    if trades and desc and not trades[-1]["comment"]:
        trades[-1]["comment"] = desc[0][:300]
    return trades


def _house_index(year: int) -> list[dict]:
    r = requests.get(f"{HOUSE}/financial-pdfs/{year}FD.zip", headers=HEADERS, timeout=120)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    lines = z.read(f"{year}FD.txt").decode("utf-8", "replace").splitlines()
    out = []
    for line in lines[1:]:
        f = line.split("\t")
        if len(f) >= 9 and f[4] == "P":
            out.append({"last": f[1], "first": f[2], "state": f[5][:2] or None, "filed": _day(f[7]), "doc": f[8].strip(),
                        "year": year})
    return out


def _house(con: sqlite3.Connection, years: list[int], limit: int | None) -> list[str]:
    from pypdf import PdfReader

    known = {r[0] for r in con.execute("SELECT id FROM congress_reports WHERE chamber = 'house'")}
    new_reports = []
    todo = [f for y in years for f in _house_index(y) if f["doc"] not in known and f["filed"]]
    for f in todo[:limit]:
        url = f"{HOUSE}/ptr-pdfs/{f['year']}/{f['doc']}.pdf"
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            if r.status_code == 404:
                continue
            r.raise_for_status()
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
        except Exception as e:  # noqa: BLE001 - one bad PDF must not stop the rest
            log.warning("House %s: %s", f["doc"], e)
            continue
        pid = _ensure_politician(con, "house", f["last"], f["first"], f["state"])
        trades = parse_house_pdf(text) if text.strip() else []
        _store(con, f["doc"], "house", pid, f["filed"], url, "electronic" if text.strip() else "paper", trades)
        new_reports.append(f["doc"])
        time.sleep(0.15)
    return new_reports


# ---------- Senate ----------

def _senate_session():
    from curl_cffi import requests as cr

    s = cr.Session(impersonate="chrome")
    r = s.get(f"{SENATE}/search/home/", timeout=60)
    token = re.search(r'csrfmiddlewaretoken" value="([^"]+)', r.text)
    if not token:
        raise RuntimeError("Sénat : page d'accord introuvable")
    s.post(f"{SENATE}/search/home/", data={"prohibition_agreement": "1", "csrfmiddlewaretoken": token.group(1)},
           headers={"Referer": f"{SENATE}/search/home/"}, timeout=60)
    return s


def _senate_list(s, since: date) -> list[dict]:
    csrf = s.cookies.get("csrftoken")
    out, start = [], 0
    while True:
        r = s.post(f"{SENATE}/search/report/data/", timeout=60, headers={"Referer": f"{SENATE}/search/",
                                                                          "X-CSRFToken": csrf},
                   data={"start": str(start), "length": "100", "report_types": "[11]", "filer_types": "[]",
                         "submitted_start_date": since.strftime("%m/%d/%Y 00:00:00"), "submitted_end_date": "",
                         "candidate_state": "", "senator_state": "", "office_id": "", "first_name": "",
                         "last_name": "", "csrfmiddlewaretoken": csrf})
        j = r.json()
        for first, last, _, link, filed in j["data"]:
            href = re.search(r'href="([^"]+)"', link)
            if href:
                out.append({"first": first, "last": last, "url": SENATE + href.group(1), "filed": _day(filed),
                            "id": href.group(1).rstrip("/").rsplit("/", 1)[-1],
                            "paper": "/paper/" in href.group(1)})
        start += 100
        if start >= j["recordsTotal"]:
            return out
        time.sleep(0.5)


def _cells(row: str) -> list[str]:
    return [html.unescape(re.sub(r"<[^>]+>", " ", c)).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]


def parse_senate_html(page: str) -> list[dict]:
    body = page[page.find("<tbody"):page.rfind("</tbody>")]
    trades = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        c = [re.sub(r"\s+", " ", x) for x in _cells(row)]
        if len(c) < 8:
            continue
        _, d, owner, ticker, asset, atype, tx, amt = c[:8]
        tx_l = tx.lower()
        action = ("vente partielle" if "partial" in tx_l else "vente" if "sale" in tx_l else "achat" if "purchase" in tx_l
                  else "échange")
        lo, hi = _amount(amt)
        at = atype.lower()
        trades.append({
            "owner": OWNERS.get(owner, owner or "Moi"), "asset": asset[:200] or "?",
            "ticker": ticker if ticker and ticker != "--" else (re.findall(r"\(([A-Z][A-Z0-9.\-]{0,7})\)", asset)
                                                                 or [None])[-1],
            "asset_type": "action" if "stock" in at and "option" not in at else "option" if "option" in at else
            "obligation" if "bond" in at or "note" in at else "fonds" if "fund" in at else "autre",
            "action": action, "tx_date": _day(d), "amount_min": lo, "amount_max": hi,
            "comment": (c[8] if len(c) > 8 and c[8] != "--" else None),
        })
    return trades


def _senate(con: sqlite3.Connection, since: date, limit: int | None) -> list[str]:
    s = _senate_session()
    known = {r[0] for r in con.execute("SELECT id FROM congress_reports WHERE chamber = 'senate'")}
    new_reports = []
    for f in [f for f in _senate_list(s, since) if f["id"] not in known][:limit]:
        pid = _ensure_politician(con, "senate", f["last"], f["first"], None)
        trades = []
        if not f["paper"]:
            try:
                trades = parse_senate_html(s.get(f["url"], timeout=60).text)
            except Exception as e:  # noqa: BLE001
                log.warning("Senate %s: %s", f["id"], e)
                continue
            time.sleep(0.4)
        _store(con, f["id"], "senate", pid, f["filed"], f["url"], "paper" if f["paper"] else "electronic", trades)
        new_reports.append(f["id"])
    return new_reports


# ---------- storage ----------

def _store(con: sqlite3.Connection, rid: str, chamber: str, pid: str, filed: str, url: str, kind: str,
           trades: list[dict]) -> None:
    con.execute("INSERT OR REPLACE INTO congress_reports VALUES (?, ?, ?, ?, ?, ?, ?)",
                (rid, chamber, pid, filed, url, kind, len(trades)))
    con.executemany(
        "INSERT OR REPLACE INTO congress_trades (id, report_id, politician_id, owner, ticker, asset, asset_type, action,"
        " tx_date, filed, amount_min, amount_max, comment) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [(_trade_id(rid, n), rid, pid, t["owner"], t["ticker"], t["asset"], t["asset_type"], t["action"], t["tx_date"],
          filed, t["amount_min"], t["amount_max"], t["comment"]) for n, t in enumerate(trades)])
    con.commit()


def sync(con: sqlite3.Connection, limit: int | None = None) -> dict:
    """Fetch the reports we do not have yet. Returns the ids of the new trades, per chamber."""
    init(con)
    before = {r[0] for r in con.execute("SELECT id FROM congress_trades")}
    first_run = con.execute("SELECT COUNT(*) FROM congress_reports").fetchone()[0] == 0
    today = date.today()
    years = list(range(FIRST_YEAR, today.year + 1)) if first_run else sorted({today.year, (today - timedelta(days=45)).year})
    errors = []
    try:
        _house(con, years, limit)
    except Exception as e:  # noqa: BLE001
        log.error("House: %s", e)
        errors.append(f"Chambre : {e}")
    last = db.get_meta(con, "last_senate_check")
    since = date(FIRST_YEAR, 1, 1) if not last else date.fromisoformat(last[:10]) - timedelta(days=10)
    try:
        _senate(con, since, limit)
        db.set_meta(con, "last_senate_check", db.now_iso())
    except Exception as e:  # noqa: BLE001
        log.error("Senate: %s", e)
        errors.append(f"Sénat : {e}")
    db.set_meta(con, "last_congress_check", db.now_iso())
    con.commit()
    new = [r[0] for r in con.execute("SELECT id FROM congress_trades") if r[0] not in before]
    return {"new": new, "errors": errors}


def update_returns(con: sqlite3.Connection, months: int = 36) -> int:
    """Price change of every stock bought or sold in the last ``months``, from the trade date to the last close,
    next to the S&P 500 over the same days (Yahoo, split and dividend adjusted)."""
    from ..prices import change, closes

    since = (date.today() - timedelta(days=31 * months)).isoformat()
    rows = con.execute("SELECT id, ticker, tx_date FROM congress_trades WHERE asset_type IN ('action', 'option')"
                       " AND ticker IS NOT NULL AND tx_date >= ?", (since,)).fetchall()
    if not rows:
        return 0
    px = closes(sorted({r[1] for r in rows} | {"SPY"}), since)
    if px.empty:
        return 0
    last_day = px.index[-1].date().isoformat()
    n = 0
    for tid, ticker, d in rows:
        r = change(px, ticker, d) if d else None
        if r is None:
            continue
        con.execute("UPDATE congress_trades SET ret = ?, bench_ret = ?, price_as_of = ? WHERE id = ?",
                    (r, change(px, "SPY", d), last_day, tid))
        n += 1
    con.commit()
    return n


def follow(con: sqlite3.Connection, pid: str, on: bool = True) -> None:
    """Follow or drop a member by hand; the choice is remembered and wins over the automatic selection."""
    manual = db.get_meta(con, "congress_follow_manual") or {}
    manual[pid] = bool(on)
    db.set_meta(con, "congress_follow_manual", manual)
    con.execute("UPDATE politicians SET followed = ? WHERE id = ?", (int(on), pid))
    con.commit()



def reparse_house(con: sqlite3.Connection, all_reports: bool = False) -> int:
    """Download and parse again the House reports whose trades look broken (a date or an amount inside an asset
    name), or every one with ``all_reports``: for parser fixes. Returns the number of reports redone."""
    from pypdf import PdfReader

    q = ("SELECT id, politician_id, filed, url FROM congress_reports WHERE chamber = 'house' AND kind = 'electronic'"
         + ("" if all_reports else " AND id IN (SELECT report_id FROM congress_trades WHERE asset GLOB"
            " '*[0-9][0-9]/[0-9][0-9]/[0-9][0-9][0-9][0-9]*' OR asset LIKE '%$%')"))
    n = 0
    for rid, pid, filed, url in con.execute(q).fetchall():
        try:
            r = requests.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            text = "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(r.content)).pages)
        except Exception as e:  # noqa: BLE001
            log.warning("House %s: %s", rid, e)
            continue
        con.execute("DELETE FROM congress_trades WHERE report_id = ?", (rid,))
        _store(con, rid, "house", pid, filed, url, "electronic", parse_house_pdf(text))
        n += 1
        time.sleep(0.15)
    return n
