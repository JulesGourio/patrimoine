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


def _con(base):
    from patrimoine import db
    return db.session(base / "patrimoine.db")


def _recalculer(c):
    from patrimoine import portfolio
    df, _ = portfolio.valuations(c)
    portfolio.store(c, df)


def test_transfert_de_titres_est_un_apport_pas_un_gain_de_marche(base):
    avant = api.accueil_ecran()["periodes"]["1M"]["cascade"]
    with _con(base) as c:
        isin, acc = c.execute("SELECT isin, account_id FROM transactions WHERE flow = 'achat_titre' AND isin IS NOT NULL LIMIT 1").fetchone()
        jour = c.execute("SELECT MAX(date) FROM transactions").fetchone()[0]
        demo._tx(c, 9100, __import__("datetime").date.fromisoformat(jour), acc, "transfert_titres", 0, "Transfert", "",
                 isin=isin, qty=10.0)
        c.commit()
        _recalculer(c)
    apres = api.accueil_ecran()["periodes"]["1M"]["cascade"]
    gain = apres["fin"] - avant["fin"]
    assert gain > 100  # le transfert a bien ajouté de la valeur
    assert apres["marches"] == pytest.approx(avant["marches"], abs=gain * 0.2)
    assert apres["epargne"] - avant["epargne"] == pytest.approx(gain, abs=gain * 0.2)
    assert apres["debut"] + apres["epargne"] + apres["marches"] + apres["dividendes"] == pytest.approx(apres["fin"], abs=0.05)


def test_compte_ouvert_depuis_moins_de_30_jours_sans_variation(base):
    with _con(base) as c:
        c.execute("INSERT INTO accounts (id, institution, name, kind, source) VALUES ('livret_neuf', 'X', 'Livret neuf', 'livret', 'manuel')")
        fin = c.execute("SELECT MAX(date) FROM valuations").fetchone()[0]
        c.execute("INSERT INTO valuations (date, account_id, cash_cents, securities_cents, cost_cents, realised_cents, deposits_cents)"
                  " VALUES (?, 'livret_neuf', 1000000, 0, 0, 0, 0)", (fin,))
        c.commit()
    cc = {x["id"]: x for x in api.accueil_ecran()["comptes"]}
    assert cc["livret_neuf"]["valeur"] == 10000.0
    assert cc["livret_neuf"]["var_30j"] is None and cc["livret_neuf"]["var_30j_pct"] is None


def test_carte_prepayee_hors_disponible(base):
    sans = api.accueil_ecran()["indicateurs"]
    with _con(base) as c:
        c.execute("INSERT INTO accounts (id, institution, name, kind, source) VALUES ('prepaye_x', 'X', 'Carte X', 'prepaye', 'manuel')")
        fin = c.execute("SELECT MAX(date) FROM valuations").fetchone()[0]
        c.execute("INSERT INTO valuations (date, account_id, cash_cents, securities_cents, cost_cents, realised_cents, deposits_cents)"
                  " VALUES (?, 'prepaye_x', 50000, 0, 0, 0, 0)", (fin,))
        c.commit()
    r = api.accueil_ecran()
    assert r["indicateurs"]["disponible_48h"] == sans["disponible_48h"]
    assert r["indicateurs"]["mois_precaution"] == sans["mois_precaution"]
    assert any(x["id"] == "prepaye_x" for x in r["comptes"])


def test_dividendes_des_seuls_comptes_presents(base):
    r0 = api.accueil_ecran()["periodes"]["MAX"]["cascade"]["dividendes"]
    with _con(base) as c:
        jour = c.execute("SELECT MAX(date) FROM valuations").fetchone()[0]
        c.execute("INSERT INTO accounts (id, institution, name, kind, source) VALUES ('compte_ferme', 'X', 'Fermé', 'livret', 'manuel')")
        demo._tx(c, 9200, __import__("datetime").date.fromisoformat(jour), "compte_ferme", "interets", 99_900_00, "Intérêts")
        c.commit()
    assert api.accueil_ecran()["periodes"]["MAX"]["cascade"]["dividendes"] == r0


def test_pea_cinq_ans(base):
    i = api.accueil_ecran()["indicateurs"]
    assert i["pea_ouverture"] and i["pea_5_ans_date"][:4] == str(int(i["pea_ouverture"][:4]) + 5)
