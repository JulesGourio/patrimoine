from patrimoine import analytics, db


def test_refunds_are_netted_off_spending_not_counted_as_income():
    con = db.connect(":memory:")
    db.init(con)
    rows = [("s", "2026-08-28", 245308, "revenu", "Salaire"), ("a", "2026-08-05", 16800, "revenu", "Aides et allocations"),
            ("r", "2026-08-10", 3500, "revenu", "Remboursements"), ("d", "2026-08-09", -7000, "depense", "Restaurants et sorties"),
            ("f", "2026-08-09", -470, "frais", None), ("i", "2026-08-01", 12000, "interne", None)]
    con.executemany("INSERT INTO transactions (id, account_id, date, amount_cents, flow, category) VALUES"
                    " (?, 'cmb_courant', ?, ?, ?, ?)", rows)
    b = analytics.monthly_balance(con).iloc[0]
    assert b.salaire == 2453.08 and b.remboursements == 35.0
    assert b.revenus == 2453.08 + 168.0  # the refund and the internal transfer are not income
    assert b.depenses == 70.0 + 4.70 - 35.0  # the friend's share comes off the dinner
    assert round(b.epargne, 2) == round(2453.08 + 168 + 35 - 74.70, 2)


def test_crypto_quotes_come_from_the_coin_code():
    from patrimoine.analytics import kind_of
    from patrimoine.prices import crypto_symbols

    assert crypto_symbols("XF000BTC0017", "Bitcoin")[0] == "BTC-EUR"
    assert crypto_symbols("XF000ETH0019", None) == ["ETH-EUR"]
    assert kind_of("Bitcoin") == "Crypto"
