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


def test_taux_moyen_12m_est_pondere(con):
    d = flux_ecran.donnees(con, 13, AUJOURDHUI)
    complets = [m for m in d["mois"] if not m["partiel"]][-12:]
    attendu = sum(m["epargne"] for m in complets) / sum(m["revenus"] for m in complets)
    assert d["indicateurs"]["taux_moyen_12m"] == pytest.approx(attendu)


def test_mois_non_couvert_par_la_base_est_partiel(con):
    # Base arrêtée au 15 octobre alors qu'on est le 10 novembre : octobre n'est pas fini dans les données.
    con.execute("DELETE FROM transactions WHERE date > '2026-10-15'")
    d = flux_ecran.donnees(con, 13, AUJOURDHUI)
    par_mois = {m["mois"]: m for m in d["mois"]}
    assert par_mois["2026-10"]["partiel"] and par_mois["2026-10"]["taux"] is None
    assert not par_mois["2026-09"]["partiel"]
    assert d["indicateurs"]["mois_comptes"] == 12


def test_base_vide(tmp_path):
    with db.session(tmp_path / "vide.db") as c:
        db.init(c)
        d = flux_ecran.donnees(c, 13, AUJOURDHUI)
    assert all(m["vide"] and m["taux"] is None for m in d["mois"])
    assert d["indicateurs"]["taux_moyen_12m"] is None


def test_investi_jamais_negatif_zero(con):
    for m in flux_ecran.donnees(con, 13, AUJOURDHUI)["mois"]:
        assert str(m["investi"]) != "-0.0"


def test_remboursement_baisse_les_depenses_sans_etre_un_revenu(con):
    avant = {m["mois"]: m for m in flux_ecran.donnees(con, 13, AUJOURDHUI)["mois"]}["2026-10"]
    demo._tx(con, 9001, date(2026, 10, 12), "cmb_courant", "revenu", 50_00, "Virement ami", "Ami", "Remboursements")
    apres = {m["mois"]: m for m in flux_ecran.donnees(con, 13, AUJOURDHUI)["mois"]}["2026-10"]
    assert apres["depenses"] == pytest.approx(avant["depenses"] - 50)
    assert apres["revenus"] == pytest.approx(avant["revenus"])
    assert apres["remboursements"] == pytest.approx(avant["remboursements"] + 50)


def test_virement_interne_exclu(con):
    avant = {m["mois"]: m for m in flux_ecran.donnees(con, 13, AUJOURDHUI)["mois"]}["2026-10"]
    demo._tx(con, 9002, date(2026, 10, 12), "cmb_courant", "interne", -300_00, "Virement", "")
    demo._tx(con, 9003, date(2026, 10, 12), "tr_especes", "interne", 300_00, "Virement", "")
    apres = {m["mois"]: m for m in flux_ecran.donnees(con, 13, AUJOURDHUI)["mois"]}["2026-10"]
    assert (apres["revenus"], apres["depenses"]) == (avant["revenus"], avant["depenses"])
