"""CMB "Recherche et export d'opérations" CSV files (RELEVE_<COMPTE>_<date>.csv).

They reach back to the opening of each account, where the PSD2 feed stops after ~13 months and does not
cover savings accounts at all. Columns: Date operation; Date valeur; Libelle; Debit; Credit (latin-1, ';').
Labels are the first part of the bank's statement label, so the same prefix rules as the feed apply.
"""
from __future__ import annotations

import csv
import hashlib
from collections import Counter
from pathlib import Path

from . import cmb_parse
from .tr_parse import Row

ACCOUNTS = {"COMPTE_CHEQUES": "cmb_courant", "LIVRET_JEUNE": "cmb_livret_jeune", "LIVRET_CMB": "cmb_livret_a"}


def account_of(path: Path) -> str | None:
    name = path.name.upper()
    return next((acc for key, acc in ACCOUNTS.items() if key in name), None)


def amount(s: str) -> float:
    s = (s or "").replace("\xa0", "").replace(" ", "").replace(",", ".")
    return float(s) if s else 0.0


def parse(path: Path, owner: set[str]) -> list[Row]:
    account = account_of(path)
    if not account:
        return []
    with open(path, encoding="latin-1", newline="") as f:
        lines = list(csv.DictReader(f, delimiter=";"))
    txs = []
    for line in lines:
        d, m, y = line["Date operation"].split("/")
        value = amount(line.get("Credit", "")) - amount(line.get("Debit", ""))
        txs.append({"booking_date": f"{y}-{m}-{d}", "status": "BOOK",
                    "credit_debit_indicator": "CRDT" if value > 0 else "DBIT",
                    "transaction_amount": {"currency": "EUR", "amount": f"{abs(value):.2f}"},
                    "remittance_information": [line["Libelle"].strip()], "source": "csv"})
    rows, _ = cmb_parse.parse({"accounts": [{"transactions": txs}]}, owner, account_id=account)
    seen: Counter = Counter()
    for r in rows:  # own id space: CSV labels are shorter than the feed's, so the two never collide
        basis = f"{account}|{r.date}|{r.amount_cents}|{r.label}"
        seen[basis] += 1
        r.id = "cmbcsv:" + hashlib.sha1(f"{basis}|{seen[basis]}".encode()).hexdigest()[:20]
    return rows
