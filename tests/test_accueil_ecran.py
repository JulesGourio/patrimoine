"""Outil `accueil_ecran` (écran Patrimoine) sur le jeu fictif : cohérence avec `patrimoine`, périodes, cascade, comptes."""
import pytest

from patrimoine import api, demo


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    demo.build(tmp_path / "patrimoine.db")
    return tmp_path


def test_le_total_vient_de_la_base(base):
    r = api.accueil_ecran()
    assert r["total"] == pytest.approx(api.patrimoine()["total"], abs=0.01)
    assert sum(t["valeur"] for t in r["types"]) == pytest.approx(r["total"], abs=0.05)
    assert sum(c["valeur"] for c in r["comptes"]) == pytest.approx(r["total"], abs=0.05)
    assert r["nb_comptes"] == len(r["comptes"])
    assert [t["id"] for t in r["types"]] == ["placements", "courants", "livrets"]


def test_chaque_periode_a_une_cascade_qui_se_somme(base):
    r = api.accueil_ecran()
    assert set(r["periodes"]) == {"1S", "1M", "3M", "YTD", "1A", "MAX"}
    for label, p in r["periodes"].items():
        c = p["cascade"]
        assert c["fin"] == pytest.approx(r["total"], abs=0.01)
        assert c["debut"] + c["epargne"] + c["marches"] + c["dividendes"] == pytest.approx(c["fin"], abs=0.05), label
        assert p["variation"] == pytest.approx(c["fin"] - c["debut"], abs=0.05)
        assert p["variation_pct"] == pytest.approx(p["variation"] / c["debut"], abs=1e-3)
        assert len(p["serie"]) <= 120 and p["serie"][-1][1] == pytest.approx(r["total"], abs=0.01)
        for t, s in p["types"].items():  # aires empilées : même dates que le total, jamais négatives
            assert [x[0] for x in s] == [x[0] for x in p["serie"]]
            assert min(x[1] for x in s) >= 0


def test_la_variation_sur_30_jours_est_celle_de_patrimoine(base):
    r = api.accueil_ecran()
    assert r["periodes"]["1M"]["variation"] == pytest.approx(api.patrimoine()["variation_30j"], abs=1500)  # 1 mois civil, pas 30 j
    cc = {c["nom"]: c for c in r["comptes"]}
    assert cc["Livret CMB"]["var_30j"] == 0 and len(cc["Livret CMB"]["serie_30j"]) == 20
    assert cc["PEA"]["titres"] and not cc["Livret CMB"]["titres"]
    assert cc["PEA"]["var_30j_pct"] == pytest.approx(cc["PEA"]["var_30j"] / (cc["PEA"]["valeur"] - cc["PEA"]["var_30j"]), abs=1e-3)


def test_indicateurs(base):
    r = api.accueil_ecran()
    i = r["indicateurs"]
    liquide = sum(t["valeur"] for t in r["types"] if t["id"] in ("courants", "livrets"))
    assert i["disponible_48h"] == pytest.approx(liquide, abs=0.05)
    assert i["mois_precaution"] == pytest.approx(liquide / i["depenses_mensuelles"], abs=0.06)
    assert 0 < i["taux_epargne"] < 1 and i["apres_impots"] <= r["total"]


def test_base_vide(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    assert "erreur" in api.accueil_ecran()
