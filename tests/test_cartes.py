"""Cartes prépayées / comptes manuels : création, opérations, import de copier-coller, patrimoine, catégories."""
from datetime import date, timedelta

import pytest

from patrimoine import api, cartes, db, mobile, queries, vault
from patrimoine.categories import INCOME, categorize
from patrimoine.config import Settings
from patrimoine.sources import edenred


@pytest.fixture
def base(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    with db.session(Settings().db_path) as con:
        db.init(con)
        con.execute("INSERT INTO transactions (id, account_id, date, amount_cents, flow, raw_json) VALUES"
                    " ('x', 'cmb_courant', '2026-01-05', 100000, 'interne', '{}')")
    return tmp_path


def test_creation_sans_collision(base):
    a = api.creer_carte("Edenred", 12.5)
    assert a["id"] == "prepaye_edenred" and a["solde"] == 12.5
    assert "erreur" in api.creer_carte("edenred")  # même nom
    with db.session(Settings().db_path) as con:  # id déjà pris par un autre compte
        con.execute("INSERT INTO accounts (id, institution, name, kind, source) VALUES ('prepaye_swile', 'X', 'X', 'courant', 'manuel')")
    assert api.creer_carte("Swile")["id"] == "prepaye_swile_2"
    assert {c["id"] for c in api.cartes()["cartes"]} == {"prepaye_edenred", "prepaye_swile_2"}
    assert "erreur" in api.creer_carte("  ")


def test_credit_revenu_et_paiement_depense(base):
    api.creer_carte("Edenred")
    r = api.carte_operation("edenred", "2026-10-01", 120, "Versement employeur", "credit")
    assert r["ok"] and r["solde"] == 120.0
    r = api.carte_operation("prepaye_edenred", "2026-10-02", -11.4, "Boulangerie Dupont")
    assert r["solde"] == 108.6
    assert api.carte_operation("edenred", "2026-10-02", 11.4, "Boulangerie Dupont")["deja_presente"]
    assert api.carte_operation("edenred", "2026-10-02", 11.4, "Boulangerie Dupont", autoriser_doublon=True)["ajoutee"]
    with db.session(Settings().db_path) as con:
        inc, sp = queries.income(con), queries.spending(con)
        assert inc[inc.account_id == "prepaye_edenred"].category.tolist() == ["Titres-restaurant"]
        assert inc[inc.account_id == "prepaye_edenred"].amount.tolist() == [120.0]
        mine = sp[sp.account_id == "prepaye_edenred"]
        assert mine.amount.sum() == pytest.approx(22.8) and set(mine.account) == {"Edenred"}
        # le vendeur se renomme comme les autres
    assert api.renommer_vendeur("Boulangerie Dupont", "Boulangerie")["operations"] == 2
    assert "erreur" in api.carte_operation("inconnue", "2026-10-02", 1, "x")
    assert "erreur" in api.carte_operation("edenred", "pas-une-date", 1, "x")
    assert "erreur" in api.carte_operation("edenred", "2026-10-02", 1, "x", "autre")


def test_categorie_credit_survit_au_recalcul(base):
    assert "Titres-restaurant" in INCOME
    api.creer_carte("Edenred")
    api.carte_operation("edenred", "2026-10-01", 50, "Versement", "credit")
    with db.session(Settings().db_path) as con:
        from patrimoine import sync
        sync.recategorize(con)
        assert con.execute("SELECT category FROM transactions WHERE event_type = 'CARTE_CREDIT'").fetchone()[0] == "Titres-restaurant"
        assert categorize("depense", "MCDONALD PARIS", "MCDONALD PARIS", db.rules(con)) == "Restaurants et sorties"


def test_solde_ajustement_ni_revenu_ni_depense(base):
    api.creer_carte("Edenred")
    api.carte_operation("edenred", "2026-10-01", 100, "Versement", "credit")
    r = api.carte_solde("edenred", 87.3, "2026-10-10")
    assert r["ajustement"] and r["ecart"] == -12.7
    assert not api.carte_solde("edenred", 87.3, "2026-10-10")["ajustement"]  # déjà bon
    with db.session(Settings().db_path) as con:
        flows = dict(con.execute("SELECT event_type, flow FROM transactions WHERE account_id = 'prepaye_edenred'").fetchall())
        assert flows["CARTE_AJUSTEMENT"] == "interne"
        assert queries.spending(con).query("account_id == 'prepaye_edenred'").empty
    c = api.cartes()["cartes"][0]
    assert c["solde"] == 87.3 and c["credit_mensuel_moyen"] == 100.0


def test_dans_le_patrimoine(base):
    api.creer_carte("Edenred", 40)
    api.carte_operation("edenred", date.today().isoformat(), 15, "Resto", "paiement")
    p = api.patrimoine()
    assert p["comptes"]["Edenred"] == 25.0
    assert [c for c in api.synthese()["comptes"] if c["compte"] == "Edenred"][0]["groupe"] == "Liquidités"
    ref = mobile.references() if hasattr(mobile, "references") else None
    assert ref is not None


def test_import_idempotent_et_tolerant(base):
    api.creer_carte("Edenred")
    texte = (
        "Date;Libellé;Montant\n"
        "05/10/2026;Versement employeur;+120,00\n"
        "06/10/2026 BOULANGERIE PAUL -4,50 €\n"
        "2026-10-07\tCarrefour City\t-1 234,56\n"
        "07/10/2026\tCafé\t-2.50\n"
        "07/10/2026\tCafé\t-2.50\n"
        "12 nov. 2026 Resto U - 8,20 €\n"
        "n'importe quoi\n"
        "31/02/2026;Faux;-1,00\n"
        "08/10/2026;Sans montant\n"
    )
    ap = api.carte_import("edenred", texte, apercu=True)
    assert not ap["ecrit"] and ap["nouvelles"] == 6 and len(ap["ignorees"]) == 4
    assert {i["raison"] for i in ap["ignorees"]} >= {"date invalide", "pas de montant", "pas de date"}
    assert api.cartes()["cartes"][0]["operations"] == 0  # l'aperçu n'écrit rien
    r = api.carte_import("edenred", texte)
    assert r["nouvelles"] == 6 and r["credits"] == 120.0 and r["solde"] == pytest.approx(120 - 4.5 - 1234.56 - 5 - 8.2)
    types = {l["libelle"]: l["type"] for l in r["lignes"]}
    assert types["Versement employeur"] == "credit" and types["BOULANGERIE PAUL"] == "paiement"
    again = api.carte_import("edenred", texte)
    assert again["nouvelles"] == 0 and again["deja_presentes"] == 6 and again["solde"] == r["solde"]
    assert "erreur" in api.carte_import("nope", texte)


def test_credit_sans_signe_par_mot_cle(base):
    good, bad = cartes.parse_text("01/10/2026;Rechargement mensuel;120,00\n02/10/2026;Resto;12,00", date(2026, 11, 1))
    assert [g["type"] for g in good] == ["credit", "paiement"] and not bad


def test_date_sans_annee(base):
    today = date(2026, 3, 10)
    good, _ = cartes.parse_text("15/12 Resto -5,00", today)
    assert good[0]["date"] == "2025-12-15"


def test_solde_manuel_refuse_pour_une_carte(base):
    from patrimoine import imports

    api.creer_carte("Edenred")
    with pytest.raises(ValueError):
        imports.balance(Settings(), "prepaye_edenred", "10")


def test_references_mobile_et_vault_edenred(base):
    api.creer_carte("Edenred")
    ref = mobile.references()
    assert ref["cartes_prepayees"] == ["prepaye_edenred"]
    assert any(a["id"] == "prepaye_edenred" for a in ref["comptes"])
    assert "edenred_login" in vault.KNOWN and "edenred_password" in vault.KNOWN


def test_connecteur_edenred_squelette():
    with pytest.raises(NotImplementedError, match="MyEdenred"):
        edenred.login()
    with pytest.raises(NotImplementedError):
        edenred.Edenred().fetch_operations(date.today() - timedelta(days=30))
