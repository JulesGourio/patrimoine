"""Read models for the dashboard (and later the MCP server): plain DataFrames out of the database."""
from __future__ import annotations

import sqlite3

import pandas as pd

from . import db, portfolio
from .categories import CATEGORIES

ACCOUNT_LABELS = {
    "tr_especes": "Trade Republic espèces",
    "tr_cto": "Compte-titres",
    "tr_pea": "PEA",
    "peg_airbus": "PEG Airbus",
    "cmb_courant": "CMB courant",
    "cmb_livret_jeune": "Livret Jeune",
    "cmb_livret_a": "Livret CMB",
}


def history(con: sqlite3.Connection) -> pd.DataFrame:
    """Daily value per account, in EUR (from the valuations table, see portfolio.store)."""
    df = pd.read_sql_query(
        "SELECT date, account_id, cash_cents, securities_cents, cost_cents, realised_cents, deposits_cents"
        " FROM valuations ORDER BY date", con, parse_dates=["date"])
    for c in ("cash", "securities", "cost", "realised", "deposits"):
        df[c] = df.pop(f"{c}_cents") / 100
    df["value"] = df["cash"] + df["securities"]
    df["account"] = df["account_id"].map(ACCOUNT_LABELS).fillna(df["account_id"])
    return df


def positions(con: sqlite3.Connection) -> pd.DataFrame:
    """Current lines with our cost basis (PMP, fees included) and the latest price."""
    book, prices = portfolio.replay(con)
    names = dict(con.execute("SELECT isin, name FROM instruments"))
    today = pd.Timestamp.today().normalize()
    out = []
    for (acc, isin), line in book.lines.items():
        if line.quantity > 1e-6:
            out.append((acc, isin, line.quantity, line.cost))
    for isin, qty in con.execute("SELECT isin, quantity FROM positions WHERE account_id = 'peg_airbus'"):
        out.append(("peg_airbus", isin, qty, None))
    rows = []
    for acc, isin, qty, cost in out:
        price = prices.get(isin, today)
        value = qty * price if price is not None else None
        rows.append({
            "account": ACCOUNT_LABELS.get(acc, acc), "isin": isin, "name": names.get(isin) or isin,
            "quantity": qty, "unit_cost": cost / qty if cost else None, "price": price, "value": value,
            "cost": cost, "gain": value - cost if value is not None and cost else None,
            "gain_pct": (value / cost - 1) if value is not None and cost else None,
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["weight"] = df["value"] / df["value"].sum()
        df = df.sort_values("value", ascending=False)
    return df


def realised(con: sqlite3.Connection) -> pd.DataFrame:
    book, _ = portfolio.replay(con)
    df = pd.DataFrame([{
        "date": pd.Timestamp(r.date), "account": ACCOUNT_LABELS.get(r.account_id, r.account_id), "name": r.name,
        "isin": r.isin, "quantity": r.quantity, "proceeds": r.proceeds, "cost": r.cost, "gain": r.gain,
    } for r in book.realised])
    return df.sort_values("date", ascending=False) if not df.empty else df


def taxes(con: sqlite3.Connection) -> pd.DataFrame:
    book, _ = portfolio.replay(con)
    return pd.DataFrame(portfolio.tax_summary(con, book)).T


def spending(con: sqlite3.Connection) -> pd.DataFrame:
    """Every spending line (refunds included, positive), with the category that applies."""
    df = pd.read_sql_query(
        "SELECT id, date, account_id, counterparty, label, amount_cents, category, category_override"
        " FROM transactions WHERE flow = 'depense' ORDER BY date DESC", con, parse_dates=["date"])
    df["amount"] = -df.pop("amount_cents") / 100
    df["category"] = df["category_override"].fillna(df["category"])
    df["merchant"] = df["counterparty"].fillna(df["label"])
    df["account"] = df["account_id"].map(ACCOUNT_LABELS)
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df


def flows_by_month(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query("SELECT date, flow, amount_cents FROM transactions", con, parse_dates=["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df.pivot_table(index="month", columns="flow", values="amount_cents", aggfunc="sum", fill_value=0) / 100


def set_category(con: sqlite3.Connection, tx_id: str, category: str | None, merchant_rule: str | None = None) -> None:
    """Fix one line by hand; with ``merchant_rule``, also teach the rule for every line of that merchant."""
    if category is not None and category not in CATEGORIES:
        raise ValueError(category)
    con.execute("UPDATE transactions SET category_override = ? WHERE id = ?", (category, tx_id))
    if merchant_rule and category:
        db.set_rule(con, merchant_rule, category)
        con.execute(
            "UPDATE transactions SET category = ? WHERE flow = 'depense' AND UPPER(counterparty) = UPPER(?)",
            (category, merchant_rule))
    con.commit()


def last_sync(con: sqlite3.Connection) -> str | None:
    return db.get_meta(con, "last_sync_tr")
