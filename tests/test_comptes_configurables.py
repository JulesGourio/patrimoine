"""Les comptes se trouvent par type, pas par identifiant : une base dont les comptes ont d'autres ids donne les
mêmes totaux que le jeu fictif, et la création d'un compte permet l'import CSV générique."""
from datetime import date

import pytest

from patrimoine import accueil_ecran, api, db, demo, flux_ecran, imports, portfolio, queries
from patrimoine.config import Settings

AUJOURDHUI = date(2026, 11, 10)
AUTRES_IDS = {
    "cmb_courant": "banque_cc", "cmb_livret_a": "banque_epargne", "cmb_livret_jeune": "banque_epargne2",
    "tr_especes": "courtier_cash", "tr_cto": "courtier_cto", "tr_pea": "courtier_pea",
    "peg_airbus": "plan_entreprise",
}


def _totaux(con):
    h = queries.history(con)
    last = h[h.date == h.date.max()]
    return float(last.value.sum()), {k: round(float(v), 2) for k, v in last.groupby("account_id").value.sum().items()}


def _renommer(con):
    """Donne d'autres identifiants aux comptes ; les comptes semés par `db.ACCOUNTS` restent, vides."""
    con.commit()
    con.execute("PRAGMA foreign_keys = OFF")
    tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")]
    for table in tables:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({table})")]
        for col in ("account_id", "holding_account_id") if table != "accounts" else ("id",):
            if col in cols:
                for old, new in AUTRES_IDS.items():
                    con.execute(f"UPDATE {table} SET {col} = ? WHERE {col} = ?", (new, old))
    con.executemany("INSERT OR IGNORE INTO accounts (id, institution, name, kind, source) VALUES (?, ?, ?, ?, ?)",
                    db.ACCOUNTS)
    con.commit()
    df, _ = portfolio.valuations(con, AUJOURDHUI)
    portfolio.store(con, df)


@pytest.fixture
def autre(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    path = Settings().db_path
    demo.build(path, today=AUJOURDHUI)
    with db.session(path) as con:
        df, _ = portfolio.valuations(con, AUJOURDHUI)
        portfolio.store(con, df)
        avant = _totaux(con)
        n_avant = len(api.synthese()["comptes"])
        _renommer(con)
    return path, avant, n_avant


def test_helpers_par_type(autre):
    path, _, _ = autre
    with db.session(path) as con:
        assert db.accounts_of_kind(con, "cto") == ["courtier_cto", "tr_cto"]
        assert db.main_account(con, "courant") == "banque_cc"  # le compte semé reste vide
        assert db.main_account(con, "pea") == "courtier_pea"
        assert db.accounts_of_kind(con, "inconnu") == [] and db.main_account(con, "inconnu") is None
        assert set(db.used_accounts(con, *db.SECURITIES_KINDS)) == {"courtier_cto", "courtier_pea"}


def test_totaux_identiques_avec_d_autres_ids(autre):
    path, (total, _), n_avant = autre
    with db.session(path) as con:
        assert _totaux(con)[0] == pytest.approx(total)
        assert queries.data_date(con) == queries.data_date(con)  # ne plante pas
        assert queries.pea_open_date(con)
    s = api.synthese()
    assert "erreur" not in s and s["total"] == pytest.approx(total)
    assert s["pea_ouverture"] and s["investi"] > 0 and s["gains_bruts"] is not None
    assert {c["compte"] for c in s["comptes"]} >= {"Compte-titres", "PEA"}
    assert len([c for c in s["comptes"]]) <= n_avant + 2  # seuls les comptes semés vides peuvent s'ajouter
    p = api.patrimoine()
    assert p["total"] == pytest.approx(total) and p["cout_investi"] > 0
    assert "courtier_cto" in api.performance("cto")["comptes"]
    assert api.performance("courtier_pea")["comptes"] == ["courtier_pea"]
    assert "erreur" in api.performance("nimportequoi")


def test_ecrans_avec_d_autres_ids(autre):
    path, (total, _), _ = autre
    with db.session(path) as con:
        d = accueil_ecran.donnees(con, api.synthese(), api.synthese(avec_peg=False))
        assert d["total"] == pytest.approx(total, abs=0.01)
        assert {c["id"] for c in d["comptes"]} >= {"courtier_cto", "courtier_pea", "banque_cc"}
        assert next(c for c in d["comptes"] if c["id"] == "courtier_cto")["titres"] is True
        assert d["sans_peg"] is not None and d["sans_peg"]["total"] < d["total"]
        f = flux_ecran.donnees(con, 13, AUJOURDHUI)
        assert len(f["mois"]) == 13 and f["mois"][-2]["salaire"] == 2850.0


def test_positions_et_ordre_sans_ids_codes_en_dur(autre):
    path, _, _ = autre
    with db.session(path) as con:
        pos = queries.positions(con)
        assert {"courtier_cto", "courtier_pea"} <= set(pos.account_id)
        assert not queries.realised(con).empty
    r = api.preparer_ordre("achat", "Titre", "raison", "risque", quantite=1, notifier=False)
    assert r["ok"]
    with db.session(path) as con:
        assert con.execute("SELECT account_id FROM order_ideas ORDER BY id DESC").fetchone()[0] == "courtier_cto"


def test_base_sans_aucun_compte_ne_plante_pas(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    with db.session(Settings().db_path) as con:
        db.init(con)
        con.commit()
        con.execute("PRAGMA foreign_keys = OFF")
        con.execute("DELETE FROM accounts")
        con.execute("DELETE FROM positions")
        assert db.accounts_of_kind(con, "courant") == [] and db.used_accounts(con, "cto") == []
        assert portfolio.peg_without_history(con) == [] and queries.pea_open_date(con) is None
        assert queries.positions(con).empty
    assert "erreur" in api.synthese() and "erreur" in api.patrimoine()
    assert "erreur" in api.performance()


def test_creer_un_compte_puis_importer_un_csv(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    r = imports.creer_compte(s, "ma_banque_cc", "Mon courant", "courant", "Ma Banque")
    assert r == {"id": "ma_banque_cc", "nom": "Mon courant", "type": "courant"}
    with pytest.raises(ValueError, match="existe déjà"):
        imports.creer_compte(s, "ma_banque_cc", "Autre", "courant")
    with pytest.raises(ValueError, match="type de compte inconnu"):
        imports.creer_compte(s, "x", "X", "bidule")
    p = tmp_path / "releve.csv"
    p.write_text("Date;Libellé;Montant\n02/10/2026;CARTE BOULANGERIE;-4,50\n03/10/2026;VIR SALAIRE ACME;1 500,00\n", encoding="utf-8")
    out = imports.csv_generique(s, p, reglages={"account": "ma_banque_cc", "amount": "Montant"})
    assert out["compte"] == "ma_banque_cc" and out["nouvelles"] == 2
    with db.session(s.db_path) as con:
        assert db.main_account(con, "courant") == "ma_banque_cc"


def _base_fictive(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    path = Settings().db_path
    demo.build(path, today=AUJOURDHUI)
    with db.session(path) as con:
        df, _ = portfolio.valuations(con, AUJOURDHUI)
        portfolio.store(con, df)
    return path


def test_performance_base_d_origine(tmp_path, monkeypatch):
    _base_fictive(tmp_path, monkeypatch)
    for compte in ("tr_cto", "tr_pea", "cto", "pea", ""):
        r = api.performance(compte)
        assert "erreur" not in r, r
    assert api.performance("tr_cto")["comptes"] == ["tr_cto"]
    assert api.performance("tr_pea")["comptes"] == ["tr_pea"]


def test_gains_synthese_identiques_apres_renommage(tmp_path, monkeypatch):
    path = _base_fictive(tmp_path, monkeypatch)
    cles = ("gains_bruts", "gains_nets", "impots_latents", "interets_et_dividendes")
    avant = api.synthese()
    assert avant["gains_bruts"]
    with db.session(path) as con:
        _renommer(con)
    apres = api.synthese()
    for k in cles:
        assert apres[k] == pytest.approx(avant[k]), k


def test_compte_homonyme_refuse(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    imports.creer_compte(s, "ma_banque_cc", "Mon courant", "courant")
    with pytest.raises(ValueError, match="déjà celui d'un autre compte"):
        imports.creer_compte(s, "autre_cc", "mon COURANT", "courant")
    with pytest.raises(ValueError, match="déjà celui d'un autre compte"):
        imports.creer_compte(s, "mon_pea", "PEA", "pea")  # libellé historique de tr_pea


def test_compte_prepaye_refuse_et_solde_selon_le_type(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    with pytest.raises(ValueError, match="creer_carte"):
        imports.creer_compte(s, "prepaye_x", "Ma carte", "prepaye")
    with db.session(s.db_path) as con:
        db.init(con)
        con.execute("INSERT INTO accounts (id, institution, name, kind, source) VALUES ('ma_carte', 'X', 'Ma carte', 'prepaye', 'manuel')")
    with pytest.raises(ValueError, match="Carte prépayée"):
        imports.balance(s, "ma_carte", "10")  # refusé d'après le type, pas le préfixe de l'id
    imports.creer_compte(s, "prepaye_livret", "Livret perso", "livret")
    assert imports.balance(s, "prepaye_livret", "10") == 1000  # un livret à l'id trompeur reste saisissable


def test_csv_generique_refuse_cto_et_peg(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    imports.creer_compte(s, "mon_cto", "Mon titres", "cto")
    imports.creer_compte(s, "mon_peg", "Mon plan", "peg")
    p = tmp_path / "r.csv"
    p.write_text("Date;Libellé;Montant\n02/10/2026;ACHAT;-4,50\n", encoding="utf-8")
    for acc in ("mon_cto", "mon_peg"):
        with pytest.raises(ValueError, match="compte espèces du courtier|Importer sur le compte espèces"):
            imports.csv_generique(s, p, reglages={"account": acc, "amount": "Montant"})


def test_main_account_deux_comptes_avec_operations(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    imports.creer_compte(s, "cc_a", "Courant A", "courant")
    imports.creer_compte(s, "cc_b", "Courant B", "courant")
    with db.session(s.db_path) as con:
        ins = "INSERT INTO transactions (id, account_id, date, amount_cents, label, flow) VALUES (?, ?, '2026-01-02', -100, 'x', 'depense')"
        for i, acc in enumerate(["cc_a"] * 2 + ["cc_b"] * 3):
            con.execute(ins, (f"t{i}", acc))
        # cmb_courant (semé) est vide ; le plus d'opérations l'emporte
        assert db.main_account(con, "courant") == "cc_b"
        con.execute(ins, ("t9", "cc_a"))
        con.execute(ins, ("t10", "cc_a"))
        assert db.main_account(con, "courant") == "cc_a"
        con.execute("DELETE FROM transactions WHERE id = 't9'")
        assert db.main_account(con, "courant") == "cc_a"  # 3 contre 3 : le premier créé l'emporte


def test_preparer_ordre_compte_explicite(tmp_path, monkeypatch):
    _base_fictive(tmp_path, monkeypatch)
    r = api.preparer_ordre("achat", "Titre", "raison", "risque", compte="tr_pea", quantite=1, notifier=False)
    assert r["ok"]
    with db.session(Settings().db_path) as con:
        assert con.execute("SELECT account_id FROM order_ideas ORDER BY id DESC").fetchone()[0] == "tr_pea"
