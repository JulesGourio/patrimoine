"""Primes = revenus (PEG compris) et renommage des vendeurs."""
import pandas as pd

from patrimoine import analytics, api, db, queries
from patrimoine.categories import categorize


def _con(rows):
    con = db.connect(":memory:")
    db.init(con)
    con.executemany("INSERT INTO transactions (id, account_id, date, amount_cents, flow, category, counterparty, label,"
                    " event_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return con


def test_peg_primes_are_income_and_savings_but_still_invested():
    base = [("s", "cmb_courant", "2026-06-28", 200000, "revenu", "Salaire", None, None, None),
            ("d", "cmb_courant", "2026-06-10", -50000, "depense", "Courses", "X", None, None),
            ("esop", "peg_airbus", "2026-06-30", -10000, "achat_titre", None, None, None, "PEG_ESOP")]
    peg = [("i", "peg_airbus", "2026-06-30", -264336, "achat_titre", None, None, None, "PEG_INTERESSEMENT"),
           ("p", "peg_airbus", "2026-06-30", -138794, "achat_titre", None, None, None, "PEG_PARTICIPATION")]
    avant = analytics.monthly_balance(_con(base)).iloc[0]
    con = _con(base + peg)
    apres = analytics.monthly_balance(con).iloc[0]
    assert round(apres.revenus - avant.revenus, 2) == 4031.30 and round(apres.primes, 2) == 4031.30
    assert apres.depenses == avant.depenses  # not a spending
    assert round(apres.epargne - avant.epargne, 2) == 4031.30
    f = queries.flows_by_month(con).loc["2026-06-01"]
    assert f.achat_titre == -(264336 + 138794 + 10000) / 100  # investi_net inputs unchanged
    inc = queries.income(con)
    assert set(inc[inc.account == "PEG Airbus"].category) == {"Primes et intéressement"}
    assert round(inc[inc.category == "Primes et intéressement"].amount.sum(), 2) == 4031.30  # ESOP excluded


def test_bank_bonus_is_a_prime():
    rules = db.rules(db.init(c := db.connect(":memory:")) or c)
    assert categorize("revenu", "VIR AIRBUS OPERATIONS SAS PRIME EXCEPTIONNELLE", "AIRBUS OPERATIONS SAS", rules) == "Primes et intéressement"
    assert categorize("revenu", "VIR AIRBUS OPERATIONS SAS SALAIRE 01 2026", "AIRBUS OPERATIONS SAS", rules) == "Salaire"
    assert categorize("depense", "CB AMAZON PRIME", None, rules) == "Abonnements et télécom"
    con = _con([("s", "cmb_courant", "2026-03-28", 200000, "revenu", "Salaire", None, None, None),
                ("b", "cmb_courant", "2026-03-30", 150000, "revenu", "Primes et intéressement", None, None, None)])
    b = analytics.monthly_balance(con).iloc[0]
    assert b.revenus == 3500 and b.primes == 1500 and b.salaire == 2000


def _loyers(coupe=3):
    rows = []
    for m in range(1, 7):  # le même loyer, libellé « A » de janvier à mars puis « B » (nouvelle orthographe)
        rows.append((f"a{m}", "cmb_courant", f"2026-{m:02d}-05", -50000, "depense", "Logement et énergie",
                     "PROPRIO A" if m <= coupe else "PROPRIO B", None, None))
    return rows


def test_rename_merge_and_remove(monkeypatch):
    con = _con(_loyers())
    monkeypatch.setattr(api, "_con", lambda: con)
    r = api.renommer_vendeur("PROPRIO A", "Loyer")
    assert r["ok"] and r["operations"] == 3
    assert set(analytics.recurring(queries.spending(con)).merchant) == {"PROPRIO B"}  # 3 mois chacun : pas encore assez
    api.renommer_vendeur("PROPRIO B", "Loyer")
    sp = queries.spending(con)
    assert set(sp.merchant) == {"Loyer"} and set(sp.merchant_raw) == {"PROPRIO A", "PROPRIO B"}
    assert set(con.execute("SELECT counterparty FROM transactions WHERE flow='depense'").fetchall()[0]) == {"PROPRIO A"}
    (rec,) = analytics.recurring(sp).itertuples()
    assert rec.merchant == "Loyer" and rec.n == 6 and rec.months == 6
    # un nom d'affichage comme `raw` touche tous les noms bruts ; idempotent
    r = api.renommer_vendeur("Loyer", "Logement")
    assert r["operations"] == 6 and set(queries.spending(con).merchant) == {"Logement"}
    api.renommer_vendeur("Loyer", "Logement")
    assert con.execute("SELECT COUNT(*) FROM merchant_names").fetchone()[0] == 2
    # retrait
    api.renommer_vendeur("Logement", "")
    assert set(queries.spending(con).merchant) == {"PROPRIO A", "PROPRIO B"}
    assert con.execute("SELECT COUNT(*) FROM merchant_names").fetchone()[0] == 0
    assert "erreur" in api.renommer_vendeur("INCONNU", "x")


def test_not_subscription_and_search(monkeypatch):
    con = _con(_loyers(coupe=6))
    monkeypatch.setattr(api, "_con", lambda: con)
    assert set(analytics.recurring(queries.spending(con), include_ended=True, min_months=3).merchant)         == {"PROPRIO A"}
    api.renommer_vendeur("PROPRIO A", pas_abonnement=True)
    sp = queries.spending(con)
    assert analytics.recurring(sp, include_ended=True, min_months=3).empty
    assert set(sp[sp.merchant_raw == "PROPRIO A"].merchant) == {"PROPRIO A"}  # no rename, only the flag
    api.renommer_vendeur("PROPRIO A", "Bailleur'; DROP TABLE transactions; --")
    names = {v["brut"]: v for v in api.vendeurs()["vendeurs"]}
    assert names["PROPRIO A"]["pas_abonnement"] is True and names["PROPRIO A"]["operations"] == 6
    assert names["PROPRIO A"]["total"] == 3000.0 and names["PROPRIO A"]["affiche"].startswith("Bailleur")
    assert [v["brut"] for v in api.vendeurs("bailleur")["vendeurs"]] == ["PROPRIO A"]
    assert [v["brut"] for v in api.vendeurs("proprio a")["vendeurs"]] == ["PROPRIO A"]
    assert api.vendeurs("zzz")["vendeurs"] == [] and len(api.vendeurs(limite=1)["vendeurs"]) == 1
    api.renommer_vendeur("PROPRIO A", "", pas_abonnement=False)
    assert "PROPRIO A" in set(analytics.recurring(queries.spending(con), include_ended=True).merchant)
    assert con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 6


def test_old_database_without_the_table(monkeypatch):
    con = _con(_loyers())
    con.execute("DROP TABLE merchant_names")
    assert set(queries.spending(con).merchant) == {"PROPRIO A", "PROPRIO B"}
    monkeypatch.setattr(api, "_con", lambda: con)
    con.execute("DROP TABLE merchant_names")
    assert api.renommer_vendeur("PROPRIO B", "Autre")["operations"] == 3
    assert any(t.__name__ == "vendeurs" for t in api.TOOLS)
