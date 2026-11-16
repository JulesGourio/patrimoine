"""Generic, configurable CSV bank export -> database rows (same ``Row`` format as the CMB parsers).

A profile says how to read the file: delimiter, encoding, header line, date format, decimal separator, and the
columns (date, label, then either one signed amount or a debit and a credit column). Flows come from
``cmb_parse.parse`` (so a transfer between the user's own accounts is ``interne``); ids are stable hashes of
the content, so re-importing the same file adds nothing.
"""
from __future__ import annotations

import csv
import hashlib
import io
import re
from collections import Counter
from typing import Iterable
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path

from . import cmb_parse
from .tr_parse import Row


@dataclass
class Profile:
    """How to read one bank's CSV. Columns are header names (or 0-based indexes when ``header`` is False)."""
    account: str
    date: str = "Date"
    label: str = "Libellé"
    amount: str | None = None  # one signed amount column...
    debit: str | None = None  # ...or a debit column (money out) and a credit column (money in)
    credit: str | None = None
    delimiter: str = ";"
    date_format: str = "%d/%m/%Y"
    decimal: str = ","
    encoding: str = "utf-8-sig"
    header: bool = True
    skip: int = 0  # lines to ignore before the header (bank preambles)

    @classmethod
    def from_dict(cls, d: dict) -> "Profile":
        known = {f.name for f in fields(cls)}
        unknown = set(d) - known
        if unknown:
            raise ValueError(f"réglages inconnus : {', '.join(sorted(unknown))}")
        p = cls(**d)
        p.check()
        return p

    def check(self) -> None:
        if not self.account:
            raise ValueError("compte cible manquant")
        if not self.amount and not (self.debit or self.credit):
            raise ValueError("indiquer la colonne montant, ou débit et crédit")
        if self.amount and (self.debit or self.credit):
            raise ValueError("colonne montant ou colonnes débit/crédit, pas les deux")
        if len(self.delimiter) != 1:
            raise ValueError("le séparateur doit être un seul caractère")
        if self.decimal not in (",", "."):
            raise ValueError("séparateur décimal : ',' ou '.'")
        datetime.strptime("2000-01-01", "%Y-%m-%d").strftime(self.date_format)  # raises on a bad format

    def to_dict(self) -> dict:
        return asdict(self)


def cents(text: str | None, decimal: str = ",") -> int:
    """'1 234,56' / '-12.50' / '(12,00)' / '12,00 €' -> integer cents; empty -> 0."""
    s = (text or "").replace("\xa0", "").replace(" ", "").replace(" ", "")
    s = re.sub(r"[€$£]|EUR", "", s)
    if not s:
        return 0
    negative = s.startswith("(") and s.endswith(")") or s.endswith("-")
    s = s.strip("()").rstrip("-")
    if decimal == ",":
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        value = round(abs(float(s)) * 100) * (-1 if s.startswith("-") else 1)
    except ValueError:
        raise ValueError(f"montant illisible : {text!r}") from None
    return -abs(value) if negative else value


def _day(text: str, fmt: str) -> str:
    try:
        return datetime.strptime(text.strip(), fmt).date().isoformat()
    except ValueError:
        raise ValueError(f"date illisible : {text!r} (format {fmt})") from None


def read(data: bytes, profile: Profile) -> list[dict]:
    """The lines of the file as {date, label, cents}; blank lines are skipped, bad ones raise."""
    text = data.decode(profile.encoding)
    lines = text.splitlines()[profile.skip:]
    reader = csv.reader(io.StringIO("\n".join(lines)), delimiter=profile.delimiter)
    table = [r for r in reader if any(c.strip() for c in r)]
    if profile.header:
        if not table:
            return []
        names = [c.strip() for c in table[0]]
        table = table[1:]

        def col(key: str | None) -> int | None:
            if key is None:
                return None
            if key not in names:
                raise ValueError(f"colonne introuvable : {key!r} (colonnes : {', '.join(names)})")
            return names.index(key)
    else:
        def col(key: str | None) -> int | None:
            return None if key is None else int(key)

    i_date, i_label = col(profile.date), col(profile.label)
    i_amount, i_debit, i_credit = col(profile.amount), col(profile.debit), col(profile.credit)

    def cell(row: list[str], i: int | None) -> str:
        return row[i] if i is not None and i < len(row) else ""

    out = []
    for n, row in enumerate(table, 1):
        try:
            if i_amount is not None:
                value = cents(cell(row, i_amount), profile.decimal)
            else:
                value = abs(cents(cell(row, i_credit), profile.decimal)) - abs(cents(cell(row, i_debit), profile.decimal))
            out.append({"date": _day(cell(row, i_date), profile.date_format),
                        "label": " ".join(cell(row, i_label).split()), "cents": value})
        except ValueError as e:
            raise ValueError(f"ligne {n} : {e}") from None
    return out


def parse(data: bytes, profile: Profile, owner: set[str] = frozenset(),
          internal: Iterable[str] = ()) -> list[Row]:
    """Rows ready for ``sync.import_rows``; ``owner`` = words of the user's name (own-account transfers)."""
    txs = []
    for line in read(data, profile):
        value = line["cents"]
        txs.append({"booking_date": line["date"], "status": "BOOK",
                    "credit_debit_indicator": "CRDT" if value > 0 else "DBIT",
                    "transaction_amount": {"currency": "EUR", "amount": f"{abs(value) / 100:.2f}"},
                    "remittance_information": [line["label"]], "source": "csv"})
    rows, _ = cmb_parse.parse({"accounts": [{"transactions": txs}]}, set(owner), account_id=profile.account,
                              internal=internal)
    seen: Counter = Counter()
    for r in rows:  # stable hash of the content; a repeat of the same line the same day gets the next number
        basis = f"{profile.account}|{r.date}|{r.amount_cents}|{r.label}"
        seen[basis] += 1
        r.id = "csv:" + hashlib.sha1(f"{basis}|{seen[basis]}".encode()).hexdigest()[:20]
    return rows


def load(path: Path) -> bytes:
    return Path(path).read_bytes()
