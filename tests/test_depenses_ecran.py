"""Outil `depenses_operations` et écran `depenses_ecran` (page Dépenses de l'appli)."""
import json
from datetime import date

import pytest

from patrimoine import db, mobile, notify, vault


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(vault, "_backend", vault.KeyringBackend())
    monkeypatch.setattr(notify, "_local", None)
    from patrimoine.config import Settings

    with db.session(Settings().db_path) as con:
        db.init(con)
        acc = con.execute("SELECT id FROM accounts LIMIT 1").fetchone()
        if acc is None:
            con.execute("INSERT INTO accounts (id, institution, name, kind) VALUES ('cmb_courant','CMB','Courant','courant')")
            acc = ("cmb_courant",)
        today = date.today()
        old = date(today.year - 3, 1, 15).isoformat()
        rows = [
            ("a", today.replace(day=1).isoformat(), -1250, "Boulangerie", "depense", "Alimentation", None),
            ("b", today.replace(day=1).isoformat(), -3000, "Mystère", "depense", None, None),
            ("c", today.replace(day=1).isoformat(), -500, "Café", "depense", "Alimentation", "Loisirs"),
            ("d", old, -999, "Vieux", "depense", "Alimentation", None),
            ("e", today.replace(day=1).isoformat(), -700, "Virement", "interne", None, None),
        ]
        for i, d, cents, cp, flow, cat, ov in rows:
            con.execute(
                "INSERT INTO transactions (id, account_id, date, amount_cents, counterparty, flow, category,"
                " category_override) VALUES (?,?,?,?,?,?,?,?)", (i, acc[0], d, cents, cp, flow, cat, ov))
    return tmp_path


def test_depenses_operations_gives_every_spending_line_of_the_window(base):
    from patrimoine import api

    ops = {o["id"]: o for o in api.depenses_operations(13)["operations"]}
    assert set(ops) == {"a", "b", "c"}  # ni l'interne, ni la ligne vieille de 3 ans
    assert ops["a"]["montant"] == 12.5 and ops["a"]["categorie"] == "Alimentation" and not ops["a"]["modifiee"]
    assert ops["a"]["contrepartie"] == "Boulangerie"
    assert ops["b"]["categorie"] == "Non catégorisé"
    assert ops["c"]["categorie"] == "Loisirs" and ops["c"]["modifiee"] is True


def test_depenses_ecran_bundles_what_the_page_needs(base):
    from patrimoine.categories import SPENDING

    raw = json.loads(mobile.call("depenses_ecran"))
    assert raw["ok"], raw
    d = raw["data"]
    assert len(d["operations"]) == 3 and d["categories"] == SPENDING
    assert {"par_mois", "mois_en_cours", "flux"} <= set(d)
