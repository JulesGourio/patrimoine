"""Airbus employee savings (PEG) from Amundi ESR statements ("AVO" PDFs).

Two supports hold Airbus exposure:
- "AIRBUS EN ACTIONS": profit-sharing invested in Airbus shares; each statement gives the quantity and
  the price, so these buys are exact.
- "ESOP SOUSCRIPTIONS" (and the "ESOP AIRBUS RELAIS" funds before conversion): the employee share plan.
  Statements only give its value, so it is converted into Airbus-share equivalents with the price implied
  by the "AIRBUS EN ACTIONS" line of the same statement (or the Airbus close when there is none). A rise
  of several shares between two statements is a new subscription (cost estimated at its value that day);
  a small rise is reinvested dividends.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable

from .tr_parse import Row

AIRBUS = "NL0000235190"
ACCOUNT = "peg_airbus"
NEW_SUBSCRIPTION = 5.0  # shares: below this, a rise of the ESOP line is dividends, not a subscription


def number(s: str) -> float:
    return float(s.replace(" ", "").replace("\xa0", "").replace(" ", "").replace(",", "."))


def day(s: str) -> str:
    return datetime.strptime(s, "%d/%m/%Y").date().isoformat()


@dataclass
class Statement:
    path: str
    kind: str                           # Relevé d'Intéressement, de Participation, de Transfert…
    date: str                           # valuation date of the holdings summary
    buys: list[dict] = field(default_factory=list)       # exact "AIRBUS EN ACTIONS" buys
    supports: dict[str, float] = field(default_factory=dict)  # support -> value (EUR)


def text_of(pdf: Path) -> str:
    from pypdf import PdfReader

    return "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages)


def parse(text: str, path: str = "") -> Statement:
    flat = re.sub(r"\s+", " ", text)
    kind = (re.search(r"(Relevé (?:de |d')[\w' ]+?)\s+(?:Pour nous|Synthèse|Récapitulatif)", flat) or
            re.search(r"(Relevé [^\n]{0,40})", text))
    when = re.search(r"valeur de vos avoirs au (\d\d/\d\d/\d{4})", flat) or re.search(r"Valence, le (\d\d/\d\d/\d{4})",
                                                                                      flat)
    st = Statement(path=path, kind=kind.group(1).strip() if kind else "Relevé", date=day(when.group(1)) if when else "")
    for m in re.finditer(r"INVESTISSEMENT DE VOTRE ([A-ZÉ' ]+?) SUR PEG - AIRBUS EN ACTIONS : ([\d ,]+) \(Quantité\) le "
                         r"(\d\d/\d\d/\d{4}) à ([\d ,]+) € - DISPONIBLES LE (\d\d/\d\d/\d{4}) ([\d ,]+) €", flat):
        st.buys.append({"what": m.group(1).strip().lower(), "quantity": number(m.group(2)), "date": day(m.group(3)),
                        "price": number(m.group(4)), "available": day(m.group(5)), "amount": number(m.group(6))})
    block = flat.split("Récapitulatif de votre épargne", 1)[-1]
    # Amounts group thousands by three ("5 949,89"), which keeps "RELAIS 2025" out of the value.
    amount = r"\d{1,3}(?: \d{3})*,\d\d"
    for m in re.finditer(rf"((?:ESOP|AIRBUS)[A-Z0-9 ]*?) ({amount}) € {amount} €", block):
        st.supports[m.group(1).strip()] = number(m.group(2))
    return st


def rows(statements: list[Statement], close: Callable[[str], float | None]) -> tuple[list[Row], dict]:
    """PEG transactions (exact buys + ESOP share equivalents) and a summary for the user."""
    out: list[Row] = []
    seen = set()
    for st in statements:
        for b in st.buys:
            key = (b["date"], b["quantity"], b["amount"])
            if key in seen:
                continue
            seen.add(key)
            out.append(Row(id="peg:" + hashlib.sha1(repr(key).encode()).hexdigest()[:16], account_id=ACCOUNT,
                           holding_account_id=ACCOUNT, date=b["date"], amount_cents=-round(b["amount"] * 100),
                           flow="achat_titre", event_type="PEG_" + b["what"].upper().replace(" ", "_"),
                           label=f"PEG Airbus : {b['what']} investi (disponible le {b['available']})",
                           isin=AIRBUS, instrument="Airbus SE", quantity=b["quantity"], price=b["price"],
                           fees_cents=0, raw=b))
    # Airbus shares held in "AIRBUS EN ACTIONS" at each statement date, from the exact buys.
    buys = sorted(({"date": r.date, "q": r.quantity} for r in out), key=lambda x: x["date"])

    def direct(on: str) -> float:
        return sum(b["q"] for b in buys if b["date"] <= on)

    esop_prev = 0.0
    summary = {"statements": [], "esop_events": []}
    for st in sorted(statements, key=lambda s: s.date):
        esop = sum(v for k, v in st.supports.items() if k.startswith("ESOP"))
        act = st.supports.get("AIRBUS EN ACTIONS")
        q_direct = direct(st.date)
        price = act / q_direct if act and q_direct else close(st.date)
        eq = esop / price if price else 0.0
        summary["statements"].append({"date": st.date, "type": st.kind, "esop_eur": esop, "actions_eur": act or 0.0,
                                      "prix": round(price or 0, 2), "esop_actions": round(eq, 4)})
        gain = eq - esop_prev
        if price and gain > 0.05:
            subscription = gain >= NEW_SUBSCRIPTION
            ev = {"date": st.date, "quantity": round(gain, 4), "price": round(price, 2),
                  "type": "souscription ESOP" if subscription else "dividendes réinvestis (ESOP)"}
            summary["esop_events"].append(ev)
            out.append(Row(id=f"peg:esop:{st.date}", account_id=ACCOUNT, holding_account_id=ACCOUNT, date=st.date,
                           amount_cents=-round(gain * price * 100) if subscription else 0,
                           flow="achat_titre" if subscription else "operation_titres", event_type="PEG_ESOP",
                           label=f"PEG Airbus : {ev['type']} (équivalent actions, coût estimé)", isin=AIRBUS,
                           instrument="Airbus SE", quantity=round(gain, 4), price=round(price, 2), fees_cents=0,
                           raw=ev))
            esop_prev = eq
    last = max(statements, key=lambda s: s.date) if statements else None
    summary["total_actions"] = round(sum(r.quantity or 0 for r in out), 4)
    summary["as_of"] = last.date if last else None
    return out, summary


def load(folder: Path) -> list[Statement]:
    return [parse(text_of(p), str(p)) for p in sorted(folder.glob("*.pdf"))]


def today() -> str:
    return date.today().isoformat()


def raw_json(row: Row) -> str:
    import json

    return json.dumps(row.raw, ensure_ascii=False, separators=(",", ":"), default=str)
