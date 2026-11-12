"""SQLite store: the single source of truth for every account, flow and valuation.

Money is stored in integer cents (``*_cents``) so sums never drift; quantities of securities
are REAL because Trade Republic and the PEG hold fractional shares.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator

from .categories import DEFAULT_RULES

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    institution TEXT NOT NULL,          -- CMB, TR, AIRBUS
    name TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- courant, livret, especes, cto, pea, peg
    source TEXT NOT NULL,               -- banque, trade_republic, manuel
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS instruments (
    isin TEXT PRIMARY KEY,
    name TEXT,
    symbol TEXT,                        -- ticker for market data (ex: AIR.PA)
    kind TEXT,                          -- action, etf, crypto, obligation, derive
    currency TEXT NOT NULL DEFAULT 'EUR'
);
CREATE TABLE IF NOT EXISTS transactions (
    id TEXT PRIMARY KEY,                -- source id, or a hash of the bank line
    account_id TEXT NOT NULL REFERENCES accounts(id),  -- where the cash moved
    holding_account_id TEXT REFERENCES accounts(id),   -- where securities moved (trades only)
    date TEXT NOT NULL,                 -- YYYY-MM-DD, Paris time
    amount_cents INTEGER NOT NULL,      -- signed cash movement; for non-cash flows, the value received
    label TEXT,
    counterparty TEXT,
    flow TEXT NOT NULL,                 -- see categories.FLOWS
    category TEXT,                      -- spending/income category, rules-based
    category_override TEXT,             -- set by hand, always wins
    isin TEXT REFERENCES instruments(isin),
    quantity REAL,                      -- always positive; the flow gives the direction
    price REAL,                         -- EUR per share
    fees_cents INTEGER,
    tax_cents INTEGER,
    event_type TEXT,                    -- source event type (ex: CARD_TRANSACTION)
    raw_json TEXT,
    imported_at TEXT
);
CREATE INDEX IF NOT EXISTS transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS transactions_account ON transactions(account_id, date);
CREATE INDEX IF NOT EXISTS transactions_isin ON transactions(isin);
CREATE TABLE IF NOT EXISTS positions (
    account_id TEXT NOT NULL REFERENCES accounts(id),
    isin TEXT NOT NULL REFERENCES instruments(isin),
    quantity REAL NOT NULL,
    avg_cost REAL,                      -- EUR per share, NULL when unknown (PEG)
    as_of TEXT NOT NULL,
    source TEXT NOT NULL,               -- trade_republic, manuel
    PRIMARY KEY (account_id, isin)
);
CREATE TABLE IF NOT EXISTS prices (
    isin TEXT NOT NULL,
    date TEXT NOT NULL,
    close REAL NOT NULL,                -- EUR
    source TEXT,
    PRIMARY KEY (isin, date)
);
CREATE TABLE IF NOT EXISTS balances (
    account_id TEXT NOT NULL REFERENCES accounts(id),
    date TEXT NOT NULL,
    cash_cents INTEGER,
    securities_cents INTEGER,
    source TEXT,                        -- reported, reconstruit
    PRIMARY KEY (account_id, date)
);
CREATE TABLE IF NOT EXISTS valuations (      -- rebuilt from the transactions (portfolio.py)
    date TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    cash_cents INTEGER NOT NULL,
    securities_cents INTEGER NOT NULL,  -- market value
    cost_cents INTEGER NOT NULL,        -- cost basis of what is still held
    realised_cents INTEGER NOT NULL,    -- cumulative realised gains
    deposits_cents INTEGER NOT NULL,    -- cumulative money moved in from Jules's other accounts
    PRIMARY KEY (date, account_id)
);
CREATE TABLE IF NOT EXISTS category_rules (
    pattern TEXT PRIMARY KEY,           -- matched, case-insensitive, in label/counterparty
    category TEXT NOT NULL,
    origin TEXT NOT NULL                -- defaut, utilisateur
);
CREATE TABLE IF NOT EXISTS budgets (
    category TEXT PRIMARY KEY,
    monthly_limit_cents INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS alert_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,                 -- baisse_pct, hausse_pct, seuil_prix, budget, concentration
    isin TEXT,                          -- NULL: every line / whole portfolio
    target TEXT,                        -- budget rules: one category (NULL: all budgets)
    threshold REAL NOT NULL,
    window_days INTEGER,
    channels TEXT NOT NULL DEFAULT 'ntfy,mail',
    active INTEGER NOT NULL DEFAULT 1,
    note TEXT
);
CREATE TABLE IF NOT EXISTS alert_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER REFERENCES alert_rules(id),
    key TEXT,                           -- what makes it the same alert (line + day, category + month…)
    triggered_at TEXT NOT NULL,
    message TEXT NOT NULL,
    sent_to TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- hebdo, demande
    title TEXT,
    body_md TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_ideas (      -- orders Claude prepares; Jules places them himself
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    account_id TEXT REFERENCES accounts(id),
    isin TEXT,
    name TEXT,
    side TEXT NOT NULL,                 -- achat, vente
    quantity REAL,
    amount_eur REAL,
    limit_price REAL,
    rationale TEXT NOT NULL,
    risks TEXT,
    status TEXT NOT NULL DEFAULT 'proposé'  -- proposé, passé, abandonné
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS merchant_names (   -- display name of a merchant; several raw names may share one
    raw TEXT PRIMARY KEY,               -- merchant as queries.spending/income derive it (counterparty cleaned)
    display TEXT NOT NULL,
    not_subscription INTEGER NOT NULL DEFAULT 0  -- 1: never listed among the recurring charges
);
"""

ACCOUNTS = [
    ("cmb_courant", "CMB", "Compte courant", "courant", "banque"),
    ("cmb_livret_jeune", "CMB", "Livret Jeune", "livret", "banque"),
    ("cmb_livret_a", "CMB", "Livret CMB", "livret", "banque"),
    ("tr_especes", "TR", "Espèces et carte", "especes", "trade_republic"),
    ("tr_cto", "TR", "Compte-titres", "cto", "trade_republic"),
    ("tr_pea", "TR", "PEA", "pea", "trade_republic"),
    ("peg_airbus", "AIRBUS", "PEG Airbus", "peg", "manuel"),
]

AIRBUS = ("NL0000235190", "Airbus SE", "AIR.PA", "action", "EUR")
PEG_AIRBUS_SHARES = 109.4


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str) -> sqlite3.Connection:
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    # A sync and the screens may write at the same time (mobile app): wait for the lock instead of failing.
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def session(path: Path | str) -> Generator[sqlite3.Connection]:
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


# Columns added after the first release: (table, column, declaration).
MIGRATIONS = [
    ("alert_rules", "target", "TEXT"),
    ("alert_events", "key", "TEXT"),
]


def migrate(con: sqlite3.Connection) -> None:
    for table, column, decl in MIGRATIONS:
        cols = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
        if column not in cols:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init(con: sqlite3.Connection) -> None:
    """Create the schema and seed the fixed accounts, the PEG holding and the default rules.

    Idempotent: seeds never overwrite what is already there (a PEG quantity or a rule edited
    by hand survives a re-run).
    """
    con.executescript(SCHEMA)
    migrate(con)
    con.executemany(
        "INSERT OR IGNORE INTO accounts (id, institution, name, kind, source) VALUES (?, ?, ?, ?, ?)",
        ACCOUNTS,
    )
    con.execute("UPDATE accounts SET name = 'Livret CMB' WHERE id = 'cmb_livret_a'")
    con.execute("INSERT OR IGNORE INTO instruments VALUES (?, ?, ?, ?, ?)", AIRBUS)
    con.execute(
        "INSERT OR IGNORE INTO positions (account_id, isin, quantity, avg_cost, as_of, source)"
        " VALUES ('peg_airbus', ?, ?, NULL, ?, 'manuel')",
        (AIRBUS[0], PEG_AIRBUS_SHARES, now_iso()[:10]),
    )
    con.executemany(
        # Default rules follow the code; rules Jules set himself are never touched.
        "INSERT INTO category_rules (pattern, category, origin) VALUES (?, ?, 'defaut')"
        " ON CONFLICT(pattern) DO UPDATE SET category = excluded.category WHERE origin = 'defaut'",
        DEFAULT_RULES.items(),
    )
    con.commit()


def get_meta(con: sqlite3.Connection, key: str) -> Any:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return json.loads(row["value"]) if row else None


def set_meta(con: sqlite3.Connection, key: str, value: Any) -> None:
    con.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, json.dumps(value)),
    )


def rules(con: sqlite3.Connection) -> dict[str, str]:
    return {r["pattern"]: r["category"] for r in con.execute("SELECT pattern, category FROM category_rules")}


def set_rule(con: sqlite3.Connection, pattern: str, category: str) -> None:
    con.execute(
        "INSERT INTO category_rules (pattern, category, origin) VALUES (?, ?, 'utilisateur')"
        " ON CONFLICT(pattern) DO UPDATE SET category = excluded.category, origin = 'utilisateur'",
        (pattern.upper(), category),
    )


def set_balance(con: sqlite3.Connection, account_id: str, day: str, cents: int, source: str = "manuel") -> None:
    con.execute(
        "INSERT INTO balances (account_id, date, cash_cents, source) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(account_id, date) DO UPDATE SET cash_cents = excluded.cash_cents, source = excluded.source",
        (account_id, day, cents, source))
    con.commit()
