"""End-to-end tests of patrimoine.imports on a temporary SQLite database with synthetic CMB exports."""
import sqlite3

import pytest

from patrimoine import db, imports
from patrimoine.config import Settings

HEADER = "Date operation;Date valeur;Libelle;Debit;Credit\n"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path / "data"))
    s = Settings()
    with db.session(s.db_path) as con:
        db.init(con)
    return s


def write_csv(folder, name, lines):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(HEADER + "".join(lines), encoding="latin-1", newline="")
    return path


COURANT = [
    "03/02/2024;03/02/2024;CARTE 01/02 BOULANGERIE 12,35 EUR;12,35;\n",
    "05/02/2024;05/02/2024;VIR de EMPLOYEUR SAS  SALAIRE JANVIER;;1 234,56\n",
    "06/02/2024;06/02/2024;VIR vers LIVRET CMB;200,00;\n",
    "07/02/2024;07/02/2024;VIR vers TRADE REPUBLIC;50,10;\n",
]


def rows(settings, account):
    with db.session(settings.db_path) as con:
        return con.execute("SELECT * FROM transactions WHERE account_id = ? ORDER BY date", (account,)).fetchall()


def test_cmb_csv_amounts_and_flows(settings, tmp_path):
    f = write_csv(tmp_path / "dl", "RELEVE_COMPTE_CHEQUES_20240301.csv", COURANT)
    result = imports.cmb_csv(settings, [f])
    assert result["cmb_courant"][:2] == (4, 0)
    r = rows(settings, "cmb_courant")
    by_date = {x["date"]: x for x in r}
    assert all(isinstance(x["amount_cents"], int) for x in r)
    assert by_date["2024-02-03"]["amount_cents"] == -1235 and by_date["2024-02-03"]["flow"] == "depense"
    assert by_date["2024-02-05"]["amount_cents"] == 123456 and by_date["2024-02-05"]["flow"] == "revenu"
    # Transfers to Jules's own accounts are internal: neither spending nor income.
    assert by_date["2024-02-06"]["flow"] == "interne" and by_date["2024-02-06"]["amount_cents"] == -20000
    assert by_date["2024-02-07"]["flow"] == "interne" and by_date["2024-02-07"]["amount_cents"] == -5010


def test_cmb_csv_reimport_creates_no_duplicates(settings, tmp_path):
    f = write_csv(tmp_path / "dl", "RELEVE_COMPTE_CHEQUES_20240301.csv", COURANT + [COURANT[0]])  # twin line
    first = imports.cmb_csv(settings, [f])
    second = imports.cmb_csv(settings, [f])
    assert first["cmb_courant"][0] == 5 and second["cmb_courant"][:2] == (0, 5)
    assert len(rows(settings, "cmb_courant")) == 5  # identical lines on the same day are kept apart
    # Picking the same export again under another folder (copied by name) still does not duplicate.
    imports.cmb_csv(settings, [])
    assert len(rows(settings, "cmb_courant")) == 5


def test_cmb_csv_livret(settings, tmp_path):
    f = write_csv(tmp_path / "dl", "RELEVE_LIVRET_CMB_20240301.csv",
                  ["06/02/2024;06/02/2024;VIR de COMPTE CHEQUES;;200,00\n",
                   "01/03/2024;01/03/2024;INTERETS CREDITEURS;;1,07\n"])
    result = imports.cmb_csv(settings, [f])
    assert result["cmb_livret_a"] == (2, 0, "2024-02-06", "2024-03-01")
    r = {x["date"]: x for x in rows(settings, "cmb_livret_a")}
    assert r["2024-02-06"]["flow"] == "interne" and r["2024-02-06"]["amount_cents"] == 20000
    assert r["2024-03-01"]["flow"] == "interets" and r["2024-03-01"]["amount_cents"] == 107


def test_balance_is_stored_in_cents(settings):
    assert imports.balance(settings, "cmb_livret_a", "1 234,56", "2024-03-01") == 123456
    assert imports.balance(settings, "cmb_livret_a", 10.1, "2024-03-02") == 1010
    with db.session(settings.db_path) as con:
        got = {r["date"]: r["cash_cents"] for r in con.execute("SELECT * FROM balances WHERE account_id = 'cmb_livret_a'")}
    assert got == {"2024-03-01": 123456, "2024-03-02": 1010}
    imports.balance(settings, "cmb_livret_a", "99,99", "2024-03-01")  # same day: replaced, not duplicated
    with db.session(settings.db_path) as con:
        n = con.execute("SELECT COUNT(*) FROM balances WHERE account_id = 'cmb_livret_a'").fetchone()[0]
    assert n == 2


def test_balance_unknown_account(settings):
    with pytest.raises(ValueError):
        imports.balance(settings, "nexiste_pas", "1")


def test_peg_without_statements_raises(settings, tmp_path):
    with pytest.raises(ValueError, match="Aucun relevé Amundi"):
        imports.peg(settings, [])


def test_backup_then_database_restores_same_base(settings, tmp_path, monkeypatch):
    imports.cmb_csv(settings, [write_csv(tmp_path / "dl", "RELEVE_COMPTE_CHEQUES_20240301.csv", COURANT)])
    imports.balance(settings, "cmb_livret_a", "500", "2024-03-01")
    before = rows(settings, "cmb_courant")
    saved = imports.backup(settings, tmp_path / "out" / "copie.db")
    assert saved.exists() and imports.check_database(saved)["operations"] == 4

    with db.session(settings.db_path) as con:  # change the live base after the backup
        con.execute("DELETE FROM transactions")
        con.commit()
    assert rows(settings, "cmb_courant") == []

    info = imports.database(settings, saved)
    assert info["operations"] == 4 and info["derniere_operation"] == "2024-02-07"
    after = rows(settings, "cmb_courant")
    assert [tuple(x) for x in after] == [tuple(x) for x in before]
    with db.session(settings.db_path) as con:
        assert con.execute("SELECT cash_cents FROM balances WHERE account_id = 'cmb_livret_a'").fetchone()[0] == 50000
    # The replaced base is kept next to it.
    assert list(settings.db_path.parent.glob("patrimoine-avant-import-*.db"))


def test_database_refuses_foreign_files(settings, tmp_path):
    other = tmp_path / "autre.db"
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE t (x)")
    con.commit()
    con.close()
    with pytest.raises(ValueError, match="pas une base Patrimoine"):
        imports.database(settings, other)
    junk = tmp_path / "junk.db"
    junk.write_bytes(b"not a database" * 100)
    with pytest.raises(ValueError):
        imports.database(settings, junk)
