"""Données de l'écran Flux (`flux_ecran`) sur le jeu fictif."""
import json
from datetime import date

import pytest

from patrimoine import db, demo, flux_ecran, mobile

AUJOURDHUI = date(2026, 11, 10)


@pytest.fixture
def con(tmp_path):
    demo.build(tmp_path / "patrimoine.db", today=AUJOURDHUI)
    with db.session(tmp_path / "patrimoine.db") as c:
        yield c


def test_mois_complets_et_courant_partiel(con):
    d = flux_ecran.donnees(con, 13, AUJOURDHUI)
    mois = d["mois"]
    assert len(mois) == 13 and mois[-1]["mois"] == "2026-11" and mois[0]["mois"] == "2025-11"
    assert mois[-1]["partiel"] and mois[-1]["taux"] is None
    m = mois[-2]
    assert not m["partiel"] and m["salaire"] == 2850.0
    assert m["revenus"] == pytest.approx(m["salaire"] + m["primes"] + m["placements"] + m["autres"])
    assert m["epargne"] == pytest.approx(m["revenus"] - m["depenses"])
    assert m["taux"] == pytest.approx(m["epargne"] / m["revenus"])
    # Les virements d'épargne (internes) ne sont ni dépenses ni revenus ; les charges fixes font partie des dépenses.
    assert m["depenses"] < m["revenus"]
    assert 780 <= m["charges_fixes"] <= m["depenses"]
    assert m["charges_fixes"] + m["depenses_courantes"] == pytest.approx(m["depenses"])


def test_indicateurs_sur_douze_mois_complets(con):
    i = flux_ecran.donnees(con, 13, AUJOURDHUI)["indicateurs"]
    assert i["mois_comptes"] == 12
    assert i["revenus_12m"] == pytest.approx(sum(i["revenus_par_source_12m"].values()))
    assert i["revenus_moyens"] == pytest.approx(i["revenus_12m"] / 12)
    assert i["salaire"]["montant"] == 2850.0 and i["salaire"]["evolution"] is None
    assert i["evolution_1an"] is not None  # le jeu couvre deux ans


def test_a_venir_ne_liste_que_les_prelevements_pas_encore_passes(con):
    # Le jeu fictif prélève les abonnements le 8 ; au 10 ils sont passés, au 5 ils sont attendus.
    assert flux_ecran.donnees(con, 13, AUJOURDHUI)["a_venir"] == []
    con.execute("DELETE FROM transactions WHERE date >= '2026-11-01'")
    d = flux_ecran.donnees(con, 13, date(2026, 11, 5))
    noms = {x["commercant"] for x in d["a_venir"]}
    assert {"Musique+", "Vidéo Flux", "Forme Club"} <= noms
    assert d["a_venir_total"] == pytest.approx(sum(x["montant"] for x in d["a_venir"]))
    assert all(x["date"] >= "2026-11-05" for x in d["a_venir"])


def test_ecran_depenses_embarque_le_detail(tmp_path):
    demo.build(tmp_path / "patrimoine.db")
    assert json.loads(mobile.init(str(tmp_path)))["ok"]
    r = json.loads(mobile.call("depenses_ecran", "{}"))
    assert r["ok"] and r["data"]["flux_detail"]["mois"]
