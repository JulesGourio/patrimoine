"""Replay the transactions: holdings, cost basis, realised gains and a daily valuation per account.

Cost basis follows the French rule for securities (prix moyen pondéré): buying fees are part of the
cost, a sale takes out cost in proportion to the shares sold. Trade Republic's own averageBuyIn is
not used (it ignores splits: 1 281 EUR per share on the Nasdaq 2x after its 1-for-200 split).
"""
from __future__ import annotations

import logging
import math
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

import pandas as pd

from .categories import NON_CASH_FLOWS

log = logging.getLogger(__name__)

IN_FLOWS = {"achat_titre", "saveback", "titres_offerts", "transfert_titres"}
OUT_FLOWS = {"vente_titre"}
CASH_ACCOUNTS = {"tr_especes", "tr_pea", "cmb_courant", "cmb_livret_a", "cmb_livret_jeune"}
SPLIT_TOLERANCE = 1.25  # a trade/close ratio beyond this means Yahoo's scale differs (split, wrong line)


@dataclass
class Line:
    quantity: float = 0.0
    cost: float = 0.0  # EUR, fees included

    @property
    def unit_cost(self) -> float | None:
        return self.cost / self.quantity if self.quantity > 1e-9 else None


@dataclass
class Realised:
    date: str
    account_id: str
    isin: str
    name: str | None
    quantity: float
    proceeds: float
    cost: float

    @property
    def gain(self) -> float:
        return self.proceeds - self.cost


@dataclass
class Book:
    lines: dict[tuple[str, str], Line] = field(default_factory=lambda: defaultdict(Line))
    realised: list[Realised] = field(default_factory=list)
    last_trade: dict[str, tuple[str, float]] = field(default_factory=dict)  # isin -> (date, unit price)

    def apply(self, row: sqlite3.Row) -> None:
        flow, isin, qty = row["flow"], row["isin"], row["quantity"]
        if not isin or not qty or flow not in IN_FLOWS | OUT_FLOWS | {"operation_titres"}:
            return
        key = (row["holding_account_id"] or row["account_id"], isin)
        line = self.lines[key]
        value = abs(row["amount_cents"]) / 100
        if flow == "operation_titres":  # split: more shares, same cost
            line.quantity += qty
            return
        if flow in IN_FLOWS:
            line.quantity += qty
            line.cost += value
            if value and flow == "achat_titre":
                fees = (row["fees_cents"] or 0) / 100
                self.last_trade[isin] = (row["date"], (value - fees) / qty)
            return
        # Sale, exercise or knock-out
        sold = min(qty, line.quantity) if line.quantity > 0 else qty
        cost_out = line.cost * (sold / line.quantity) if line.quantity > 1e-9 else 0.0
        self.realised.append(Realised(row["date"], key[0], isin, row["label"], sold, value, cost_out))
        line.quantity -= sold
        line.cost -= cost_out
        if line.quantity < 1e-6:
            line.quantity, line.cost = 0.0, 0.0
        if value and sold:
            fees = (row["fees_cents"] or 0) / 100
            self.last_trade[isin] = (row["date"], (value + fees) / sold)


def rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    con.row_factory = sqlite3.Row
    return con.execute("SELECT * FROM transactions ORDER BY date, json_extract(raw_json, '$.timestamp'), id").fetchall()


# ---------- prices ----------

def trade_prices(txs: list[sqlite3.Row]) -> dict[str, list[tuple[pd.Timestamp, float]]]:
    out: dict[str, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    for r in txs:
        if r["flow"] in ("achat_titre", "vente_titre") and r["isin"] and r["quantity"] and r["amount_cents"]:
            fees = (r["fees_cents"] or 0) / 100
            value = abs(r["amount_cents"]) / 100
            unit = (value - fees if r["flow"] == "achat_titre" else value + fees) / r["quantity"]
            out[r["isin"]].append((pd.Timestamp(r["date"]), unit))
    return out


class Prices:
    """EUR price of an ISIN on a day: Yahoo close, rescaled when needed, else the last trade price."""

    def __init__(self, con: sqlite3.Connection, txs: list[sqlite3.Row]):
        self.series: dict[str, pd.Series] = {}
        for isin, d, close in con.execute("SELECT isin, date, close FROM prices ORDER BY isin, date"):
            self.series.setdefault(isin, {})[pd.Timestamp(d)] = close  # type: ignore[index]
        self.series = {k: pd.Series(v).sort_index() for k, v in self.series.items()}  # type: ignore[arg-type]
        self.trades = trade_prices(txs)
        splits: dict[str, list[pd.Timestamp]] = defaultdict(list)
        self.split_ratio: dict[tuple[str, pd.Timestamp], float] = {}
        held: dict[str, float] = defaultdict(float)
        for r in txs:
            if not r["isin"] or not r["quantity"]:
                continue
            if r["flow"] == "operation_titres":
                day = pd.Timestamp(r["date"])
                splits[r["isin"]].append(day)
                if held[r["isin"]] > 1e-9:
                    self.split_ratio[(r["isin"], day)] = (held[r["isin"]] + r["quantity"]) / held[r["isin"]]
                held[r["isin"]] += r["quantity"]
            elif r["flow"] in IN_FLOWS:
                held[r["isin"]] += r["quantity"]
            elif r["flow"] in OUT_FLOWS:
                held[r["isin"]] = max(held[r["isin"]] - r["quantity"], 0.0)
        self.factors: dict[str, list[tuple[pd.Timestamp, float]]] = {}
        for isin, s in self.series.items():
            self.factors[isin] = self._calibrate(isin, s, sorted(splits.get(isin, [])))

    def _calibrate(self, isin: str, s: pd.Series, splits: list[pd.Timestamp]) -> list[tuple[pd.Timestamp, float]]:
        """One scale factor per period between splits, from our own trade prices against Yahoo's close.

        Yahoo back-adjusts closes for splits, while our quantities before a split are the old ones;
        the factor puts the price back on the scale of the shares held at the time.
        """
        bounds = [pd.Timestamp.min] + splits + [pd.Timestamp.max]
        out = []
        for lo, hi in zip(bounds, bounds[1:]):
            ratios = []
            for d, unit in self.trades.get(isin, []):
                if lo <= d < hi:
                    close = s.asof(d)
                    if close and not math.isnan(close):
                        ratios.append(unit / close)
            f = statistics.median(ratios) if ratios else 1.0
            # A split ahead of this period: prefer the exact ratio when the trades agree with it.
            later = [self.split_ratio.get((isin, d), 1.0) for d in splits if d >= hi]
            exact = math.prod(later) if later else None
            if exact and exact != 1.0 and abs(math.log(f / exact)) < math.log(SPLIT_TOLERANCE):
                f = exact
            elif 1 / SPLIT_TOLERANCE < f < SPLIT_TOLERANCE:
                f = 1.0
            elif ratios:
                log.info("%s: prix Yahoo remis à l'échelle ×%.4g à partir de %s", isin, f, lo.date())
            out.append((lo, f))
        return out

    def get(self, isin: str, day: pd.Timestamp) -> float | None:
        s = self.series.get(isin)
        if s is not None and not s.empty and day >= s.index[0]:
            close = s.asof(day)
            factor = next(f for lo, f in reversed(self.factors[isin]) if day >= lo)
            return float(close) * factor
        past = [p for d, p in self.trades.get(isin, []) if d <= day]
        return past[-1] if past else None


def peg_without_history(con: sqlite3.Connection) -> list[tuple[str, float]]:
    """PEG lines typed by hand, used only while no Amundi statement has been imported."""
    if con.execute("SELECT 1 FROM transactions WHERE holding_account_id = 'peg_airbus' LIMIT 1").fetchone():
        return []
    return [tuple(r) for r in con.execute("SELECT isin, quantity FROM positions WHERE account_id = 'peg_airbus'")]


def replay(con: sqlite3.Connection) -> tuple[Book, Prices]:
    """Holdings and realised gains as of today, without the daily valuation."""
    txs = rows(con)
    book = Book()
    for r in txs:
        book.apply(r)
    return book, Prices(con, txs)


# ---------- daily valuation ----------

def valuations(con: sqlite3.Connection, end: date | None = None) -> tuple[pd.DataFrame, Book]:
    """One row per (day, account): cash, market value, remaining cost, realised gains, net deposits (EUR)."""
    txs = rows(con)
    if not txs:
        return pd.DataFrame(), Book()
    prices = Prices(con, txs)
    peg = peg_without_history(con)
    start, end = date.fromisoformat(txs[0]["date"]), end or date.today()
    by_day: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for r in txs:
        by_day[r["date"]].append(r)

    book = Book()
    cash: dict[str, float] = defaultdict(float)
    deposits: dict[str, float] = defaultdict(float)
    out = []
    day = start
    while day <= end:
        for r in by_day.get(day.isoformat(), []):
            book.apply(r)
            if r["account_id"] in CASH_ACCOUNTS and r["flow"] not in NON_CASH_FLOWS:
                cash[r["account_id"]] += r["amount_cents"] / 100
                if r["flow"] == "interne":
                    deposits[r["account_id"]] += r["amount_cents"] / 100
        ts = pd.Timestamp(day)
        value: dict[str, float] = defaultdict(float)
        cost: dict[str, float] = defaultdict(float)
        for (acc, isin), line in book.lines.items():
            if line.quantity > 1e-9:
                p = prices.get(isin, ts)
                value[acc] += line.quantity * (p if p is not None else (line.unit_cost or 0))
                cost[acc] += line.cost
        for isin, qty in peg:
            p = prices.get(isin, ts)
            if p is not None:
                value["peg_airbus"] += qty * p
        realised: dict[str, float] = defaultdict(float)
        for x in book.realised:
            realised[x.account_id] += x.gain
        for acc in sorted(set(cash) | set(value) | set(realised) | {"tr_cto", "tr_pea"}):
            out.append({"date": day.isoformat(), "account_id": acc, "cash": round(cash[acc], 2),
                        "securities": round(value[acc], 2), "cost": round(cost[acc], 2),
                        "realised": round(realised[acc], 2), "deposits": round(deposits[acc], 2)})
        day += timedelta(days=1)
    return anchor_to_balances(con, pd.DataFrame(out), txs), book


def anchor_to_balances(con: sqlite3.Connection, df: pd.DataFrame, txs: list[sqlite3.Row]) -> pd.DataFrame:
    """Shift each account's cash so it matches the latest balance its bank reported (or Jules typed).

    Bank feeds only reach back ~13 months, so the running sum of the lines misses the opening balance;
    the reported balance fixes it. Days before the first known line of such an account are dropped.
    """
    first_line: dict[str, str] = {}
    for r in txs:
        first_line.setdefault(r["account_id"], r["date"])
    latest = con.execute(
        "SELECT b.account_id, b.date, b.cash_cents FROM balances b JOIN (SELECT account_id, MAX(date) d FROM"
        " balances WHERE cash_cents IS NOT NULL GROUP BY account_id) m ON m.account_id = b.account_id AND m.d = b.date"
    ).fetchall()
    for acc, d, cents in latest:
        mask = df.account_id == acc
        if not mask.any():
            # No line at all (Livret Jeune): flat since the bank feed begins.
            start = first_line.get(acc) or first_line.get("cmb_courant") or d
            days = pd.date_range(max(start, df.date.min()), df.date.max()).strftime("%Y-%m-%d")
            df = pd.concat([df, pd.DataFrame({"date": days, "account_id": acc, "cash": 0.0, "securities": 0.0,
                                              "cost": 0.0, "realised": 0.0, "deposits": 0.0})])
            mask = df.account_id == acc
        at = df[mask & (df.date <= d)].sort_values("date")
        if at.empty:
            continue
        offset = cents / 100 - at.iloc[-1].cash
        if abs(offset) > 0.005:
            df.loc[mask, "cash"] = (df.loc[mask, "cash"] + offset).round(2)
            if acc in first_line:
                df = df[~(mask & (df.date < first_line[acc]))]
    return df.sort_values(["date", "account_id"]).reset_index(drop=True)


def store(con: sqlite3.Connection, df: pd.DataFrame) -> None:
    con.execute("DELETE FROM valuations")
    con.executemany(
        "INSERT INTO valuations (date, account_id, cash_cents, securities_cents, cost_cents, realised_cents,"
        " deposits_cents) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(r.date, r.account_id, round(r.cash * 100), round(r.securities * 100), round(r.cost * 100),
          round(r.realised * 100), round(r.deposits * 100)) for r in df.itertuples()],
    )
    con.commit()


# ---------- tax ----------

def _apply_carry(carry: list[tuple[int, float]], year: int, gain: float) -> tuple[list[tuple[int, float]], float, float]:
    """Un an de plus-values nettes `gain` : (reports restants, moins-values imputées, plus-values imposables).
    Les moins-values de plus de dix ans sont écartées ; une perte nette de l'année s'ajoute au report."""
    carry = [(yr, amt) for yr, amt in carry if year - yr <= 10]
    if gain < 0:
        carry.append((year, -gain))
        gain = 0.0
    used = 0.0
    while gain > 0 and carry:
        yr, amt = carry[0]
        take = min(amt, gain)
        gain, used = gain - take, used + take
        carry = [(yr, amt - take)] + carry[1:] if amt > take else carry[1:]
    return carry, used, gain


def carry_into(plus_values_by_year: dict[int, float], year: int) -> float:
    """Moins-values reportables utilisables en `year` à partir des plus-values nettes des années antérieures
    (celles de plus de dix ans sont écartées), pour une année sans ligne dans `tax_summary`."""
    carry: list[tuple[int, float]] = []
    for yr in sorted(k for k in plus_values_by_year if k < year):
        carry, _, _ = _apply_carry(carry, yr, plus_values_by_year[yr])
    return sum(a for yr, a in carry if year - yr <= 10)


def tax_summary(con: sqlite3.Connection, book: Book) -> dict[int, dict[str, float]]:
    """Per year, what goes on the French return for the compte-titres (PFU estimate, check the IFU).

    PEA gains are not taxed while they stay in the PEA; only compte-titres gains, dividends and
    Trade Republic interest are counted here.
    """
    years: dict[int, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for x in book.realised:
        if x.account_id == "tr_cto":
            years[int(x.date[:4])]["plus_values"] += x.gain
    for d, flow, amount, tax, acc in con.execute(
            "SELECT date, flow, amount_cents, tax_cents, COALESCE(holding_account_id, account_id)"
            " FROM transactions WHERE flow IN ('dividende', 'interets')"):
        if flow == "dividende" and acc == "tr_pea":
            continue
        y = years[int(d[:4])]
        y["dividendes" if flow == "dividende" else "interets"] += (amount + (tax or 0)) / 100  # gross
        y["deja_preleve"] += (tax or 0) / 100
    # Net capital losses carry forward over the next ten years (moins-values reportables).
    carry: list[tuple[int, float]] = []
    for year in sorted(years):
        y = years[year]
        carry, used, gain = _apply_carry(carry, year, y["plus_values"])
        y["moins_values_imputees"] = used
        y["plus_values_imposables"] = gain
        y["moins_values_reportables"] = sum(a for _, a in carry)
        base = gain + y["dividendes"] + y["interets"]
        y["pfu_estime"] = base * 0.30 - y["deja_preleve"]
    return {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in sorted(years.items())}
