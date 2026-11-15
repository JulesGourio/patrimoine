"""Cours en séance (période 1J de l'écran Bourse) : stockage, rafraîchissement, série du jour, hors ligne."""
import sqlite3
from datetime import datetime, timezone

import pandas as pd
import pytest

from patrimoine import api, bourse, db, demo, prices


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    demo.build(tmp_path / "patrimoine.db")
    bourse._INDICE.clear()
    prices._ECHEC.clear()
    prices._ESSAI.clear()
    yield tmp_path
    bourse._INDICE.clear()
    prices._ECHEC.clear()
    prices._ESSAI.clear()


def hors_ligne(monkeypatch):
    def boom(*a, **k):
        raise OSError("pas de réseau")

    monkeypatch.setattr(prices, "history", boom)
    monkeypatch.setattr(prices, "intraday", boom)


def con_de(base):
    return db.connect(base / "patrimoine.db")


def test_la_serie_1j_finit_sur_la_valeur_du_jour(base, monkeypatch):
    hors_ligne(monkeypatch)
    r = api.bourse()
    j = r["tous"]["periodes"]["1J"]
    assert j["intraday"] is True and 20 <= len(j["serie"]) <= bourse.MAX_POINTS_JOUR
    assert j["serie"][-1][1] == pytest.approx(r["tous"]["valeur"], abs=0.02)
    assert "T" in j["serie"][0][0] and j["serie"][0][0][:10] == j["depuis"]
    assert j["variation"] == pytest.approx(j["serie"][-1][1] - j["cloture_precedente"], abs=0.02)
    assert j["serie_pct"][-1][1] == pytest.approx(j["variation_pct"], abs=1e-4)
    assert len(j["serie_pct"]) == len(j["serie"]) and j["indice_serie"] == []


def test_la_somme_des_comptes_vaut_le_total_a_chaque_instant(base, monkeypatch):
    hors_ligne(monkeypatch)
    r = api.bourse()
    tot = r["tous"]["periodes"]["1J"]
    assert set(tot["comptes"]) == set(r["par_compte"])
    for i, (stamp, v) in enumerate(tot["serie"]):
        assert sum(c["periodes"]["1J"]["serie"][i][1] for c in r["par_compte"].values()) == pytest.approx(v, abs=0.05)
        assert all(c["periodes"]["1J"]["serie"][i][0] == stamp for c in r["par_compte"].values())
    for acc, c in r["par_compte"].items():
        p = c["periodes"]["1J"]
        assert p["serie"][-1][1] == pytest.approx(c["valeur"], abs=0.02)
        assert p["comptes"].keys() == {acc}
    assert sum(c["periodes"]["1J"]["variation"] for c in r["par_compte"].values()) == pytest.approx(tot["variation"], abs=0.05)


def test_sans_cours_stockes_on_garde_le_comportement_precedent(base, monkeypatch):
    hors_ligne(monkeypatch)
    with con_de(base) as con:
        con.execute("DELETE FROM prices_intraday")
    j = api.bourse()["tous"]["periodes"]["1J"]
    assert j["intraday"] is False and j["serie"] == [] and j["variation"] is not None


def test_une_seance_perimee_n_est_pas_melangee_au_cours_du_jour(base, monkeypatch):
    hors_ligne(monkeypatch)
    with con_de(base) as con:
        con.execute("UPDATE prices_intraday SET ts = replace(ts, substr(ts, 1, 10), '2020-01-02')")
    assert api.bourse()["tous"]["periodes"]["1J"]["intraday"] is False


def test_base_sans_la_table_ne_plante_pas(base, monkeypatch):
    hors_ligne(monkeypatch)
    with con_de(base) as con:
        con.execute("DROP TABLE prices_intraday")
        assert bourse.charger_seance(con, bourse.portfolio.replay(con)[1]) is None


# ---------- rafraîchissement ----------

MERCREDI_10H = datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc)   # 10 h à Paris
MERCREDI_SOIR = datetime(2026, 11, 11, 21, 30, tzinfo=timezone.utc)  # 22 h 30 à Paris


def faux_cours(seen: list, jour="2026-11-11"):
    def fake(symbol, interval="5m", jours=5):
        seen.append(symbol)
        idx = pd.date_range(f"{jour} 08:00", f"{jour} 08:55", freq="5min")
        return pd.Series([100.0 + i for i in range(len(idx))], index=idx), "EUR"
    return fake


def instrument(con, isin="XX0000000001", symbol="TST.PA", currency="EUR", kind="action"):
    con.execute("INSERT OR REPLACE INTO instruments VALUES (?,?,?,?,?)", (isin, "Titre test", symbol, kind, currency))


def test_les_cours_manquants_sont_recuperes_et_stockes(base, monkeypatch):
    seen: list = []
    monkeypatch.setattr(prices, "intraday", faux_cours(seen))
    with con_de(base) as con:
        con.execute("DELETE FROM prices_intraday")
        instrument(con)
        n = prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_10H)
        assert n == {"XX0000000001": 12} and seen == ["TST.PA"]
        assert con.execute("SELECT COUNT(*), MAX(ts) FROM prices_intraday").fetchone()[:] == (12, "2026-11-11T08:55:00Z")


def test_pendant_la_seance_on_ne_recharge_qu_apres_15_minutes(base, monkeypatch):
    seen: list = []
    monkeypatch.setattr(prices, "intraday", faux_cours(seen))
    with con_de(base) as con:
        instrument(con)
        prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_10H)
        assert len(seen) == 1
        prices.update_intraday(con, ["XX0000000001"], now=datetime(2026, 11, 11, 9, 10, tzinfo=timezone.utc))
        assert len(seen) == 1                       # dernier cours de 8 h 55 UTC : 15 min pas dépassées
        prices.update_intraday(con, ["XX0000000001"], now=datetime(2026, 11, 11, 9, 20, tzinfo=timezone.utc))
        assert len(seen) == 2                       # 25 minutes : périmé
        prices.update_intraday(con, ["XX0000000001"], now=datetime(2026, 11, 11, 9, 20, tzinfo=timezone.utc), force=True)
        assert len(seen) == 3                       # la veille force


def test_hors_seance_la_derniere_seance_stockee_suffit(base, monkeypatch):
    seen: list = []
    monkeypatch.setattr(prices, "intraday", faux_cours(seen))
    with con_de(base) as con:
        instrument(con)
        prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_10H)
        prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_SOIR)
        assert len(seen) == 1
        # le lendemain soir de week-end : la séance à couvrir est celle du vendredi
        prices.update_intraday(con, ["XX0000000001"], now=datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc))
        assert len(seen) == 2


def test_hors_ligne_aucune_exception_et_les_cours_stockes_restent(base, monkeypatch):
    hors_ligne(monkeypatch)
    with con_de(base) as con:
        avant = con.execute("SELECT COUNT(*) FROM prices_intraday").fetchone()[0]
        assert avant > 0
        assert prices.update_intraday(con, force=True) == {}
        assert con.execute("SELECT COUNT(*) FROM prices_intraday").fetchone()[0] == avant


def test_la_source_en_panne_n_est_pas_redemandee_a_chaque_ecran(base, monkeypatch):
    appels: list = []

    def boom(symbol, **k):
        appels.append(symbol)
        raise OSError("hors ligne")

    monkeypatch.setattr(prices, "intraday", boom)
    with con_de(base) as con:
        instrument(con)
        for _ in range(3):
            prices.update_intraday(con, ["XX0000000001"], now=MERCREDI_10H)
    assert appels == ["TST.PA"]


def test_ecran_bourse_hors_ligne_sur_une_base_non_fictive(base, monkeypatch):
    """Base « réelle » (sans le drapeau démo) : l'écran tente de rafraîchir, échoue sans bruit et rend ce qu'il a."""
    hors_ligne(monkeypatch)
    with con_de(base) as con:
        con.execute("DELETE FROM meta WHERE key = 'demo'")
        con.commit()
    j = api.bourse()["tous"]["periodes"]["1J"]
    assert j["intraday"] is True


def test_conversion_en_euros_des_cours_en_pence_et_en_dollars(monkeypatch):
    idx = pd.date_range("2026-11-11 15:00", periods=3, freq="5min")
    brut = pd.Series([1000.0, 1010.0, 1020.0], index=idx)
    assert prices.intraday_eur(brut, "EUR", {}).tolist() == brut.tolist()
    monkeypatch.setattr(prices, "intraday", lambda sym, **k: (pd.Series([2.0, 2.0, 2.0], index=idx), "USD"))
    usd = prices.intraday_eur(brut, "USD", {})
    assert usd.tolist() == [500.0, 505.0, 510.0]
    assert prices.intraday_eur(brut, "XYZ", {}) is None


def test_purge_des_cours_de_plus_de_quelques_jours(base):
    with con_de(base) as con:
        con.execute("DELETE FROM prices_intraday")
        con.executemany("INSERT INTO prices_intraday VALUES ('A', ?, 1.0, 'test')",
                        [("2026-11-01T10:00:00Z",), ("2026-11-03T10:00:00Z",), ("2026-11-10T10:00:00Z",)])
        n = prices.purge_intraday(con, now=datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc), jours=7)
        assert n == 2
        assert [r[0] for r in con.execute("SELECT ts FROM prices_intraday")] == ["2026-11-10T10:00:00Z"]
        # la purge accompagne chaque rafraîchissement
        con.execute("INSERT INTO prices_intraday VALUES ('A', '2026-10-01T10:00:00Z', 1.0, 'test')")
        prices.update_intraday(con, [], now=datetime(2026, 11, 11, 9, 0, tzinfo=timezone.utc))
        assert con.execute("SELECT COUNT(*) FROM prices_intraday WHERE ts < '2026-11-04'").fetchone()[0] == 0


def test_la_table_est_creee_sans_toucher_aux_autres(tmp_path):
    con = sqlite3.connect(tmp_path / "vieille.db")
    con.row_factory = sqlite3.Row
    db.init(con)
    db.init(con)  # idempotent
    cols = {r[1] for r in con.execute("PRAGMA table_info(prices_intraday)")}
    assert cols == {"isin", "ts", "close", "source"}
    assert {r[1] for r in con.execute("PRAGMA table_info(prices)")} == {"isin", "date", "close", "source"}


def test_le_jeu_fictif_ne_demande_jamais_le_reseau(base, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("réseau demandé")

    monkeypatch.setattr(prices, "intraday", boom)
    monkeypatch.setattr(prices, "history", lambda *a, **k: (_ for _ in ()).throw(OSError("hors ligne")))
    assert api.bourse()["tous"]["periodes"]["1J"]["intraday"] is True
    assert api.titre("DE000DEMO001")["periodes"]["1J"]["intraday"] is True
