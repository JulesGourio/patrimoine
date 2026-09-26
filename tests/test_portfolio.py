import json
from datetime import date

import pytest

from patrimoine import db, portfolio


def con_with(rows, prices=()):
    con = db.connect(":memory:")
    db.init(con)
    for i, r in enumerate(rows):
        r = {"id": f"t{i}", "account_id": "tr_especes", "holding_account_id": "tr_cto", "fees_cents": 0, **r}
        r["raw_json"] = json.dumps({"timestamp": r.pop("ts", r["date"] + "T12:00:00.000+0000")})
        con.execute("INSERT OR IGNORE INTO instruments (isin) VALUES (?)", (r["isin"],))
        cols = ",".join(r)
        con.execute(f"INSERT INTO transactions ({cols}) VALUES ({','.join('?' * len(r))})", list(r.values()))
    con.executemany("INSERT INTO prices (isin, date, close) VALUES (?, ?, ?)", prices)
    con.commit()
    return con


def buy(d, isin, qty, total, fees=100, **kw):
    return {"date": d, "isin": isin, "flow": "achat_titre", "quantity": qty, "amount_cents": -total, "fees_cents": fees, **kw}


def sell(d, isin, qty, total, fees: int | None = 100, **kw):
    return {"date": d, "isin": isin, "flow": "vente_titre", "quantity": qty, "amount_cents": total, "fees_cents": fees, **kw}


def test_weighted_average_cost_and_realised_gain():
    con = con_with([
        buy("2025-01-02", "X", 10, 10_100),   # 100 EUR + 1 fee
        buy("2025-02-02", "X", 10, 20_100),   # 200 EUR + 1 fee
        sell("2025-03-02", "X", 5, 14_900),   # 150 EUR - 1 fee
    ])
    _, book = portfolio.valuations(con, end=date(2025, 3, 3))
    line = book.lines[("tr_cto", "X")]
    assert line.quantity == 15 and line.cost == pytest.approx(302 * 15 / 20)
    (r,) = book.realised
    assert r.proceeds == 149 and r.cost == pytest.approx(302 / 4) and r.gain == pytest.approx(149 - 75.5)


def test_same_day_buy_then_sell_follows_the_clock():
    con = con_with([
        sell("2024-09-24", "T", 700, 117_710, ts="2024-09-24T15:00:00.000+0000"),
        buy("2024-09-24", "T", 700, 117_560, ts="2024-09-24T09:00:00.000+0000"),
    ])
    _, book = portfolio.valuations(con, end=date(2024, 9, 25))
    assert book.lines[("tr_cto", "T")].quantity == 0
    assert book.realised[0].gain == pytest.approx(1177.10 - 1175.60)


def test_knock_out_closes_the_line_at_a_loss():
    con = con_with([buy("2024-06-04", "W", 700, 20_400), sell("2024-06-28", "W", 700, 70, fees=None)])
    _, book = portfolio.valuations(con, end=date(2024, 6, 29))
    assert book.realised[0].gain == pytest.approx(0.70 - 204)


def test_split_keeps_cost_and_rescales_yahoo_prices():
    # 2 shares at ~1900, then a 1-for-200 split: 398 shares added. Yahoo back-adjusts closes to ~9.5.
    con = con_with(
        [buy("2026-05-18", "N", 1, 187_740, fees=0, account_id="tr_pea", holding_account_id="tr_pea"),
         buy("2026-06-23", "N", 1, 198_120, fees=0, account_id="tr_pea", holding_account_id="tr_pea"),
         {"date": "2026-07-10", "isin": "N", "flow": "operation_titres", "quantity": 398, "amount_cents": 0,
          "account_id": "tr_pea", "holding_account_id": "tr_pea"}],
        prices=[("N", "2026-05-18", 9.387), ("N", "2026-06-23", 9.906), ("N", "2026-07-10", 9.95)],
    )
    df, book = portfolio.valuations(con, end=date(2026, 7, 10))
    line = book.lines[("tr_pea", "N")]
    assert line.quantity == 400 and line.cost == pytest.approx(3858.60)
    pea = df[df.account_id == "tr_pea"].set_index("date")
    assert pea.loc["2026-06-23", "securities"] == pytest.approx(2 * 9.906 * 200)  # exact split ratio
    assert pea.loc["2026-07-10", "securities"] == pytest.approx(400 * 9.95)


def test_cash_and_deposits():
    con = con_with([
        {"date": "2025-01-01", "flow": "interne", "amount_cents": 100_000, "isin": None, "holding_account_id": None},
        buy("2025-01-02", "X", 1, 50_100),
        {"date": "2025-01-03", "flow": "saveback", "amount_cents": 638, "isin": "X", "quantity": 0.01,
         "account_id": "tr_cto"},
    ])
    df, _ = portfolio.valuations(con, end=date(2025, 1, 3))
    cash = df[(df.account_id == "tr_especes") & (df.date == "2025-01-03")].iloc[0]
    assert cash.cash == 499 and cash.deposits == 1000


def test_losses_carry_forward():
    con = con_with([
        buy("2024-01-02", "A", 1, 100_000, fees=0), sell("2024-02-02", "A", 1, 70_000, fees=0),
        buy("2025-01-02", "B", 1, 100_000, fees=0), sell("2025-02-02", "B", 1, 150_000, fees=0),
    ])
    _, book = portfolio.valuations(con, end=date(2025, 2, 3))
    tax = portfolio.tax_summary(con, book)
    assert tax[2024]["moins_values_reportables"] == 300
    assert tax[2025]["plus_values_imposables"] == 200 and tax[2025]["pfu_estime"] == 60


def test_bank_cash_is_anchored_on_the_reported_balance():
    # The feed starts mid-history: lines sum to -50, but the bank says 191.41 today.
    con = con_with([
        {"date": "2026-09-01", "flow": "revenu", "amount_cents": 100_00, "isin": None,
         "account_id": "cmb_courant", "holding_account_id": None},
        {"date": "2026-09-10", "flow": "depense", "amount_cents": -150_00, "isin": None,
         "account_id": "cmb_courant", "holding_account_id": None},
    ])
    con.execute("INSERT INTO balances (account_id, date, cash_cents, source) VALUES ('cmb_courant', '2026-09-10', 19141, 'reported')")
    df, _ = portfolio.valuations(con, end=date(2026, 9, 11))
    cmb = df[df.account_id == "cmb_courant"].set_index("date").cash
    assert cmb["2026-09-10"] == 191.41 and cmb["2026-09-01"] == 341.41
    assert cmb.index.min() == "2026-09-01"
