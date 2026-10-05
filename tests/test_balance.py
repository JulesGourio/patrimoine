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


def test_inheritance_is_wealth_not_income_nor_savings():
    from patrimoine.categories import categorize

    label = "VIR SURAVENIR ASS VIE SURAVENIR REGLT DECES - LE BUHAN MICHEL S261001000097"
    assert categorize("revenu", label, "SURAVENIR", {}) == "Autres revenus"  # rules come from the database
    con = db.connect(":memory:")
    db.init(con)
    assert categorize("revenu", label, "SURAVENIR", db.rules(con)) == "Héritage et donations"
    con.executemany("INSERT INTO transactions (id, account_id, date, amount_cents, flow, category) VALUES"
                    " (?, 'cmb_courant', ?, ?, ?, ?)", [("s", "2026-10-28", 245308, "revenu", "Salaire"),
                                                        ("h", "2026-10-01", 481275, "revenu", "Héritage et donations")])
    b = analytics.monthly_balance(con).iloc[0]
    assert b.revenus == 2453.08 and b.epargne == 2453.08 and b.heritage == 4812.75


def test_cmb_balance_leaves_out_pending_lines():
    from patrimoine.sources import cmb_parse

    tx = lambda d, s, ind, amt: {"booking_date": d, "status": s, "credit_debit_indicator": ind,  # noqa: E731
                                 "transaction_amount": {"amount": amt}}
    dump = {"accounts": [{"balances": [{"balance_type": "XPCD", "reference_date": "2026-10-02",
                                        "balance_amount": {"amount": "1037.24"}}],
                          "transactions": [tx("2026-10-02", "PDNG", "DBIT", "5700.0"),
                                           tx("2026-10-02", "PDNG", "DBIT", "720.0"),
                                           tx("2026-10-01", "BOOK", "CRDT", "4812.75")]}]}
    # Pending transfers are not imported: the anchor is the booked balance on the eve of the first one.
    assert cmb_parse.balance(dump) == ("2026-10-01", 745724)
    dump["accounts"][0]["balances"][0]["balance_type"] = "CLBD"
    assert cmb_parse.balance(dump) == ("2026-10-02", 103724)
