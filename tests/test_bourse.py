"""Outil `bourse` (écran Bourse) sur le jeu fictif : totaux, une période, compte sans dividendes, indice hors ligne."""
import json

import pandas as pd
import pytest

from patrimoine import api, bourse, db, demo, mobile, prices


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    demo.build(tmp_path / "patrimoine.db")
    bourse._INDICE.clear()
    yield tmp_path
    bourse._INDICE.clear()


def indice_factice(monkeypatch):
    days = pd.date_range(pd.Timestamp.today().normalize() - pd.Timedelta(days=900), pd.Timestamp.today().normalize())
    s = pd.Series([100 + 0.05 * i for i in range(len(days))], index=days)
    monkeypatch.setattr(prices, "history", lambda symbol, start: (s, "EUR"))


def sans_reseau(monkeypatch):
    def boom(symbol, start):
        raise OSError("pas de réseau")

    monkeypatch.setattr(prices, "history", boom)


def test_les_comptes_viennent_de_la_base(base, monkeypatch):
    sans_reseau(monkeypatch)
    r = api.bourse()
    ids = [c["id"] for c in r["comptes"]]
    assert {"tr_cto", "tr_pea"} <= set(ids) and set(r["par_compte"]) == set(ids)
    assert all(c["nom"] for c in r["comptes"])


def test_somme_des_comptes_egale_le_total(base, monkeypatch):
    sans_reseau(monkeypatch)
    r = api.bourse()
    comptes = r["par_compte"].values()
    assert sum(c["valeur"] for c in comptes) == pytest.approx(r["tous"]["valeur"], abs=0.05)
    assert sum(c["nb_lignes"] for c in comptes) == r["tous"]["nb_lignes"]
    for champ in ("plus_value_realisee", "dividendes", "frais"):
        assert sum(c[champ] for c in comptes) == pytest.approx(r["tous"][champ], abs=0.05)
    connus = [c for c in comptes if c["cout_connu"]]
    assert sum(c["gain_total"] for c in connus) == pytest.approx(r["tous"]["gain_total"], abs=0.05)
    assert sum(p["valeur"] for p in r["tous"]["positions"]) == pytest.approx(r["tous"]["valeur"], abs=0.5)
    g = r["tous"]
    assert g["gain_total"] == pytest.approx(g["plus_value_latente"] + g["plus_value_realisee"] + g["dividendes"], abs=0.02)


def test_une_periode_serie_variation_et_indice(base, monkeypatch):
    indice_factice(monkeypatch)
    p = api.bourse()["tous"]["periodes"]["3M"]
    assert p["intraday"] and len(p["serie"]) >= 20 and len(p["serie"]) <= bourse.MAX_POINTS
    assert p["serie"][0][0] == p["depuis"] and p["serie_pct"][0][1] == 0
    assert p["variation_pct"] is not None and p["indice_pct"] is not None and p["indice_pct"] > 0
    assert len(p["indice_serie"]) == len(p["serie"]) and p["indice_serie"][0][1] == 0
    assert set(p["comptes"]) == {c["id"] for c in api.bourse()["comptes"]}
    assert all(len(s) == len(p["serie"]) for s in p["comptes"].values())


def test_un_jour_sans_intrajournalier(base, monkeypatch):
    sans_reseau(monkeypatch)
    with db.session(base / "patrimoine.db") as con:  # le jeu fictif porte une séance : on la retire (cours en séance : test_seance.py)
        con.execute("DELETE FROM prices_intraday")
    j = api.bourse()["tous"]["periodes"]["1J"]
    assert j["intraday"] is False and j["serie"] == []
    assert j["variation"] is not None and j["variation_pct"] is not None and j["depuis"]


def test_compte_sans_dividendes(base, monkeypatch):
    sans_reseau(monkeypatch)
    r = api.bourse()
    sans = [c for c in r["par_compte"].values() if c["dividendes"] == 0]
    assert sans, "le jeu fictif doit avoir un compte sans dividendes"
    d = sans[0]["dividendes_12m"]
    assert d["total"] == 0 and len(d["par_mois"]) == 12 and all(m["montant"] == 0 for m in d["par_mois"])
    avec = r["tous"]["dividendes_12m"]
    assert avec["total"] == pytest.approx(34.2) and "prochain" not in avec


def test_cout_inconnu_ne_donne_ni_investi_ni_gain(base, monkeypatch):
    sans_reseau(monkeypatch)
    r = api.bourse()
    inconnus = [c for c in r["par_compte"].values() if not c["cout_connu"]]
    assert inconnus
    assert all(c["investi"] is None and c["gain_total"] is None for c in inconnus)
    assert r["tous"]["cout_connu"] is False and r["tous"]["periodes"]["1A"]["investi"] == []


def test_sans_reseau_l_indice_est_null_sans_exception(base, monkeypatch):
    sans_reseau(monkeypatch)
    r = api.bourse()
    assert r["indice"]["disponible"] is False
    t = r["tous"]
    assert t["indice"] is None
    for label, p in t["periodes"].items():
        assert p["indice_pct"] is None and p["indice_serie"] == [], label
    assert t["periodes"]["1A"]["variation_pct"] is not None
    assert t["rendement_annualise"] is not None and t["plus_forte_baisse"] is not None


def test_repartition_rendements_et_lignes(base, monkeypatch):
    sans_reseau(monkeypatch)
    t = api.bourse()["tous"]
    assert {"compte", "type"} <= set(t["repartition"]) and "secteur" not in t["repartition"]
    assert sum(x["poids"] for x in t["repartition"]["type"]) == pytest.approx(1, abs=0.01)
    assert all({"annee", "mois", "rendement"} <= set(m) for m in t["rendements_mensuels"])
    ligne = t["positions"][0]
    assert set(ligne["variation"]) == set(bourse.PERIODES) and ligne["compte"] and ligne["nom"]


def test_appel_mobile_json(base, monkeypatch):
    sans_reseau(monkeypatch)
    assert json.loads(mobile.init(str(base)))["ok"]
    r = json.loads(mobile.call("bourse", "{}"))
    assert r["ok"] and r["data"]["tous"]["valeur"] > 0
