"""Load parsed source data into the database, idempotently."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from . import db
from .categories import categorize
from .sources.tr_parse import Parsed, raw_json


@dataclass
class Report:
    new: int
    updated: int
    positions: int
    unknown: dict[str, int]

    def lines(self) -> list[str]:
        out = [f"{self.new} nouvelles opérations, {self.updated} mises à jour, {self.positions} positions"]
        if self.unknown:
            out.append("Types d'événements inconnus, non importés : "
                       + ", ".join(f"{k} ({v})" for k, v in self.unknown.items()))
        return out


def import_rows(con: sqlite3.Connection, rows: list, raw_json) -> tuple[int, int]:
    """Upsert rows (sources.tr_parse.Row); returns (new, updated). Hand-set categories are kept."""
    rules = db.rules(con)
    now = db.now_iso()
    known = {r[0] for r in con.execute("SELECT id FROM transactions")}
    for r in rows:
        if r.isin:
            kind = "derive" if (r.instrument or "").startswith(("Long", "Short")) else None
            con.execute("INSERT OR IGNORE INTO instruments (isin, name, kind) VALUES (?, ?, ?)",
                        (r.isin, r.instrument, kind))
    new = updated = 0
    for r in rows:
        category = categorize(r.flow, r.label, r.counterparty, rules)
        values = (r.id, r.account_id, r.holding_account_id, r.date, r.amount_cents, r.label, r.counterparty,
                  r.flow, category, r.isin, r.quantity, r.price, r.fees_cents, r.tax_cents, r.event_type,
                  raw_json(r), now)
        con.execute(
            """INSERT INTO transactions (id, account_id, holding_account_id, date, amount_cents, label, counterparty,
                   flow, category, isin, quantity, price, fees_cents, tax_cents, event_type, raw_json, imported_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET account_id = excluded.account_id,
                   holding_account_id = excluded.holding_account_id, date = excluded.date,
                   amount_cents = excluded.amount_cents, label = excluded.label,
                   counterparty = excluded.counterparty, flow = excluded.flow, category = excluded.category,
                   isin = excluded.isin, quantity = excluded.quantity, price = excluded.price,
                   fees_cents = excluded.fees_cents, tax_cents = excluded.tax_cents,
                   event_type = excluded.event_type, raw_json = excluded.raw_json""",
            values,
        )
        if r.id in known:
            updated += 1
        else:
            new += 1
    return new, updated


def import_trade_republic(con: sqlite3.Connection, parsed: Parsed, as_of: str | None = None,
                          owner: dict | None = None) -> Report:
    as_of = as_of or date.today().isoformat()
    for p in parsed.positions:
        con.execute("INSERT OR IGNORE INTO instruments (isin, name, kind) VALUES (?, ?, ?)",
                    (p["isin"], p["name"], p["kind"]))
    new, updated = import_rows(con, parsed.rows, raw_json)
    if owner:
        db.set_meta(con, "owner", owner)

    # Positions: Trade Republic's view replaces ours for its accounts.
    tr_accounts = sorted({p["account_id"] for p in parsed.positions} | {"tr_cto", "tr_pea"})
    con.execute(f"DELETE FROM positions WHERE account_id IN ({','.join('?' * len(tr_accounts))})", tr_accounts)
    for p in parsed.positions:
        con.execute(
            "INSERT INTO positions (account_id, isin, quantity, avg_cost, as_of, source) VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(account_id, isin) DO UPDATE SET quantity = excluded.quantity, avg_cost = excluded.avg_cost,"
            " as_of = excluded.as_of, source = excluded.source",
            (p["account_id"], p["isin"], p["quantity"], p["avg_cost"], as_of, "trade_republic"),
        )
    for account_id, cash in parsed.cash.items():
        con.execute(
            "INSERT INTO balances (account_id, date, cash_cents, source) VALUES (?, ?, ?, 'reported')"
            " ON CONFLICT(account_id, date) DO UPDATE SET cash_cents = excluded.cash_cents, source = 'reported'",
            (account_id, as_of, cash),
        )
    db.set_meta(con, "last_sync_tr", db.now_iso())
    con.commit()
    return Report(new=new, updated=updated, positions=len(parsed.positions), unknown=dict(parsed.unknown))


def import_cmb(con: sqlite3.Connection, dump: dict) -> Report:
    from .sources import cmb_parse
    from .sources.tr_parse import words

    name = db.get_meta(con, "owner") or {}
    owner = set(words(name.get("last")) + words(name.get("first"))[:1])
    rows, _ = cmb_parse.parse(dump, owner)
    new, updated = import_rows(con, rows, cmb_parse.raw_json)
    bal = cmb_parse.balance(dump)
    if bal:
        con.execute(
            "INSERT INTO balances (account_id, date, cash_cents, source) VALUES ('cmb_courant', ?, ?, 'reported')"
            " ON CONFLICT(account_id, date) DO UPDATE SET cash_cents = excluded.cash_cents, source = 'reported'",
            bal)
    db.set_meta(con, "last_sync_cmb", db.now_iso())
    con.commit()
    return Report(new=new, updated=updated, positions=0, unknown={})
