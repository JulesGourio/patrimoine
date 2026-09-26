"""Alert rules checked after each sync. Each rule fires at most once per key (day, month, level).

Kinds:
- ``baisse_ligne`` / ``hausse_ligne``: every held line moving by ``threshold`` % over ``window_days``;
  with ``isin`` set, only that line.
- ``baisse_portefeuille``: current holdings losing ``threshold`` % over ``window_days`` (flows excluded:
  today's quantities valued at both dates).
- ``seuil_bas`` / ``seuil_haut``: an ISIN's price crossing ``threshold`` EUR.
- ``concentration``: a line above ``threshold`` % of invested wealth (PEG included).
- ``budget``: a category's spending this month above its budget (``budgets`` table); ``target`` limits
  it to one category.
"""
from __future__ import annotations

import math
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

import pandas as pd

from . import db, portfolio, queries

DEFAULT_RULES = [
    ("baisse_ligne", None, None, 8.0, 1, "Une ligne perd 8 % en une séance"),
    ("hausse_ligne", None, None, 10.0, 1, "Une ligne gagne 10 % en une séance"),
    ("baisse_portefeuille", None, None, 5.0, 7, "Le portefeuille perd 5 % sur 7 jours"),
    ("concentration", None, None, 35.0, None, "Une ligne dépasse 35 % du patrimoine investi"),
    ("budget", None, None, 100.0, None, "Budget mensuel dépassé"),
]


@dataclass
class Fired:
    rule_id: int
    key: str
    title: str
    message: str
    priority: int = 3


def seed(con: sqlite3.Connection) -> None:
    if db.get_meta(con, "alerts_seeded"):
        return
    con.executemany(
        "INSERT INTO alert_rules (kind, isin, target, threshold, window_days, note) VALUES (?, ?, ?, ?, ?, ?)",
        DEFAULT_RULES)
    seed_budgets(con)
    db.set_meta(con, "alerts_seeded", True)
    con.commit()


def seed_budgets(con: sqlite3.Connection) -> None:
    """Starting budgets: 12-month average per category plus 15 %, rounded up to 10 EUR."""
    sp = queries.spending(con)
    if sp.empty:
        return
    this_month = pd.Timestamp.today().to_period("M").to_timestamp()
    last12 = sp[(sp.month < this_month) & (sp.month >= this_month - pd.DateOffset(months=12))]
    months = max(last12.month.nunique(), 1)
    for cat, total in last12.groupby("category")["amount"].sum().items():
        if cat in ("Divers", "Retraits d'espèces", "Impôts et taxes") or total <= 0:
            continue
        limit = math.ceil(total / months * 1.15 / 10) * 10
        con.execute("INSERT OR IGNORE INTO budgets (category, monthly_limit_cents) VALUES (?, ?)", (cat, limit * 100))


def _series(prices: portfolio.Prices, isin: str) -> pd.Series | None:
    s = prices.series.get(isin)
    return s if s is not None and len(s) > 2 else None


def _change(prices: portfolio.Prices, isin: str, days: int, today: pd.Timestamp) -> tuple[float, float] | None:
    """(last price, % change over ``days`` trading sessions), on Yahoo closes."""
    s = _series(prices, isin)
    if s is None:
        return None
    s = s[s.index <= today]
    if len(s) <= days:
        return None
    now, before = float(s.iloc[-1]), float(s.iloc[-1 - days])
    return now, (now / before - 1) * 100 if before else 0.0


def check(con: sqlite3.Connection, today: date | None = None) -> list[Fired]:
    today_ts = pd.Timestamp(today or date.today())
    book, prices = portfolio.replay(con)
    names = dict(con.execute("SELECT isin, name FROM instruments"))
    held: dict[str, float] = {}
    for (_, isin), line in book.lines.items():
        if line.quantity > 1e-6:
            held[isin] = held.get(isin, 0) + line.quantity
    for isin, qty in portfolio.peg_without_history(con):
        held[isin] = held.get(isin, 0) + qty
    month = today_ts.strftime("%Y-%m")
    fired: list[Fired] = []
    rules = con.execute("SELECT id, kind, isin, target, threshold, window_days FROM alert_rules WHERE active = 1")
    for rid, kind, isin, target, threshold, window in rules.fetchall():
        window = window or 1
        if kind in ("baisse_ligne", "hausse_ligne"):
            for i in [isin] if isin else list(held):
                ch = _change(prices, i, window, today_ts)
                if not ch:
                    continue
                price, pct = ch
                if (kind == "baisse_ligne" and pct <= -threshold) or (kind == "hausse_ligne" and pct >= threshold):
                    word = "chute" if pct < 0 else "bondit"
                    fired.append(Fired(rid, f"{i}:{today_ts.date()}", f"{names.get(i) or i} {word} de {pct:+.1f} %",
                                       f"{names.get(i) or i} : {price:.2f} € ({pct:+.1f} % sur {window} séance(s)).",
                                       4 if pct < 0 else 3))
        elif kind == "baisse_portefeuille":
            now = before = 0.0
            for i, qty in held.items():
                s = _series(prices, i)
                if s is None:
                    continue
                s = s[s.index <= today_ts]
                past = s[s.index <= today_ts - timedelta(days=window)]
                if s.empty or past.empty:
                    continue
                now += qty * float(s.iloc[-1])
                before += qty * float(past.iloc[-1])
            if before:
                pct = (now / before - 1) * 100
                if pct <= -threshold:
                    fired.append(Fired(rid, f"{today_ts.date()}", f"Portefeuille {pct:+.1f} % sur {window} jours",
                                       f"Tes lignes valent {now:,.0f} € contre {before:,.0f} € il y a {window} jours "
                                       f"({now - before:+,.0f} €).".replace(",", " "), 4))
        elif kind in ("seuil_bas", "seuil_haut") and isin:
            s = _series(prices, isin)
            if s is None:
                continue
            price = float(s[s.index <= today_ts].iloc[-1])
            if (kind == "seuil_bas" and price <= threshold) or (kind == "seuil_haut" and price >= threshold):
                sens = "sous" if kind == "seuil_bas" else "au-dessus de"
                fired.append(Fired(rid, f"{today_ts.date()}", f"{names.get(isin) or isin} {sens} {threshold:.2f} €",
                                   f"Cours : {price:.2f} €.", 4))
        elif kind == "concentration":
            values = {}
            for i, qty in held.items():
                p = prices.get(i, today_ts)
                if p:
                    values[i] = qty * p
            total = sum(values.values())
            for i, v in values.items():
                if total and v / total * 100 >= threshold:
                    level = int(v / total * 100 // 5 * 5)  # re-alert only when it crosses the next 5 % step
                    fired.append(Fired(rid, f"{i}:{level}", f"{names.get(i) or i} pèse {v / total:.0%} du portefeuille",
                                       f"{v:,.0f} € sur {total:,.0f} € investis. Seuil : {threshold:.0f} %."
                                       .replace(",", " "), 3))
        elif kind == "budget":
            sp = queries.spending(con)
            sp = sp[sp.month == today_ts.to_period("M").to_timestamp()]
            spent = sp.groupby("category")["amount"].sum()
            for cat, limit in con.execute("SELECT category, monthly_limit_cents / 100.0 FROM budgets"):
                if target and cat != target:
                    continue
                used = float(spent.get(cat, 0.0))
                if limit and used >= limit * threshold / 100:
                    fired.append(Fired(rid, f"{cat}:{month}", f"Budget {cat} dépassé",
                                       f"{used:.0f} € dépensés ce mois-ci pour un budget de {limit:.0f} €.", 3))
    return fired


def run(con: sqlite3.Connection, send: bool = True, today: date | None = None) -> list[Fired]:
    """Check every rule, notify what is new, remember it. Returns what was newly fired."""
    from . import notify

    seed(con)
    new = []
    for f in check(con, today):
        if con.execute("SELECT 1 FROM alert_events WHERE rule_id = ? AND key = ?", (f.rule_id, f.key)).fetchone():
            continue
        sent = notify.send(f.title, f.message, priority=f.priority, tags=["chart_with_downwards_trend"]
                           if f.priority >= 4 else ["bell"]) if send else False
        con.execute("INSERT INTO alert_events (rule_id, key, triggered_at, message, sent_to) VALUES (?, ?, ?, ?, ?)",
                    (f.rule_id, f.key, db.now_iso(), f"{f.title} — {f.message}", sent or None))
        new.append(f)
    con.commit()
    return new
