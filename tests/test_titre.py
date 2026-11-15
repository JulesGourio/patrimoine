"""Outil `titre` (fiche d'un titre) sur le jeu fictif : cours, périodes, position par compte, opérations, états vides."""
import pytest

from patrimoine import api, bourse, db, demo, prices

ACTION, ETF, PEG = "DE000DEMO001", "IE000DEMO005", "NL0000235190"


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    demo.build(tmp_path / "patrimoine.db")
    bourse._INDICE.clear()
    return tmp_path


def test_cours_et_periodes(base):
    t = api.titre(ACTION)
    assert t["nom"] == "Aérostar Industries" and t["type"] == "Actions" and t["symbole"] == "AERO.PA" and t["detenu"]
    assert set(t["periodes"]) == {"1J", "1S", "1M", "3M", "YTD", "1A", "MAX"}
    for p in t["periodes"].values():
        assert len(p["serie"]) <= 120
    j = t["periodes"]["1J"]
    assert j["intraday"] and j["serie"][-1][1] == pytest.approx(t["cours"], abs=1e-3) and "T" in j["serie"][0][0]
    assert j["pct"] == pytest.approx(j["serie"][-1][1] / j["base"] - 1, abs=1e-3)
    a = t["periodes"]["1A"]
    assert a["serie"][-1][1] == pytest.approx(t["cours"], abs=0.01)
    assert a["pct"] == pytest.approx(a["serie"][-1][1] / a["serie"][0][1] - 1, abs=1e-3)
    assert set(t["variations"]) == {"1J", "1S", "1M", "3M", "YTD", "1A"}
    assert t["variations"]["1J"]["pct"] == j["pct"]
    assert t["risque"]["volatilite"] > 0 and t["risque"]["plus_forte_baisse"] < 0


def test_la_position_vient_de_la_base_et_se_decompose_par_compte(base):
    t = api.titre(ACTION)
    p = t["position"]
    pos = {x["isin"]: x for x in api.positions()["positions"] if x["isin"] == ACTION}
    assert p["valeur"] == pytest.approx(sum(x["value"] for x in api.positions()["positions"] if x["isin"] == ACTION), abs=0.05)
    assert p["pmp"] == pytest.approx(p["investi"] / p["quantite"], rel=1e-3)  # la sortie JSON arrondit les quantités à 2 décimales
    assert p["plus_value"] == pytest.approx(p["valeur"] - p["investi"], abs=0.05)
    assert p["plus_value_pct"] == pytest.approx(p["plus_value"] / p["investi"], abs=1e-3)
    assert p["variation_jour"] == pytest.approx(p["quantite"] * t["periodes"]["1J"]["eur"], abs=0.05)
    total = api.bourse()["tous"]["valeur"]
    assert p["poids"] == pytest.approx(p["valeur"] / total, abs=0.002)
    assert sum(c["valeur"] for c in p["comptes"]) == pytest.approx(p["valeur"], abs=0.05)
    assert sum(c["quantite"] for c in p["comptes"]) == pytest.approx(p["quantite"], abs=1e-4)
    assert pos  # la ligne existe aussi dans `positions`


def test_un_titre_detenu_dans_deux_comptes_a_une_ligne_par_compte(base):
    with db.session(base / "patrimoine.db") as con:
        con.execute("UPDATE transactions SET holding_account_id = 'tr_cto' WHERE isin = ? AND holding_account_id = 'tr_pea'", (ETF,))
        con.execute(
            "INSERT INTO transactions (id, account_id, holding_account_id, date, amount_cents, label, flow, isin, quantity,"
            " price, fees_cents) VALUES ('t-pea', 'tr_especes', 'tr_pea', '2026-10-01', -50000, 'Achat', 'achat_titre', ?, 5, 100, 0)", (ETF,))
    t = api.titre(ETF)
    assert {c["id"] for c in t["position"]["comptes"]} == {"tr_cto", "tr_pea"}
    assert all(c["nom"] for c in t["position"]["comptes"])
    assert sum(c["valeur"] for c in t["position"]["comptes"]) == pytest.approx(t["position"]["valeur"], abs=0.05)


def test_un_titre_sans_prix_de_revient(base):
    t = api.titre(PEG)
    p = t["position"]
    assert p["valeur"] > 0 and p["pmp"] is None and p["investi"] is None and p["plus_value"] is None
    assert p["plus_value_pct"] is None and p["comptes"][0]["pmp"] is None
    assert t["pmp"] is None and t["operations"] == [] and t["dividendes"] is None
    assert t["periodes"]["1A"]["serie"]


def test_operations_et_dividendes(base):
    t = api.titre(ACTION)
    ops = t["operations"]
    assert [o["date"] for o in ops] == sorted((o["date"] for o in ops), reverse=True)
    assert {o["sens"] for o in ops} >= {"achat", "dividende"}
    for o in ops:
        if o["sens"] == "achat":
            assert o["quantite"] > 0 and o["prix"] > 0 and o["montant"] == pytest.approx(o["quantite"] * o["prix"] + o["frais"], abs=0.02)
        if o["sens"] == "dividende":
            assert o["prix"] is None and o["montant"] > 0
    d = t["dividendes"]
    assert d["total"] == pytest.approx(sum(o["montant"] for o in ops if o["sens"] == "dividende"), abs=0.01)
    assert d["dernier"]["montant"] > 0 and t["nb_operations"] == len(ops)
    # un titre qui n'a pas versé de dividende n'a pas de carte
    assert api.titre(ETF)["dividendes"] is None


def test_une_vente_est_une_operation_de_sens_vente(base):
    ventes = [o for o in api.titre("US000DEMO003")["operations"] if o["sens"] == "vente"]
    assert len(ventes) == 1 and ventes[0]["quantite"] == 2


def test_le_symbole_donne_le_meme_titre_que_l_isin(base):
    assert api.titre("AERO.PA")["isin"] == ACTION


def test_titre_inconnu_ou_sans_cours_ne_plante_pas(base):
    t = api.titre("ZZ0000000000")
    assert t["detenu"] is False and t["cours"] is None and t["position"] is None
    assert t["operations"] == [] and all(not p["serie"] for p in t["periodes"].values())
    with db.session(base / "patrimoine.db") as con:
        con.execute("DELETE FROM prices_intraday")
    sans = api.titre(ACTION)
    assert sans["periodes"]["1J"]["intraday"] is False and sans["periodes"]["1J"]["serie"] == []
    assert sans["periodes"]["1J"]["pct"] is not None  # variation entre les deux dernières clôtures


def test_cours_garde_ses_operations(base):
    c = api.cours(ACTION)
    assert c["cours"] and c["pmp"] and {"date", "sens", "quantite", "prix"} <= set(c["operations"][0])


def test_hors_ligne_la_fiche_se_construit(base, monkeypatch):
    def boom(*a, **k):
        raise OSError("hors ligne")

    monkeypatch.setattr(prices, "history", boom)
    monkeypatch.setattr(prices, "intraday", boom)
    with db.session(base / "patrimoine.db") as con:
        con.execute("DELETE FROM meta WHERE key = 'demo'")
    assert api.titre(ACTION)["periodes"]["1J"]["intraday"] is True
