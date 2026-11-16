from patrimoine import db


def fresh():
    con = db.connect(":memory:")
    db.init(con)
    return con


def test_init_seeds_accounts_and_peg():
    con = fresh()
    ids = {r["id"] for r in con.execute("SELECT id FROM accounts")}
    assert {"cmb_courant", "cmb_livret_jeune", "cmb_livret_a", "tr_especes", "tr_cto", "tr_pea", "peg_airbus"} == ids
    assert con.execute("SELECT COUNT(*) FROM positions").fetchone()[0] == 0  # plus de PEG fantôme chez un nouvel utilisateur


def test_base_existante_garde_la_ligne_peg():
    """Une base d'avant (comptes déjà là, signature périmée) garde sa ligne PEG, et elle se recrée si elle manque."""
    con = fresh()
    con.execute("INSERT INTO positions (account_id, isin, quantity, avg_cost, as_of, source)"
                " VALUES ('peg_airbus', ?, 109.4, NULL, '2026-01-01', 'manuel')", (db.AIRBUS[0],))
    con.execute("PRAGMA user_version = 0")
    db.init(con)
    assert con.execute("SELECT quantity FROM positions WHERE account_id = 'peg_airbus'").fetchone()[0] == 109.4
    con.execute("DELETE FROM positions")
    con.execute("PRAGMA user_version = 0")
    db.init(con)
    assert con.execute("SELECT quantity FROM positions WHERE account_id = 'peg_airbus'").fetchone()[0] == 109.4


def test_libelles_internes_ignorent_les_noms_d_etablissement():
    con = fresh()
    db.create_account(con, "rev", "Revolut", "courant")
    db.create_account(con, "cc2", "Banque Verte Courant", "courant")
    db.set_meta(con, "libelles_internes", ["COFFRE ZETA"])
    labels = db.internal_labels(con)
    assert "Revolut" not in labels and "Banque Verte Courant" in labels and "COFFRE ZETA" in labels


def test_init_is_idempotent_and_keeps_manual_edits():
    con = fresh()
    con.execute("INSERT INTO positions (account_id, isin, quantity, avg_cost, as_of, source)"
                " VALUES ('peg_airbus', ?, 109.4, NULL, '2026-01-01', 'manuel')", (db.AIRBUS[0],))
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


def test_obsolete_default_rules_become_user_rules_and_internal_labels_are_seeded():
    """A database made by older code: its default rules that left the code stay, as the user's own."""
    from patrimoine import db
    from patrimoine.categories import DEFAULT_RULES

    con = db.connect(":memory:")
    db.init(con)
    con.execute("INSERT INTO category_rules (pattern, category, origin) VALUES ('CHEZ MARCEL', 'Restaurants et sorties', 'defaut')")
    con.execute("UPDATE category_rules SET category = 'Shopping' WHERE pattern = 'LIDL'")
    set_ = "INSERT INTO transactions (id, account_id, date, amount_cents, label, counterparty, flow) VALUES (?, 'cmb_courant', '2026-01-02', -1000, ?, ?, ?)"
    con.execute(set_, ("a", "VIR vers COFFRE ZETA  de X", "COFFRE ZETA", "interne"))
    con.execute(set_, ("b", "VIR vers LIVRET CMB", "LIVRET CMB", "interne"))
    con.execute(set_, ("c", "VIR vers DUPONT ALICE", "DUPONT ALICE", "interne"))
    con.execute(set_, ("d", "VIR vers PAUL", "PAUL", "depense"))
    con.execute("DELETE FROM meta WHERE key = 'libelles_internes'")
    db.set_meta(con, "owner", {"first": "Alice", "last": "Dupont"})
    con.execute("PRAGMA user_version = 0")  # as if the code had changed
    db.init(con)
    rows = {r["pattern"]: (r["category"], r["origin"]) for r in con.execute("SELECT * FROM category_rules")}
    assert rows["CHEZ MARCEL"] == ("Restaurants et sorties", "utilisateur")  # kept, now the user's
    assert rows["LIDL"] == ("Courses", "defaut")  # still a default: follows the code
    assert set(DEFAULT_RULES) <= set(rows)
    assert db.get_meta(con, "libelles_internes") == ["COFFRE ZETA"]
    assert "COFFRE ZETA" in db.internal_labels(con)
    db.set_meta(con, "libelles_internes", ["COFFRE ZETA", "AUTRE"])  # the user's list is never rewritten
    con.execute("PRAGMA user_version = 0")
    db.init(con)
    assert db.get_meta(con, "libelles_internes") == ["COFFRE ZETA", "AUTRE"]
