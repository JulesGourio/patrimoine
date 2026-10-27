import sqlite3

import pytest

from patrimoine import db, imports
from patrimoine.config import Settings


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    with db.session(s.db_path) as con:
        db.init(con)
    return s


def test_balance_accepts_french_amounts_and_rejects_unknown_accounts(settings):
    assert imports.balance(settings, "cmb_livret_a", "1 234,56", "2026-10-01") == 123_456
    with db.session(settings.db_path) as con:
        row = con.execute("SELECT cash_cents FROM balances WHERE account_id = 'cmb_livret_a'").fetchone()
    assert row[0] == 123_456
    with pytest.raises(ValueError, match="inconnu"):
        imports.balance(settings, "nope", "1")


def test_backup_then_import_round_trip_keeps_the_previous_copy(settings, tmp_path):
    with db.session(settings.db_path) as con:
        con.execute("INSERT INTO transactions (id, account_id, date, amount_cents, flow) VALUES "
                    "('x', 'cmb_courant', '2026-10-02', -500, 'depense')")
    copy = imports.backup(settings, tmp_path / "out" / "copie.db")
    assert imports.check_database(copy) == {"operations": 1, "derniere_operation": "2026-10-02"}

    other = Settings(data_dir=tmp_path / "phone")
    info = imports.database(other, copy)  # first import: nothing to keep aside
    assert info["operations"] == 1
    with db.session(other.db_path) as con:
        assert con.execute("SELECT amount_cents FROM transactions").fetchone()[0] == -500

    imports.database(other, copy)  # again: each replaced copy is kept aside
    imports.database(other, copy)
    assert len(list(other.data_dir.glob("patrimoine-avant-import-*.db"))) == 2


def test_paths_with_url_characters_are_read(settings, tmp_path):
    copy = imports.backup(settings, tmp_path / "dossier #1 50%" / "copie.db")
    assert imports.check_database(copy)["operations"] == 0


def test_import_refuses_files_that_are_not_a_patrimoine_database(settings, tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not sqlite at all" * 100)
    with pytest.raises(ValueError, match="illisible"):
        imports.database(settings, junk)
    other = tmp_path / "other.db"
    sqlite3.connect(other).execute("CREATE TABLE t (x)").connection.close()
    with pytest.raises(ValueError, match="pas une base Patrimoine"):
        imports.database(settings, other)


def test_peg_without_statements_is_a_clear_error(settings):
    with pytest.raises(ValueError, match="Aucun relevé"):
        imports.peg(settings, [])
