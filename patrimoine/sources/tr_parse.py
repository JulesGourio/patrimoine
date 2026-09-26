"""Turn a raw Trade Republic dump (see trade_republic.fetch_all) into rows for the database.

Everything here reads the French web texts ("Frais", "Titres"…) and event types that Trade
Republic may rename at any time. Unknown event types are never dropped silently: they come back
in ``Parsed.unknown`` so the sync can report them.
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")

CARD = {"CARD_TRANSACTION", "CARD_AFT", "CARD_REFUND", "BANK_TRANSACTION_OUTGOING_DIRECT_DEBIT"}
INCOMING = {"BANK_TRANSACTION_INCOMING", "PAYMENT_INBOUND", "PAYMENT_INBOUND_CREDIT_CARD"}
OUTGOING = {"BANK_TRANSACTION_OUTGOING", "PAYMENT_OUTBOUND"}
INTEREST = {"INTEREST_PAYOUT", "INTEREST_PAYOUT_CREATED"}
TRADES = {
    "TRADE_INVOICE", "ORDER_EXECUTED", "TRADING_TRADE_EXECUTED",
    "SAVINGS_PLAN_INVOICE_CREATED", "SAVINGS_PLAN_EXECUTED", "TRADING_SAVINGSPLAN_EXECUTED",
}
DIVIDENDS = {"SSP_CORPORATE_ACTION_CASH", "CREDIT"}
# Events with no money or securities effect (failed plans, card checks, documents, chats…).
IGNORED = {
    "CARD_VERIFICATION", "TRADING_SAVINGSPLAN_EXECUTION_FAILED", "SAVINGS_PLAN_EXECUTION_FAILED",
    "ORDER_REJECTED", "DOCUMENTS_ACCEPTED", "DOCUMENTS_CREATED", "CSX_CHAT_ACTIVITY",
    "EX_POST_COST_REPORT_CREATED", "TAX_YEAR_END_REPORT_CREATED", "QUARTERLY_NET_WORTH_STATEMENT_CREATED",
    "TAX_CUSTOMER_CONFIGURATION_CHANGED", "PRIVATE_MARKETS_SUITABILITY_QUIZ_COMPLETED", "DEVICE_RESET",
    "PUK_CREATED", "REFERENCE_ACCOUNT_CHANGED", "EMAIL_VALIDATED", "CUSTOMER_CREATED",
    "SECURITIES_ACCOUNT_CREATED", "SSP_CORPORATE_ACTION_INFORMATIVE", "SSP_CORPORATE_ACTION_ACTIVITY",
}


@dataclass
class Row:
    id: str
    account_id: str
    date: str
    amount_cents: int
    flow: str
    event_type: str | None
    label: str | None = None
    counterparty: str | None = None
    holding_account_id: str | None = None
    isin: str | None = None
    instrument: str | None = None
    quantity: float | None = None
    price: float | None = None
    fees_cents: int | None = None
    tax_cents: int | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class Parsed:
    rows: list[Row]
    positions: list[dict[str, Any]]      # {account_id, isin, name, quantity, avg_cost, kind}
    cash: dict[str, int | None]          # account_id -> cents, as reported by Trade Republic
    unknown: Counter


# ---------- small readers ----------

def number(text: Any) -> float | None:
    """French web numbers: '1 851,00 €', '2.684,43 €', '0.190726', '+ 6,38 €', 'Gratuit'."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    t = str(text)
    if t.strip().lower() in {"gratuit", "free"}:
        return 0.0
    t = re.sub(r"[^\d,.\-]", "", t)
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        # The last separator is the decimal one.
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    else:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def words(text: str | None) -> list[str]:
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().upper()
    return re.findall(r"[A-Z]+", t)


def cents(value: float | None) -> int | None:
    return None if value is None else int(round(value * 100))


def paris_date(ts: str) -> str:
    dt = datetime.strptime(ts[:23] + ts[23:].replace(":", ""), "%Y-%m-%dT%H:%M:%S.%f%z")
    return dt.astimezone(PARIS).date().isoformat()


def detail_rows(detail: dict | None) -> dict[str, str]:
    """{row title: row text} over every table of a timeline detail; the first occurrence wins."""
    out: dict[str, str] = {}
    for section in (detail or {}).get("sections", []):
        if section.get("type") != "table" or not isinstance(section.get("data"), list):
            continue
        for row in section["data"]:
            if not isinstance(row, dict) or not row.get("title"):
                continue
            text = (row.get("detail") or {}).get("text")
            if text is not None:
                out.setdefault(row["title"], text)
    return out


def header_isin(detail: dict | None) -> str | None:
    """The traded instrument. For turbos the icon is the underlying's; the header action is the product."""
    for section in (detail or {}).get("sections", []):
        if section.get("type") == "header":
            action = section.get("action") or {}
            if action.get("type") == "instrumentDetail" and ISIN_RE.match(str(action.get("payload"))):
                return action["payload"]
    return None


def icon_isin(event: dict) -> str | None:
    m = re.match(r"logos/([A-Z0-9]{12})/", event.get("icon") or "")
    return m.group(1) if m and ISIN_RE.match(m.group(1)) else None


def first(rows: dict[str, str], *titles: str) -> str | None:
    for t in titles:
        if t in rows:
            return rows[t]
    return None


def quantity_and_price(rows: dict[str, str]) -> tuple[float | None, float | None]:
    qty = number(first(rows, "Titres", "Actions"))
    price = number(first(rows, "Cours du titre"))
    tx = rows.get("Transaction")
    if tx and re.search(r"[x×]", tx):
        q, p = re.split(r"\s*[x×]\s*", tx, maxsplit=1)
        qty = qty if qty is not None else number(q)
        price = price if price is not None else number(p)
    return qty, price


def is_payout(event: dict, rows: dict[str, str]) -> bool:
    """A cash corporate action that is not a dividend: warrant exercise, turbo knock-out."""
    what = (rows.get("Événement") or event.get("subtitle") or "").lower()
    return "dividende" not in what and ("warrant" in what or "exercice" in what or "knock" in what)


def instrument_kind(position: dict) -> str:
    t = (position.get("instrumentType") or "").lower()
    if position.get("derivativeInfo"):
        return "derive"
    return {"fund": "etf", "stock": "action", "crypto": "crypto", "bond": "obligation"}.get(t, t or "action")


# ---------- main parser ----------

def parse(dump: dict[str, Any]) -> Parsed:
    account = dump.get("account") or {}
    name = account.get("name") or {}
    owner = set(words(name.get("last")) + words(name.get("first"))[:1])
    main_cash = next((c["accountNumber"] for c in dump.get("cash") or [] if c.get("accountNumber")), None)
    cto_no = account.get("securitiesAccountNumber")

    def cash_account(event: dict) -> str:
        no = event.get("cashAccountNumber")
        return "tr_pea" if no and main_cash and no != main_cash else "tr_especes"

    def holding(event: dict, rows: dict[str, str]) -> str:
        wallet = (first(rows, "Portefeuille", "Compte") or "").upper()
        if "PEA" in wallet or "PLAN EPARGNE" in wallet or "PLAN ÉPARGNE" in wallet:
            return "tr_pea"
        if "COMPTE-TITRES" in wallet:
            return "tr_cto"
        return "tr_pea" if cash_account(event) == "tr_pea" else "tr_cto"

    def is_owner(who: str | None) -> bool:
        return bool(owner) and owner <= set(words(who))

    def held_in(isin: str | None) -> str:
        """The account that holds this security so far (for events that do not say it)."""
        for row in reversed(rows):
            if row.isin == isin and row.holding_account_id:
                return row.holding_account_id
        return "tr_cto"

    rows: list[Row] = []
    unknown: Counter = Counter()
    details = dump.get("details") or {}
    bought_by_icon: dict[str, dict[str, float]] = {}  # underlying icon ISIN -> {product ISIN: net qty}

    events = sorted((dump.get("transactions") or []) + (dump.get("activity") or []), key=lambda e: e["timestamp"])
    for ev in events:
        et = ev.get("eventType")
        if ev.get("deleted") or ev.get("status") == "CANCELED" or et in IGNORED:
            continue
        det = details.get(ev["id"])
        r = detail_rows(det)
        value = (ev.get("amount") or {}).get("value")
        amount = cents(value) or 0
        base: dict[str, Any] = dict(id=ev["id"], date=paris_date(ev["timestamp"]), event_type=et, label=ev.get("title"),
                    raw=ev)
        tax = cents(abs(number(first(r, "Taxes", "Impôt", "Impôts")) or 0)) or None
        fees = cents(number(r.get("Frais")))

        if et in CARD:
            flow = "interne" if is_owner(ev.get("title")) else "depense"
            rows.append(Row(**base, account_id="tr_especes", amount_cents=amount, flow=flow,
                            counterparty=first(r, "Commerçant", "Destinataire") or ev.get("title")))
        elif et in INCOMING or et in OUTGOING:
            who = first(r, "Expéditeur", "De", "Destinataire") or ev.get("title")
            flow = "interne" if is_owner(who) or et == "PAYMENT_INBOUND_CREDIT_CARD" else (
                "revenu" if amount > 0 else "depense")
            rows.append(Row(**base, account_id=cash_account(ev), amount_cents=amount, flow=flow, counterparty=who))
        elif et in INTEREST:
            rows.append(Row(**base, account_id=cash_account(ev), amount_cents=amount, flow="interets", tax_cents=tax))
        elif et in TRADES:
            isin = header_isin(det) or icon_isin(ev)
            qty, price = quantity_and_price(r)
            flow = "achat_titre" if amount < 0 else "vente_titre"
            rows.append(Row(**base, account_id=cash_account(ev), holding_account_id=holding(ev, r),
                            amount_cents=amount, flow=flow, isin=isin, instrument=ev.get("title"),
                            quantity=qty, price=price, fees_cents=fees, tax_cents=tax))
            under = icon_isin(ev)
            if under and isin and qty:
                held = bought_by_icon.setdefault(under, {})
                held[isin] = held.get(isin, 0) + (qty if flow == "achat_titre" else -qty)
        elif et == "SAVEBACK_AGGREGATE" or et == "STOCK_PERK_REFUNDED":
            qty, price = quantity_and_price(r)
            got = number(first(r, "Total", "Accumulé"))
            rows.append(Row(**base, account_id="tr_cto", holding_account_id="tr_cto",
                            amount_cents=cents(abs(got if got is not None else value or 0)) or 0,
                            flow="saveback" if et == "SAVEBACK_AGGREGATE" else "titres_offerts",
                            isin=header_isin(det) or icon_isin(ev), instrument=ev.get("title"),
                            quantity=qty, price=price))
        elif et in DIVIDENDS and not is_payout(ev, r):
            rows.append(Row(**base, account_id=cash_account(ev), holding_account_id=holding(ev, r),
                            amount_cents=amount, flow="dividende", isin=header_isin(det) or icon_isin(ev),
                            instrument=first(r, "Actif", "Actifs") or ev.get("title"),
                            quantity=number(first(r, "Actions", "Titres")), tax_cents=tax))
        elif et == "SSP_CORPORATE_ACTION_CASH_NON_DIVIDEND" or et in DIVIDENDS:
            # Turbo/warrant paid out (exercise, knock-out): the icon is the underlying's, so find the
            # product held on it; when no quantity is given, the whole line is closed.
            qty = number(first(r, "Actions retirées", "Actions"))
            under = icon_isin(ev)
            held = bought_by_icon.get(under or "", {})
            isin = next((i for i, q in held.items() if qty and abs(q - qty) < 1e-6), None)
            isin = isin or next((i for i, q in held.items() if q > 1e-6), None)
            if isin:
                qty = qty if qty is not None else held[isin]
                held[isin] -= qty
            rows.append(Row(**base, account_id=cash_account(ev), holding_account_id=holding(ev, r),
                            amount_cents=amount, flow="vente_titre", isin=isin,
                            instrument=first(r, "Actif") or ev.get("title"), quantity=qty, tax_cents=tax))
        elif et == "SSP_CORPORATE_ACTION_NO_CASH":
            isin = icon_isin(ev)
            rows.append(Row(**base, account_id=held_in(isin), holding_account_id=held_in(isin), amount_cents=0,
                            flow="operation_titres", isin=isin, instrument=first(r, "Actif"),
                            quantity=number(first(r, "Actions ajoutées", "Actions"))))
        elif et == "SSP_SECURITIES_TRANSFER_INCOMING" and (r.get("BIC") or "").startswith("TRBK"):
            continue  # moved from Trade Republic Germany to France: the shares were already counted
        elif et == "SSP_SECURITIES_TRANSFER_INCOMING":
            rows.append(Row(**base, account_id="tr_cto", holding_account_id="tr_cto", amount_cents=0,
                            flow="transfert_titres", isin=icon_isin(ev), instrument=first(r, "Actif"),
                            quantity=number(first(r, "Actions"))))
        elif et == "PEA_SAVINGS_PLAN_PAY_IN":
            # Cash leaves the main account for the PEA cash account: two sides of one internal transfer.
            rows.append(Row(**base, account_id="tr_especes", amount_cents=amount, flow="interne",
                            counterparty="PEA Trade Republic"))
            rows.append(Row(**{**base, "id": ev["id"] + ":pea"}, account_id="tr_pea", amount_cents=-amount,
                            flow="interne", counterparty="Trade Republic espèces"))
        elif et is None and "PEA" in (ev.get("title") or "").upper():
            rows.append(Row(**base, account_id="tr_pea", amount_cents=amount, flow="interne"))
        else:
            unknown[et or ev.get("title") or "?"] += 1

    positions = []
    for sec_no, portfolio in (dump.get("portfolios") or {}).items():
        acc = "tr_cto" if sec_no == cto_no else "tr_pea"
        for cat in (portfolio or {}).get("categories", []):
            for p in cat.get("positions", []):
                qty = number(p.get("netSize"))
                if qty:
                    positions.append({"account_id": acc, "isin": p.get("isin") or p.get("instrumentId"),
                                      "name": p.get("name"), "quantity": qty,
                                      "avg_cost": number(p.get("averageBuyIn")), "kind": instrument_kind(p)})
    cash = {"tr_especes": cents(c["amount"]) for c in dump.get("cash") or [] if c.get("accountNumber") == main_cash}
    return Parsed(rows=rows, positions=positions, cash=cash, unknown=unknown)


def raw_json(row: Row) -> str:
    return json.dumps(row.raw, ensure_ascii=False, separators=(",", ":"))
