"""Corrections de relecture : séance plus récente que la clôture, rafraîchissement, dividendes d'une ligne vendue,
séance crypto, gain en pourcentage, jeu fictif (CLI et veille)."""
from datetime import datetime, timezone

import pandas as pd
import pytest

from patrimoine import api, bourse, cli, db, demo, mobile, prices

ACTION = "DE000DEMO001"


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    demo.build(tmp_path / "patrimoine.db")
    bourse._INDICE.clear()
    prices._ECHEC.clear()
    prices._ESSAI.clear()

    def boom(*a, **k):
        raise OSError("pas de réseau")

    monkeypatch.setattr(prices, "history", boom)
    monkeypatch.setattr(prices, "intraday", boom)
    yield tmp_path
    bourse._INDICE.clear()
    prices._ECHEC.clear()
    prices._ESSAI.clear()


def con_de(base):
    return db.connect(base / "patrimoine.db")


def sans_cloture_du_jour(base, isin=ACTION):
    """Séance du jour présente, ligne quotidienne du jour absente pour `isin`."""
    with con_de(base) as con:
        dernier = con.execute("SELECT MAX(date) FROM prices WHERE isin = ?", (isin,)).fetchone()[0]
        con.execute("DELETE FROM prices WHERE isin = ? AND date = ?", (isin, dernier))
    return dernier


def ligne_1j(r, isin=ACTION):
    return next(x for x in r["tous"]["positions"] if x["isin"] == isin)["variation"]["1J"]


def test_variation_1j_de_la_fiche_avec_seance_plus_recente_que_la_cloture(base):
    sans_cloture_du_jour(base)
    t = api.titre(ACTION)
    j = t["periodes"]["1J"]
    assert j["intraday"] and j["pct"] not in (None, 0)
    assert j["pct"] == pytest.approx(j["serie"][-1][1] / j["base"] - 1, abs=1e-3)
    assert t["position"]["variation_jour"] == pytest.approx(t["position"]["quantite"] * j["eur"], abs=0.05)
    assert t["variations"]["1J"]["pct"] == j["pct"]
    # même variation que la ligne de l'écran Bourse
    assert ligne_1j(api.bourse())["pct"] == pytest.approx(j["pct"], abs=2e-4)


def test_les_lignes_de_l_ecran_bourse_suivent_l_en_tete(base):
    sans_cloture_du_jour(base)
    r = api.bourse()
    tete = r["tous"]["periodes"]["1J"]
    assert tete["intraday"]
    assert sum(x["variation"]["1J"]["eur"] or 0 for x in r["tous"]["positions"]) == pytest.approx(tete["variation"], rel=0.01)
    assert ligne_1j(r)["pct"] != 0


# ---------- rafraîchissement ----------

MERCREDI_8H30 = datetime(2026, 11, 11, 7, 30, tzinfo=timezone.utc)  # 8 h 30 à Paris


def test_une_ligne_n_est_pas_redemandee_dans_les_15_minutes_meme_si_les_barres_sont_vieilles(base, monkeypatch):
    seen: list = []

    def fake(symbol, interval="5m", jours=5):
        seen.append(symbol)  # Yahoo renvoie les barres de la veille : la dernière reste vieille
        idx = pd.date_range("2026-11-10 08:00", "2026-11-10 08:55", freq="5min")
        return pd.Series([100.0] * len(idx), index=idx), "EUR"

    monkeypatch.setattr(prices, "intraday", fake)
    with con_de(base) as con:
        con.execute("INSERT OR REPLACE INTO instruments VALUES ('XX0000000001', 'Test', 'TST.PA', 'action', 'EUR')")
        prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_8H30)
        prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_8H30.replace(minute=40))
        assert seen == ["TST.PA"]
        prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_8H30.replace(minute=50))
        assert len(seen) == 2


# ---------- dividendes ----------

def vendre_une_ligne_avec_dividende(base):
    isin = "XX0000000009"
    with con_de(base) as con:
        con.execute("INSERT OR REPLACE INTO instruments VALUES (?, 'Ligne vendue', 'VEND.PA', 'action', 'EUR')", (isin,))
        for i, (d, flow, cents, q, px_, hold) in enumerate([
                ("2026-02-02", "achat_titre", -100000, 10, 100, "tr_cto"),
                ("2026-05-04", "dividende", 12345, None, None, None),
                ("2026-08-03", "vente_titre", 110000, 10, 110, "tr_cto"),
                ("2026-09-07", "dividende", 5000, None, None, None)]):
            con.execute(
                "INSERT INTO transactions (id, account_id, holding_account_id, date, amount_cents, label, flow, isin,"
                " quantity, price, fees_cents) VALUES (?, 'tr_especes', ?, ?, ?, 'x', ?, ?, ?, ?, 0)",
                (f"div{i}", hold, d, cents, flow, isin, q, px_))
    return isin


def test_dividende_d_une_ligne_entierement_vendue_est_compte(base):
    avant = api.bourse()["tous"]
    isin = vendre_une_ligne_avec_dividende(base)
    bourse._INDICE.clear()
    apres = api.bourse()["tous"]
    assert apres["dividendes"] - avant["dividendes"] == pytest.approx(173.45, abs=0.01)
    assert apres["gain_total"] - avant["gain_total"] == pytest.approx(
        (apres["plus_value_realisee"] - avant["plus_value_realisee"]) + 173.45, abs=0.05)
    dv = api.bourse()["par_compte"]["tr_cto"]["dividendes"]
    assert dv >= 173.45
    assert apres["dividendes_12m"]["total"] - avant["dividendes_12m"]["total"] == pytest.approx(173.45, abs=0.01)
    assert isin


# ---------- séance crypto, gain ----------

def test_une_cloture_plus_recente_d_un_seul_titre_n_efface_pas_la_seance(base):
    with con_de(base) as con:
        con.execute("INSERT OR REPLACE INTO instruments VALUES ('XX0000000002', 'Crypto', 'BTC-EUR', 'crypto', 'EUR')")
        con.execute("INSERT INTO prices VALUES ('XX0000000002', '2999-01-01', 10.0, 'test')")
        con.execute("INSERT INTO prices_intraday VALUES ('XX0000000002', '2026-01-01T10:00:00Z', 10.0, 'test')")
        px = bourse.portfolio.replay(con)[1]
        se = bourse.charger_seance(con, px)
    assert se is not None and "XX0000000002" not in se.brut and ACTION in se.brut


def test_gain_total_pct_exige_un_investi_positif(base):
    with con_de(base) as con:
        con.execute("UPDATE transactions SET amount_cents = 0 WHERE flow IN ('virement_interne', 'interne')"
                    " AND account_id = 'tr_especes'")
    t = api.bourse()["tous"]
    assert t["investi"] is None or t["investi"] > 0 or t["gain_total_pct"] is None


# ---------- jeu fictif ----------

def test_demo_refuse_le_dossier_de_donnees(tmp_path, monkeypatch):
    from argparse import Namespace

    from patrimoine.config import Settings

    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    s = Settings()
    with pytest.raises(SystemExit):
        cli.cmd_demo(Namespace(dossier=None), s)
    with pytest.raises(SystemExit):
        cli.cmd_demo(Namespace(dossier=str(tmp_path)), s)


def test_la_veille_ne_met_pas_a_jour_les_cours_du_jeu_fictif(base, monkeypatch):
    appels: list = []
    monkeypatch.setattr(prices, "update", lambda *a, **k: appels.append("update"))
    monkeypatch.setattr(prices, "update_intraday", lambda *a, **k: appels.append("intraday"))
    mobile.veille(force=True)
    assert appels == []


# ---------- séance plus récente que la clôture : cohérence de la valeur et de la variation ----------

def recalculer_valuations(base):
    from patrimoine import portfolio
    with con_de(base) as con:
        df, _ = portfolio.valuations(con)
        portfolio.store(con, df)


def test_variation_1j_avec_valuations_a_la_cloture_d_hier(base):
    sans_cloture_du_jour(base)
    recalculer_valuations(base)
    j = api.bourse()["tous"]["periodes"]["1J"]
    assert j["intraday"] and j["serie"]
    assert j["variation_pct"] == pytest.approx(j["variation"] / j["cloture_precedente"], abs=1e-4)
    assert j["cloture_precedente"] == pytest.approx(j["serie"][-1][1] - j["variation"], abs=0.05)


def test_seance_dans_une_autre_unite_est_ignoree(base):
    sans_cloture_du_jour(base)
    with con_de(base) as con:
        con.execute("UPDATE prices_intraday SET close = close * 100 WHERE isin = ?", (ACTION,))
    j = api.titre(ACTION)["periodes"]["1J"]
    assert not j["intraday"]
    assert abs(j["pct"]) < 0.5
