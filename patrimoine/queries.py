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


# Grouping of the accounts on the home page (PC and phone share it).
ACCOUNT_GROUPS = {"PEA": "Bourse", "Compte-titres": "Bourse", "PEG Airbus": "Épargne salariale", "Livret CMB": "Livrets",
                  "Livret Jeune": "Livrets", "Trade Republic espèces": "Liquidités", "CMB courant": "Liquidités"}


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


def positions(con: sqlite3.Connection, replayed: tuple | None = None) -> pd.DataFrame:
    """Current lines with our cost basis (PMP, fees included) and the latest price.
    `replayed`: result of `portfolio.replay(con)` already computed by the caller."""
    book, prices = replayed or portfolio.replay(con)
    names = dict(con.execute("SELECT isin, name FROM instruments"))
    today = pd.Timestamp.today().normalize()
    out = []
    for (acc, isin), line in book.lines.items():
        if line.quantity > 1e-6:
            out.append((acc, isin, line.quantity, line.cost))
    for isin, qty in portfolio.peg_without_history(con):
        out.append(("peg_airbus", isin, qty, None))
    rows = []
    for acc, isin, qty, cost in out:
        price = prices.get(isin, today)
        value = qty * price if price is not None else None
        rows.append({
            "account": ACCOUNT_LABELS.get(acc, acc), "isin": isin, "name": names.get(isin) or isin,
            "quantity": qty, "unit_cost": cost / qty if cost else float("nan"), "price": price, "value": value,
            "cost": cost if cost else float("nan"),
            "gain": value - cost if value is not None and cost else float("nan"),
            "gain_pct": (value / cost - 1) if value is not None and cost else float("nan"),
        })
    df = pd.DataFrame(rows)
    if not df.empty:
        df["weight"] = df["value"] / df["value"].sum()
        df = df.sort_values("value", ascending=False)
    return df


def realised(con: sqlite3.Connection, replayed: tuple | None = None) -> pd.DataFrame:
    book, _ = replayed or portfolio.replay(con)
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
    df["merchant"] = (df["counterparty"].fillna(df["label"]).str.replace(r"^((vers|VIR|PRLV|WERO|INST)\s+)+", "", regex=True)
                      .str.strip())
    df["account"] = df["account_id"].map(ACCOUNT_LABELS)
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    return df


def income(con: sqlite3.Connection) -> pd.DataFrame:
    """Every income line (positive), with the category that applies. Internal transfers are a separate
    flow ('interne') and never show up here."""
    df = pd.read_sql_query(
        "SELECT id, date, account_id, counterparty, label, amount_cents, category, category_override"
        " FROM transactions WHERE flow = 'revenu' ORDER BY date DESC", con, parse_dates=["date"])
    df["amount"] = df.pop("amount_cents") / 100
    df["category"] = df["category_override"].fillna(df["category"])
    df["merchant"] = (df["counterparty"].fillna(df["label"]).str.replace(r"^((vers|VIR|PRLV|WERO|INST)\s+)+", "", regex=True)
                      .str.strip())
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


def investment_income(con: sqlite3.Connection) -> pd.DataFrame:
    """Interest and dividends actually received, by flow and account, EUR."""
    df = pd.read_sql_query(
        "SELECT flow, COALESCE(holding_account_id, account_id) AS account_id, SUM(amount_cents) AS cents"
        " FROM transactions WHERE flow IN ('interets', 'dividende') GROUP BY flow, account_id", con)
    df["amount"] = df.pop("cents") / 100
    df["account"] = df["account_id"].map(ACCOUNT_LABELS).fillna(df["account_id"])
    return df


def account_open_dates(con: sqlite3.Connection) -> dict[str, str]:
    """Earliest transaction date per account (and per holding account), to judge the PEA/PEG 5-year mark."""
    out: dict[str, str] = {}
    for acc, d in con.execute(
            "SELECT acc, MIN(date) FROM (SELECT account_id AS acc, date FROM transactions UNION ALL"
            " SELECT holding_account_id AS acc, date FROM transactions WHERE holding_account_id IS NOT NULL)"
            " GROUP BY acc"):
        out[acc] = d
    return out


# Ongoing charges (TER) of Jules's funds, % per year, from their factsheets: to check against the KID.
TER = {
    "FR0011550185": 0.0015,   # Amundi PEA S&P 500
    "FR0010342592": 0.0060,   # Amundi Nasdaq-100 Daily 2x Leveraged
    "IE00BHZRR030": 0.0009,   # Franklin FTSE Korea
    "IE000YU9K6K2": 0.0055,   # VanEck Space Innovators
    "IE000KHX9DX6": 0.0055,   # VanEck Rare Earth and Strategic Metals
}


def fees_by_year(con: sqlite3.Connection) -> pd.DataFrame:
    """Per year, EUR: brokerage fees on trades, bank fees, and the funds' ongoing charges estimated on each line's
    average value that year (TER table above; lines without a known TER are left out)."""
    trades = pd.read_sql_query(
        "SELECT substr(date, 1, 4) AS year, SUM(COALESCE(fees_cents, 0)) / 100.0 AS courtage, COUNT(*) AS ordres"
        " FROM transactions WHERE flow IN ('achat_titre', 'vente_titre') GROUP BY year", con).set_index("year")
    bank = pd.read_sql_query(
        "SELECT substr(date, 1, 4) AS year, -SUM(amount_cents) / 100.0 AS banque FROM transactions"
        " WHERE flow = 'frais' GROUP BY year", con).set_index("year")
    out = trades.join(bank, how="outer")
    book, prices = portfolio.replay(con)
    held = pd.read_sql_query("SELECT date, isin, COALESCE(holding_account_id, account_id) AS acc, flow, quantity"
                             " FROM transactions WHERE isin IS NOT NULL AND quantity IS NOT NULL ORDER BY date", con,
                             parse_dates=["date"])
    ter = {}
    for isin, rate in TER.items():
        h = held[held["isin"] == isin]
        if h.empty:
            continue
        sign = h.flow.map(lambda f: -1 if f == "vente_titre" else 1)
        qty = (h.quantity * sign).groupby(h.date).sum().cumsum()
        days = pd.date_range(qty.index.min(), pd.Timestamp.today().normalize())
        qty = qty.reindex(days).ffill().clip(lower=0)
        px = pd.Series({d: prices.get(isin, d) for d in days[::7]}, dtype=float).reindex(days).ffill().bfill()
        daily = (qty * px * rate / 365).groupby(days.year).sum()
        for y, v in daily.items():
            ter[str(y)] = ter.get(str(y), 0.0) + float(v)
    out = out.join(pd.Series(ter, name="frais_fonds"), how="outer").fillna(0.0)
    out["total"] = out.courtage + out.banque + out.frais_fonds
    return out.sort_index()
