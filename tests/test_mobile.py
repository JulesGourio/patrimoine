import json

import pytest

from patrimoine import mobile, notify, vault


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
