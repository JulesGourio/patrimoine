"""CMB current account lines (Enable Banking dump) -> database rows.

The bank sends no transaction codes, only the statement label, so the flow comes from its prefix:
"CARTE 24/08 MERCHANT", "PRLV CREDITOR", "VIR INST NAME  de ...", "VIR vers NAME  de ...",
"VIR de NAME", "RET DAB", "F COTISATION". The label is split on runs of two spaces.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from typing import Any

from .tr_parse import Row, words

# Labels that move money between Jules's own accounts (Trade Republic, CMB savings).
# Jules's own accounts; Revolut was one (closed, empty) that mostly relayed money to Trade Republic.
INTERNAL = re.compile(r"LIVRET|COMPTE CHEQUES|TRADE ?REPUBLIC|GOURIO TRADER|REVOLU", re.I)
TAX = re.compile(r"DIRECTION GENERALE DES FINA|DGFIP|IMPOT", re.I)


def parts(tx: dict[str, Any]) -> list[str]:
    text = "  ".join(tx.get("remittance_information") or [])
    return [p.strip() for p in re.split(r"\s{2,}", text) if p.strip()]


def counterparty(label: str, first: str) -> str | None:
    """The other side, from the first part of the label."""
    m = re.match(r"CARTE \d\d/\d\d (.+)", first)
    if m:
        return re.sub(r"\s+\d+,\d\d EUR$", "", m.group(1)).strip()
    for prefix in ("VIR INST ", "VIR vers ", "VIR de ", "VIR ", "vers ", "PRLV "):
        if first.startswith(prefix):
            return first[len(prefix):].strip(" /")
    return first


def parse(dump: dict[str, Any], owner: set[str], account_id: str = "cmb_courant") -> tuple[list[Row], Counter]:
    rows: list[Row] = []
    kinds: Counter = Counter()
    for acc in dump.get("accounts", []):
        seen: Counter = Counter()
        for tx in acc.get("transactions", []):
            if tx.get("status") not in (None, "BOOK"):
                continue  # pending lines change; wait until booked
            p = parts(tx)
            label = " ".join(p)
            first = p[0] if p else ""
            amount = round(float(tx["transaction_amount"]["amount"]) * 100)
            if tx.get("credit_debit_indicator") == "DBIT":
                amount = -abs(amount)
            who = counterparty(label, first)

            if INTERNAL.search(label) or (who and owner and owner <= set(words(who))):
                flow = "interne"
            elif first.startswith("F COTISATION") or first.startswith("FRAIS") or first.startswith("COMMISSION"):
                flow = "frais"
            elif TAX.search(label) and amount < 0:
                flow = "depense"
            elif first.startswith("INTERETS") or first.startswith("INT CREDITEURS"):
                flow = "interets"
            elif amount > 0:
                flow = "revenu"
            else:
                flow = "depense"
            kinds[first.split(" ")[0] if first else "?"] += 1

            # The bank's entry_reference is a per-day index ("2026-09-25T00:00:02-0") that can shift
            # when a line is added the same day: identify lines by content instead.
            basis = f"{tx.get('booking_date')}|{amount}|{label}"
            seen[basis] += 1
            rid = "cmb:" + hashlib.sha1(f"{basis}|{seen[basis]}".encode()).hexdigest()[:20]
            rows.append(Row(id=rid, account_id=account_id, date=tx.get("booking_date") or tx.get("value_date"),
                            amount_cents=amount, flow=flow, event_type=first.split(" ")[0] if first else None,
                            label=label, counterparty=who, raw=tx))
    return rows, kinds


def livret_mirror(rows: list[Row], livret: str = "cmb_livret_a") -> list[Row]:
    """The Livret CMB is not in the bank feed: mirror every transfer the current account makes with it."""
    out = []
    for r in rows:
        if r.flow == "interne" and "LIVRET CMB" in (r.label or "").upper():
            out.append(Row(id=r.id + ":livret", account_id=livret, date=r.date, amount_cents=-r.amount_cents,
                           flow="interne", event_type=r.event_type, label=r.label, counterparty="Compte courant CMB",
                           raw=r.raw))
    return out


def balance(dump: dict[str, Any]) -> tuple[str, int] | None:
    for acc in dump.get("accounts", []):
        for b in acc.get("balances", []):
            amount = b.get("balance_amount") or {}
            if amount.get("amount") is not None:
                return b.get("reference_date") or "", round(float(amount["amount"]) * 100)
    return None


def raw_json(row: Row) -> str:
    return json.dumps(row.raw, ensure_ascii=False, separators=(",", ":"))
