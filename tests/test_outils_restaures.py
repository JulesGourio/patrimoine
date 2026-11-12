"""Outils `frais`, `pistes_fiscales`, `performance`, `risques`, `abonnements` (calculs de l'ancien tableau de bord)."""
import json
from datetime import date, timedelta

import pandas as pd
import pytest

from patrimoine import analytics, api, db, notify, portfolio, queries, vault
from patrimoine.config import Settings

LEV = "ZZ00000LEV01"  # ETF inventé à levier x2 (déclaré dans `base`)
TER_ISIN = "ZZ0000TER001"  # ETF inventé, TER 0,15 %
TODAY = date.today()
START = TODAY.replace(month=1, day=1)


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(vault, "_backend", vault.KeyringBackend())
    monkeypatch.setattr(notify, "_local", None)
    monkeypatch.setitem(analytics.LEVERAGE, LEV, 2.0)
    monkeypatch.setitem(analytics.CURRENCY, LEV, "USD")
    monkeypatch.setitem(analytics.CURRENCY, TER_ISIN, "USD")
    monkeypatch.setitem(queries.TER, LEV, 0.0060)
    monkeypatch.setitem(queries.TER, TER_ISIN, 0.0015)
    with db.session(Settings().db_path) as con:
        db.init(con)
    return tmp_path


def _tx(con, i, d, flow, isin=None, qty=None, cents=0, fees=0, acc="tr_cto", ts="12:00:00", **kw):
    if isin:
        con.execute("INSERT OR IGNORE INTO instruments (isin, name) VALUES (?, ?)", (isin, f"Titre {isin}"))
    r = {"id": f"t{i}", "account_id": "tr_especes", "holding_account_id": acc if isin else None, "date": d.isoformat(),
         "flow": flow, "isin": isin, "quantity": qty, "amount_cents": cents, "fees_cents": fees,
         "raw_json": json.dumps({"timestamp": f"{d.isoformat()}T{ts}.000+0000"}), **kw}
    con.execute(f"INSERT INTO transactions ({','.join(r)}) VALUES ({','.join('?' * len(r))})", list(r.values()))


def _portefeuille():
    """CTO : A gagne (+500), B perd (-400), C vendu avec +300 réalisés cette année ; PEA : ETF S&P 500 et Nasdaq x2."""
    with db.session(Settings().db_path) as con:
        for a, kind in (("tr_especes", "especes"), ("tr_cto", "cto"), ("tr_pea", "pea")):
            con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES (?, 'X', ?, ?)", (a, a, kind))
        _tx(con, 1, START, "achat_titre", "AAA", 10, -100_000)
        _tx(con, 2, START, "achat_titre", "BBB", 10, -100_000)
        _tx(con, 3, START, "achat_titre", "CCC", 10, -50_000, ts="09:00:00")
        _tx(con, 4, START, "vente_titre", "CCC", 10, 80_000, ts="15:00:00")
        _tx(con, 5, START, "achat_titre", TER_ISIN, 10, -100_000, acc="tr_pea", fees=100)
        _tx(con, 6, START, "achat_titre", LEV, 5, -50_000, acc="tr_pea")
        _tx(con, 7, START, "frais", cents=-470, account_id="cmb_courant")
        # cours du jour de l'achat = prix payé (sinon le moteur recale l'échelle des cours), puis cours actuel
        for isin, px0, px in (("AAA", 100, 150), ("BBB", 100, 60), ("CCC", 65, 80), (TER_ISIN, 100, 120), (LEV, 100, 100)):
            con.execute("INSERT INTO prices VALUES (?, ?, ?, 'test')", (isin, START.isoformat(), px0))
            if TODAY > START:
                con.execute("INSERT INTO prices VALUES (?, ?, ?, 'test')", (isin, TODAY.isoformat(), px))
        df, _ = portfolio.valuations(con)
        portfolio.store(con, df)


def _depenses():
    with db.session(Settings().db_path) as con:
        con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES ('cmb_courant', 'X', 'c', 'courant')")
        for m in range(5):  # abonnement stable tous les mois, courses variables et irrégulières
            d = TODAY - timedelta(days=30 * m + 3)
            _tx(con, 100 + m, d, "depense", cents=-1299, account_id="cmb_courant", counterparty="Musique+",
                category="Abonnements")
        _tx(con, 200, TODAY - timedelta(days=5), "depense", cents=-5000, account_id="cmb_courant", counterparty="Resto")


# ---------- sans données ----------

@pytest.mark.parametrize("nom", ["frais", "pistes_fiscales", "performance", "risques", "abonnements"])
def test_sans_donnees(base, nom):
    assert "erreur" in getattr(api, nom)()


def test_outils_declares():
    noms = {t.__name__ for t in api.TOOLS}
    assert {"frais", "pistes_fiscales", "performance", "risques", "abonnements"} <= noms


# ---------- frais ----------

def test_frais(base):
    _portefeuille()
    r = api.frais()
    json.dumps(r)
    y = r["annees"][str(TODAY.year)]
    assert y["banque"] == pytest.approx(4.70) and y["courtage"] == pytest.approx(1.0) and y["ordres"] == 6
    assert y["total"] == pytest.approx(y["banque"] + y["courtage"] + y["frais_fonds"])
    assert {x["isin"] for x in r["detail_fonds"]} == {TER_ISIN, LEV}
    sp = next(x for x in r["detail_fonds"] if x["isin"] == TER_ISIN)
    assert sp["cout_annuel"] == pytest.approx(1200 * 0.0015)
    assert r["frais_fonds_rythme_actuel"] == pytest.approx(1200 * 0.0015 + 500 * 0.006)


# ---------- pistes fiscales ----------

def test_pistes_fiscales(base):
    _portefeuille()
    r = api.pistes_fiscales()
    json.dumps(r)
    assert r["plus_values_realisees"] == pytest.approx(300)
    assert r["plus_value_latente_cto"] == pytest.approx(100)  # +500 - 400
    assert r["moins_values_latentes"] == pytest.approx(400)
    assert r["economie_estimee"] == pytest.approx(300 * 0.30)  # min(400, 300) x 30 %
    assert r["impot_si_tout_vendu"] == pytest.approx(100 * 0.30)
    assert [x["isin"] for x in r["lignes_en_perte"]] == ["BBB"]
    assert r["pea"]["atteint"] is False and r["pea"]["cinq_ans"] == START.replace(year=START.year + 5).isoformat()
    assert r["pistes"]


def test_pistes_sans_plus_value_pas_d_economie(base):
    with db.session(Settings().db_path) as con:
        con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES ('tr_especes', 'X', 'e', 'especes')")
        con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES ('tr_cto', 'X', 'c', 'cto')")
        _tx(con, 1, START, "achat_titre", "BBB", 10, -100_000)
        con.execute("INSERT INTO prices VALUES ('BBB', ?, 100, 'test')", (START.isoformat(),))
        con.execute("INSERT INTO prices VALUES ('BBB', ?, 60, 'test')", (TODAY.isoformat(),))
    r = api.pistes_fiscales()
    assert r["plus_values_realisees"] == 0 and r["economie_estimee"] == 0 and r["moins_values_latentes"] == pytest.approx(400)


# ---------- performance ----------

def test_performance(base):
    _portefeuille()
    r = api.performance()
    json.dumps(r)
    assert r["comptes"] == ["tr_cto", "tr_pea"]
    # valeur : AAA 1500 + BBB 600 + ETF 1200 + Nasdaq 500 ; net investi : 1000+1000+(500-800)+1000+500
    assert r["valeur"] == pytest.approx(3800) and r["net_investi"] == pytest.approx(3200)
    assert r["gain_total"] == pytest.approx(600)
    assert "indice" not in r
    assert api.performance(compte="pea")["comptes"] == ["tr_pea"]


def test_performance_erreurs(base):
    _portefeuille()
    assert "erreur" in api.performance(compte="livret")
    assert "erreur" in api.performance(indice="Bitcoin")


def test_performance_indice(base, monkeypatch):
    _portefeuille()
    monkeypatch.setattr(analytics, "benchmark", lambda con, v, sym: v.value * 0.9)
    r = api.performance(indice="msci world")
    assert r["indice"]["nom"] == "MSCI World" and r["indice"]["symbole"] == "IWDA.AS"
    assert r["indice"]["ecart_portefeuille"] == pytest.approx(r["valeur"] * 0.1)
    monkeypatch.setattr(analytics, "benchmark", lambda con, v, sym: None)
    assert api.performance(indice="CAC 40")["indice"]["erreur"] == "cours indisponibles"


# ---------- risques ----------

def test_risques(base):
    _portefeuille()
    r = api.risques(baisse_pct=20)
    json.dumps(r)
    # lignes : AAA 1500, BBB 600, ETF S&P 1200 (USD), Nasdaq x2 500 (USD, exposition 1000)
    assert r["valeur_investie"] == pytest.approx(3800) and r["exposition_reelle"] == pytest.approx(4300)
    assert r["part_a_levier"] == pytest.approx(500 / 3800, abs=1e-3)
    assert r["exposition_dollar"] == pytest.approx(2200) and r["part_dollar"] == pytest.approx(2200 / 4300, abs=1e-3)
    assert r["plus_grosse_ligne"]["nom"] == "Titre AAA"
    assert r["perte_estimee"] == pytest.approx(-(1500 + 600 + 1200 + 1000) * 0.2)
    nasdaq = next(x for x in r["lignes"] if x["levier"] == 2)
    assert nasdaq["perte_si_baisse"] == pytest.approx(-200)


def test_risques_levier_plafonne(base):
    _portefeuille()
    r = api.risques(baisse_pct=100)  # le x2 ne peut pas perdre plus que sa valeur
    assert next(x for x in r["lignes"] if x["levier"] == 2)["perte_si_baisse"] == pytest.approx(-500)
    assert "erreur" in api.risques(baisse_pct=0)


# ---------- abonnements ----------

def test_abonnements(base):
    _depenses()
    r = api.abonnements()
    json.dumps(r)
    (a,) = r["abonnements"]
    assert a["marchand"] == "Musique+" and a["montant_mensuel"] == pytest.approx(12.99)
    assert a["cout_annuel"] == pytest.approx(12.99 * 12) and a["mois"] >= 3
    assert r["total_annuel"] == pytest.approx(a["cout_annuel"])
    assert pd.Timestamp(a["dernier_paiement"]).date() <= TODAY


# ---------- pistes fiscales : moins-values reportables ----------

def _cto_avec_perte_latente(extra=None):
    """CTO : une ligne BBB en moins-value latente (-400) ; `extra(con)` ajoute d'autres opérations."""
    with db.session(Settings().db_path) as con:
        con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES ('tr_especes', 'X', 'e', 'especes')")
        con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES ('tr_cto', 'X', 'c', 'cto')")
        _tx(con, 1, START, "achat_titre", "BBB", 10, -100_000)
        con.execute("INSERT INTO prices VALUES ('BBB', ?, 100, 'test')", (START.isoformat(),))
        con.execute("INSERT INTO prices VALUES ('BBB', ?, 60, 'test')", (TODAY.isoformat(),))
        if extra:
            extra(con)


def _vente_annee(con, i, annee, achat, vente):
    d = date(annee, 3, 1)
    _tx(con, i, d, "achat_titre", "OLD", 10, -achat, ts="09:00:00")
    _tx(con, i + 1, d, "vente_titre", "OLD", 10, vente, ts="15:00:00")
    con.execute("INSERT OR IGNORE INTO prices VALUES ('OLD', ?, 1, 'test')", (d.isoformat(),))


def test_pistes_moins_values_reportees_reduisent_l_economie(base):
    def extra(con):
        _vente_annee(con, 10, TODAY.year - 1, 100_000, 70_000)  # -300 reportés
        _tx(con, 20, START, "achat_titre", "CCC", 10, -50_000, ts="09:00:00")
        _tx(con, 21, START, "vente_titre", "CCC", 10, 80_000, ts="15:00:00")  # +300 cette année
        _tx(con, 22, START, "achat_titre", "DDD", 10, -50_000, ts="09:30:00")
        _tx(con, 23, START, "vente_titre", "DDD", 10, 70_000, ts="15:30:00")  # +200 : 500 bruts
    _cto_avec_perte_latente(extra)
    r = api.pistes_fiscales()
    assert r["plus_values_realisees"] == pytest.approx(500)
    assert r["moins_values_reportables"] == 0  # 300 imputés sur 500
    assert r["economie_estimee"] == pytest.approx(min(400, 200) * 0.30)  # imposable = 200
    assert "200 € de plus-values imposables" in r["pistes"][0]


def test_pistes_pertes_reportees_effacent_les_gains_pas_d_economie(base):
    def extra(con):
        _vente_annee(con, 10, TODAY.year - 1, 100_000, 50_000)  # -500 reportés
        _tx(con, 20, START, "achat_titre", "CCC", 10, -50_000, ts="09:00:00")
        _tx(con, 21, START, "vente_titre", "CCC", 10, 80_000, ts="15:00:00")  # +300 : tout imputé
    _cto_avec_perte_latente(extra)
    r = api.pistes_fiscales()
    assert r["plus_values_realisees"] == pytest.approx(300)
    assert r["economie_estimee"] == 0
    assert r["moins_values_reportables"] == pytest.approx(200)


def test_pistes_annee_sans_ligne_reprend_le_report(base):
    _cto_avec_perte_latente(lambda con: _vente_annee(con, 10, TODAY.year - 2, 100_000, 60_000))  # -400
    # BBB acheté l'an dernier : pas de ligne fiscale pour l'année en cours
    with db.session(Settings().db_path) as con:
        con.execute("UPDATE transactions SET date = ? WHERE id = 't1'", (date(TODAY.year - 1, 1, 5).isoformat(),))
    r = api.pistes_fiscales()
    assert r["moins_values_reportables"] == pytest.approx(400)
    assert r["plus_value_latente_cto"] == pytest.approx(-400)
    assert r["impot_si_tout_vendu"] == 0
    assert any("400 € de moins-values reportables" in p for p in r["pistes"])


def test_pistes_report_de_plus_de_dix_ans_ecarte(base):
    _cto_avec_perte_latente(lambda con: _vente_annee(con, 10, TODAY.year - 11, 100_000, 60_000))
    r = api.pistes_fiscales()
    assert r["moins_values_reportables"] == 0


def test_carry_into():
    assert portfolio.carry_into({2020: -100.0, 2021: 40.0}, 2023) == pytest.approx(60)
    assert portfolio.carry_into({2010: -100.0}, 2021) == 0
    assert portfolio.carry_into({2010: -100.0}, 2020) == pytest.approx(100)
