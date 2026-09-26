from patrimoine import db


def fresh():
    con = db.connect(":memory:")
    db.init(con)
    return con


def test_init_seeds_accounts_and_peg():
    con = fresh()
    ids = {r["id"] for r in con.execute("SELECT id FROM accounts")}
    assert {"cmb_courant", "cmb_livret_jeune", "cmb_livret_a", "tr_especes", "tr_cto", "tr_pea", "peg_airbus"} == ids
    peg = con.execute("SELECT quantity, source FROM positions WHERE account_id = 'peg_airbus'").fetchone()
    assert peg["quantity"] == 109.4 and peg["source"] == "manuel"


def test_init_is_idempotent_and_keeps_manual_edits():
    con = fresh()
    con.execute("UPDATE positions SET quantity = 120 WHERE account_id = 'peg_airbus'")
    db.set_rule(con, "carrefour", "Divers")
    db.init(con)
    assert con.execute("SELECT quantity FROM positions WHERE account_id = 'peg_airbus'").fetchone()[0] == 120
    assert db.rules(con)["CARREFOUR"] == "Divers"
    assert con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 7


def test_meta_roundtrip():
    con = fresh()
    assert db.get_meta(con, "last_sync") is None
    db.set_meta(con, "last_sync", {"tr": "2026-09-26"})
    db.set_meta(con, "last_sync", {"tr": "2026-09-27"})
    assert db.get_meta(con, "last_sync") == {"tr": "2026-09-27"}
