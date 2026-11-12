"""Corrections de l'audit des données : date de référence, mois partiel, frais des fonds, impôt sur les intérêts,
détection des charges récurrentes."""
import json

import pandas as pd
import pytest

from patrimoine import analytics, api, db, notify, portfolio, queries, vault
from patrimoine.config import Settings

SPLIT = "ZZ0000SPLT01"  # fonds inventé, division par 200 le 10/07/2026
NOTER = "ZZ0000NOTER1"  # fonds inventé, sans TER connu


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(vault, "_backend", vault.KeyringBackend())
    monkeypatch.setattr(notify, "_local", None)
    monkeypatch.setitem(queries.TER, SPLIT, 0.0060)
    with db.session(Settings().db_path) as con:
        db.init(con)
        for a, kind in (("cmb_courant", "courant"), ("tr_especes", "especes"), ("tr_cto", "cto"),
                        ("cmb_livret_a", "livret")):
            con.execute("INSERT OR IGNORE INTO accounts (id, institution, name, kind) VALUES (?, 'X', ?, ?)", (a, a, kind))
    return tmp_path


def _tx(con, i, d, flow, cents=0, acc="cmb_courant", isin=None, qty=None, fees=0, holding=None, **kw):
    if isin:
        con.execute("INSERT OR IGNORE INTO instruments (isin, name) VALUES (?, ?)", (isin, f"Fonds {isin}"))
    r = {"id": f"t{i}", "account_id": acc, "holding_account_id": holding, "date": d, "flow": flow, "isin": isin,
         "quantity": qty, "amount_cents": cents, "fees_cents": fees,
         "raw_json": json.dumps({"timestamp": f"{d}T12:00:00.000+0000"}), **kw}
    con.execute(f"INSERT INTO transactions ({','.join(r)}) VALUES ({','.join('?' * len(r))})", list(r.values()))


def _mois_complets_puis_partiel():
    """Août et septembre complets (salaire 2000, dépenses 500), octobre arrêté au 27 (8 € de revenus, 300 de dépenses)."""
    with db.session(Settings().db_path) as con:
        n = 0
        for m in ("2026-08", "2026-09"):
            _tx(con, n + 1, f"{m}-02", "revenu", 200_000, category="Salaire")
            _tx(con, n + 2, f"{m}-10", "depense", -50_000, counterparty="Courses")
            n += 2
        _tx(con, 91, "2026-10-05", "revenu", 800, category="Aides")
        _tx(con, 92, "2026-10-27", "depense", -30_000, counterparty="Courses")
        _tx(con, 93, "2026-08-03", "achat_titre", -100_000, acc="tr_especes", isin=NOTER, qty=10, holding="tr_cto")
        con.execute("INSERT INTO prices VALUES (?, '2026-08-03', 100, 'test')", (NOTER,))
        con.execute("INSERT INTO prices VALUES (?, '2026-10-27', 110, 'test')", (NOTER,))
        df, _ = portfolio.valuations(con)
        portfolio.store(con, df)


# ---------- 1. date de référence et mois partiel ----------

def test_data_date_prefers_current_account_then_any(base):
    with db.session(Settings().db_path) as con:
        assert queries.data_date(con) == pd.Timestamp.today().normalize()
        _tx(con, 1, "2026-10-20", "depense", -100, acc="cmb_courant")
        _tx(con, 2, "2026-11-05", "interne", 100, acc="tr_especes")
        assert queries.data_date(con) == pd.Timestamp("2026-10-20")
        con.execute("DELETE FROM transactions WHERE id = 't1'")
        assert queries.data_date(con) == pd.Timestamp("2026-11-05")


def test_complete_months():
    bal = pd.DataFrame({"epargne": [1, 2, 3]}, index=pd.to_datetime(["2026-08-01", "2026-09-01", "2026-10-01"]))
    assert list(queries.complete_months(bal, pd.Timestamp("2026-10-27")).index.month) == [8, 9]
    assert list(queries.complete_months(bal, pd.Timestamp("2026-10-31")).index.month) == [8, 9, 10]


def test_flux_marque_le_mois_partiel(base):
    _mois_complets_puis_partiel()
    r = api.flux()
    json.dumps(r)
    assert r["donnees_au"] == "2026-10-27"
    by = {x["month"]: x for x in r["flux"]}
    assert by["2026-10-01"]["partiel"] is True and by["2026-10-01"]["taux_epargne"] is None
    assert by["2026-09-01"]["partiel"] is False and by["2026-09-01"]["taux_epargne"] == pytest.approx(0.75)


def test_epargne_par_defaut_ignore_le_mois_partiel(base):
    _mois_complets_puis_partiel()
    r = api.projection(horizon_ans=1)
    assert r["hypotheses"]["epargne_mensuelle"] == 1500  # (1500 + 1500) / 2, octobre exclu
    assert r["donnees_au"] == "2026-10-27"


def test_risques_synthese_performance_abonnements(base):
    _mois_complets_puis_partiel()
    r = api.risques(baisse_pct=30)
    assert r["donnees_au"] == "2026-10-27"
    assert r["epargne_mensuelle_moyenne"] == pytest.approx(1500)  # octobre (-292 €) exclu
    assert api.synthese()["epargne_moyenne"] == pytest.approx(1500)
    assert api.abonnements()["donnees_au"] == "2026-10-27"
    assert api.performance()["donnees_au"] == "2026-10-27"


# ---------- 2-4. frais ----------

def test_frais_fonds_apres_division_prix_quotidien(base):
    with db.session(Settings().db_path) as con:
        _tx(con, 1, "2026-06-01", "achat_titre", -1_000_000, acc="tr_especes", isin=SPLIT, qty=10, holding="tr_cto",
            fees=100)
        _tx(con, 2, "2026-07-10", "operation_titres", 0, acc="tr_especes", isin=SPLIT, qty=1990, holding="tr_cto")
        con.execute("INSERT INTO prices VALUES (?, '2026-06-01', 5, 'test')", (SPLIT,))  # cours ajusté de la division
        f = queries.fees_by_year(con)
    jours = (pd.Timestamp.today().normalize() - pd.Timestamp("2026-06-01")).days + 1
    # 10 000 € pendant toute la période (avant et après la division), TER 0,60 %
    assert f.frais_fonds.sum() == pytest.approx(jours * 10_000 * 0.006 / 365, rel=1e-6)


def test_frais_ordres_payants_et_executions_plans(base):
    with db.session(Settings().db_path) as con:
        _tx(con, 1, "2026-03-02", "achat_titre", -10_000, acc="tr_especes", isin=SPLIT, qty=1, holding="tr_cto", fees=100)
        _tx(con, 2, "2026-03-09", "achat_titre", -2_500, acc="tr_especes", isin=SPLIT, qty=1, holding="tr_cto")
        _tx(con, 3, "2026-03-16", "achat_titre", -2_500, acc="tr_especes", isin=SPLIT, qty=1, holding="tr_cto")
        con.execute("INSERT INTO prices VALUES (?, '2026-03-02', 100, 'test')", (SPLIT,))
    y = api.frais()["annees"]["2026"]
    assert y["ordres_payants"] == 1 and y["executions_plans"] == 2 and "ordres" not in y


def test_frais_signale_les_lignes_sans_ter(base):
    with db.session(Settings().db_path) as con:
        _tx(con, 1, "2026-03-02", "achat_titre", -10_000, acc="tr_especes", isin=NOTER, qty=1, holding="tr_cto", fees=100)
        _tx(con, 2, "2026-04-02", "vente_titre", 10_000, acc="tr_especes", isin=NOTER, qty=1, holding="tr_cto", fees=100)
        _tx(con, 3, "2026-03-02", "achat_titre", -10_000, acc="tr_especes", isin=SPLIT, qty=1, holding="tr_cto")
        con.execute("INSERT INTO prices VALUES (?, '2026-03-02', 100, 'test')", (NOTER,))
        con.execute("INSERT INTO prices VALUES (?, '2026-03-02', 100, 'test')", (SPLIT,))
    r = api.frais()
    json.dumps(r)
    assert [x["isin"] for x in r["isin_sans_ter"]] == [NOTER]  # vendu, mais détenu sur la période
    assert r["isin_sans_ter"][0]["nom"] == f"Fonds {NOTER}"
    assert "sous-estimés" in r["note_isin_sans_ter"]


# ---------- 5. intérêts ----------

def test_interets_de_livret_ne_comptent_pas_dans_l_impot(base):
    with db.session(Settings().db_path) as con:
        _tx(con, 1, "2026-12-31", "interets", 50_000, acc="cmb_livret_a")
        book, _ = portfolio.replay(con)
        assert portfolio.tax_summary(con, book) == {}
        _tx(con, 2, "2026-12-31", "interets", 1_000, acc="tr_especes", tax_cents=300)
        t = portfolio.tax_summary(con, book)[2026]
    assert t["interets"] == pytest.approx(13.0) and t["pfu_estime"] == pytest.approx(13.0 * 0.30 - 3.0)


# ---------- 6. charges récurrentes ----------

def _lignes(*paiements, categorie="Abonnements"):
    """paiements : (marchand, 'AAAA-MM-JJ', montant)"""
    df = pd.DataFrame([{"merchant": m, "date": pd.Timestamp(d), "amount": a, "category": categorie}
                       for m, d, a in paiements])
    df["month"] = df.date.dt.to_period("M").dt.to_timestamp()
    return df


def _mensuel(marchand, montants, debut="2026-01-05"):
    return [(marchand, (pd.Timestamp(debut) + pd.DateOffset(months=i)).date().isoformat(), a)
            for i, a in enumerate(montants)]


def test_recurring_hausse_de_prix():
    sp = _lignes(*_mensuel("Musique", [10.99] * 5 + [11.99] * 4))
    (r,) = analytics.recurring(sp).itertuples()
    assert r.amount == 11.99 and r.previous_amount == 10.99 and r.status == "actif"
    assert r.changed_on == pd.Timestamp("2026-06-05") and r.since == pd.Timestamp("2026-06-05")


def test_recurring_resilie():
    sp = _lignes(*_mensuel("Vieux", [9.99] * 7),
                 *_mensuel("Autre", [5.0] * 12))  # « Autre » fixe la date des données à décembre 2026
    assert "Vieux" not in set(analytics.recurring(sp).merchant)
    r = analytics.recurring(sp, include_ended=True).set_index("merchant")
    assert r.loc["Vieux", "status"] == "résilié" and r.loc["Autre", "status"] == "actif"


def test_recurring_facture_ponctuelle_au_meme_beneficiaire():
    paiements = _mensuel("Proprio", [590.0] * 8)
    paiements.append(("Proprio", "2026-08-20", 38.0))  # facture d'eau ponctuelle, dernier paiement en date
    r = analytics.recurring(_lignes(*paiements, categorie="Logement")).set_index("merchant")
    assert r.loc["Proprio", "amount"] == 590.0 and r.loc["Proprio", "status"] == "actif"
    assert pd.isna(r.loc["Proprio", "previous_amount"]) and r.loc["Proprio", "since"] == pd.Timestamp("2026-01-05")


def test_recurring_base_perimee_de_15_jours():
    # Série arrêtée il y a 15 jours : la base est périmée, pas la charge.
    fin = pd.Timestamp.today().normalize() - pd.Timedelta(days=15)
    sp = _lignes(*_mensuel("Forfait", [19.99] * 6, debut=(fin - pd.DateOffset(months=5)).date().isoformat()))
    assert analytics.recurring(sp).iloc[0].status == "actif"
    # Même série bien plus ancienne : « aujourd'hui » = date max des dépenses, donc toujours active.
    sp2 = _lignes(*_mensuel("Forfait", [19.99] * 6, debut="2024-01-05"))
    assert analytics.recurring(sp2, include_ended=True).iloc[0].status == "actif"


def test_recurring_garde_les_cles_existantes():
    cols = set(analytics.recurring(_lignes(*_mensuel("Musique", [10.0] * 4))).columns)
    assert {"merchant", "months", "median", "amount", "previous_amount", "changed_on", "since", "last", "category",
            "n", "status", "annual"} <= cols
