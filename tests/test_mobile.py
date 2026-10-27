import json

import pytest

from patrimoine import db, mobile, notify, vault


class Store:
    """Stands in for the Kotlin Keystore-backed store."""

    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


class Notifier:
    def __init__(self):
        self.shown = []

    def show(self, title, message, priority):
        self.shown.append((title, message, priority))
        return True


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(vault, "_backend", vault.KeyringBackend())
    monkeypatch.setattr(notify, "_local", None)
    store, notifier = Store(), Notifier()
    reply = json.loads(mobile.init(str(tmp_path / "files"), store, notifier))
    assert reply["ok"], reply
    return store, notifier, reply["data"]


def ok(raw: str):
    reply = json.loads(raw)
    assert reply["ok"], reply
    return reply["data"]


def test_init_creates_the_database_and_reports_state(app, tmp_path):
    _, _, state = app
    assert state["base"].startswith(str(tmp_path / "files"))
    assert state["operations"] == 0 and state["trade_republic_session"] is False
    assert set(state["secrets"]) == set(vault.KNOWN)


def test_secrets_go_to_the_phone_store(app):
    store, _, _ = app
    ok(mobile.set_secret("tr_pin", " 1234 "))
    assert store.values == {"tr_pin": "1234"} and vault.get("tr_pin") == "1234"
    ok(mobile.set_secret("tr_pin", ""))
    assert store.values == {}
    assert json.loads(mobile.set_secret("whatever", "x"))["ok"] is False


def test_pushes_become_phone_notifications(app):
    _, notifier, _ = app
    assert ok(mobile.test_notification())["canaux"] == "téléphone"
    assert notifier.shown[0][0] == "Test Patrimoine"


def test_call_runs_tools_and_screens_with_json_arguments(app):
    assert ok(mobile.call("operations", json.dumps({"jours": 30}))) == {"operations": [], "tronque": False}
    home = ok(mobile.call("accueil"))
    assert home["courbe"] == [] and home["ordres_proposes"] == 0
    assert home["courbes_comptes"] == {} and home["courbe_titres"] == {"valeur": [], "cout": []}
    names = {t["nom"] for t in ok(mobile.tools())}
    assert {"patrimoine", "positions", "accueil", "etat"} <= names


def test_errors_come_back_as_messages(app):
    assert json.loads(mobile.call("nope"))["erreur"] == "fonction inconnue : nope"
    assert json.loads(mobile.call("operations", "[1]"))["ok"] is False
    assert json.loads(mobile.call("operations", '{"pas_un_parametre": 1}'))["ok"] is False
    assert json.loads(mobile.import_file("autre", "/tmp/x"))["erreur"].startswith("type de fichier inconnu")


def test_export_then_import_database(app, tmp_path):
    copy = ok(mobile.export_database(str(tmp_path / "share" / "patrimoine.db")))["fichier"]
    assert ok(mobile.import_file("base", copy))["operations"] == 0


def test_only_one_sync_at_a_time(app, monkeypatch):
    from patrimoine import cloud, pipeline

    monkeypatch.setattr(pipeline, "run", lambda settings, send_alerts=True: ["étape"])
    monkeypatch.setattr(cloud, "pull", lambda settings: ["analyse 1 publiée"])
    assert ok(mobile.sync()) == {"deja_en_cours": False, "lignes": ["étape", "analyse 1 publiée"]}
    mobile._sync_lock.acquire()
    try:
        assert ok(mobile.sync())["deja_en_cours"] is True
        assert json.loads(mobile.import_file("base", "/x"))["ok"] is False
    finally:
        mobile._sync_lock.release()


def test_balance_entry(app):
    assert ok(mobile.set_balance("cmb_livret_jeune", "1600,50")) == {"centimes": 160_050}


def test_synchroniser_through_call_uses_the_lock(app, monkeypatch):
    from patrimoine import cloud, pipeline

    monkeypatch.setattr(pipeline, "run", lambda settings, send_alerts=True: ["étape"])
    monkeypatch.setattr(cloud, "pull", lambda settings: [])
    mobile._sync_lock.acquire()
    try:
        assert ok(mobile.call("synchroniser"))["deja_en_cours"] is True
    finally:
        mobile._sync_lock.release()
    assert ok(mobile.call("synchroniser"))["lignes"] == ["étape"]


def test_database_import_holds_the_sync_lock(app, tmp_path, monkeypatch):
    from patrimoine import imports

    seen = []
    monkeypatch.setattr(imports, "database", lambda settings, path: seen.append(mobile._sync_lock.locked()) or {})
    ok(mobile.import_file("base", str(tmp_path / "x.db")))
    assert seen == [True] and not mobile._sync_lock.locked()


def test_blank_secret_is_deleted(app):
    store, _, _ = app
    ok(mobile.set_secret("ntfy_topic", "abc"))
    assert ok(mobile.set_secret("ntfy_topic", "   ")) == {"ntfy_topic": False}
    assert store.values == {}


def test_references_for_the_screens(app):
    refs = ok(mobile.call("references"))
    assert "Courses" in refs["categories_depenses"]
    assert refs["comptes_solde_manuel"] == ["cmb_livret_a", "cmb_livret_jeune"]


def test_order_status_is_only_a_note(app):
    from patrimoine import api

    made = api.preparer_ordre("achat", "Airbus", "test", "aucun", notifier=False)
    assert ok(mobile.call("statut_ordre", json.dumps({"id": made["id"], "statut": "passé"})))["statut"] == "passé"
    assert api.ordres_proposes("passé")["ordres"][0]["id"] == made["id"]
    assert json.loads(mobile.call("statut_ordre", json.dumps({"id": 999, "statut": "passé"})))["ok"] is False
    assert json.loads(mobile.call("statut_ordre", json.dumps({"id": made["id"], "statut": "exécute"})))["ok"] is False


def test_analysis_detail(app):
    from patrimoine import briefing, db
    from patrimoine.config import Settings

    with db.session(Settings().db_path) as con:
        con.executescript(briefing.SCHEMA)
        facts = {"lignes": [{"isin": "X", "nom": "Airbus", "move": -0.02, "impact_eur": -50, "series": [1, 2]}],
                 "patrimoine": {"effet_marche_eur": -50}, "marche": [{"nom": "CAC 40", "groupe": "Europe", "move": 0.01}]}
        bid = con.execute("INSERT INTO briefings (created_at, kind, session, facts, analysis) VALUES "
                          "('2026-10-26T08:00:00+00:00', 'quotidien', '2026-10-23', ?, ?)",
                          (json.dumps(facts), json.dumps({"titre": "Séance calme"}))).lastrowid
    a = ok(mobile.call("analyse", json.dumps({"id": bid})))
    assert a["analyse"]["titre"] == "Séance calme"
    assert a["lignes"]["X"]["nom"] == "Airbus" and "series" not in a["lignes"]["X"]
    assert json.loads(mobile.call("analyse", '{"id": 999}'))["ok"] is False


def test_operations_filter_by_month_and_category(app):
    from patrimoine import api, db
    from patrimoine.config import Settings

    with db.session(Settings().db_path) as con:
        con.executemany(
            "INSERT INTO transactions (id, account_id, date, amount_cents, flow, category, counterparty) VALUES "
            "(?, 'cmb_courant', ?, -1000, 'depense', ?, 'SHOP')",
            [("o1", "2020-03-05", "Courses"), ("o2", "2020-03-20", "Loisirs"), ("o3", "2020-04-02", "Courses")])
    ids = lambda **kw: sorted(o["id"] for o in api.operations(**kw)["operations"])  # noqa: E731
    assert ids(mois="2020-03") == ["o1", "o2"]
    assert ids(mois="2020-03", categorie="Courses") == ["o1"]
    assert ids(mois="2020-04", categorie="Loisirs") == []


def test_income_lines_take_income_categories(app):
    from patrimoine import db
    from patrimoine.config import Settings

    with db.session(Settings().db_path) as con:
        con.execute("INSERT INTO transactions (id, account_id, date, amount_cents, flow, counterparty) VALUES "
                    "('r1', 'cmb_courant', '2026-10-20', 2500, 'revenu', 'PAUL')")
    ok(mobile.call("categoriser", json.dumps({"transaction_id": "r1", "categorie": "Remboursements"})))
    with db.session(Settings().db_path) as con:
        assert con.execute("SELECT category_override FROM transactions WHERE id = 'r1'").fetchone()[0] == "Remboursements"
    assert json.loads(mobile.call("categoriser", json.dumps({"transaction_id": "r1", "categorie": "x"})))["ok"] is False


def test_accueil_gives_per_account_and_invested_curves(app):
    with db.session(mobile.settings().db_path) as con:
        db.init(con)
        for acc, kind in (("tr_cto", "cto"), ("cmb_courant", "courant")):
            con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind, source) VALUES (?, 'X', ?, ?, 'manuel')",
                        (acc, acc, kind))
        for d, sec, cost, cash in (("2026-10-01", 1100_00, 1000_00, 0), ("2026-10-02", 1200_00, 1000_00, 0)):
            con.execute("INSERT INTO valuations VALUES (?, 'tr_cto', ?, ?, ?, 0, 0)", (d, cash, sec, cost))
            con.execute("INSERT INTO valuations VALUES (?, 'cmb_courant', 50000, 0, 0, 0, 0)", (d,))
    home = ok(mobile.call("accueil"))
    assert home["courbes_comptes"]["Compte-titres"] == [["2026-10-01", 1100.0], ["2026-10-02", 1200.0]]
    assert home["courbes_comptes"]["CMB courant"][0] == ["2026-10-01", 500.0]
    assert home["courbe_titres"]["valeur"][-1] == ["2026-10-02", 1200.0]
    assert home["courbe_titres"]["cout"] == [["2026-10-01", 1000.0], ["2026-10-02", 1000.0]]
    assert home["comptes_titres"] == ["Compte-titres", "PEA"]
