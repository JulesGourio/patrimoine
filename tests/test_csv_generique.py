"""Import CSV générique : fichiers inventés."""
import pytest

from patrimoine import db, imports
from patrimoine.config import Settings
from patrimoine.sources import csv_generique as gen


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=tmp_path / "data")
    with db.session(s.db_path) as con:
        db.init(con)
    return s


def write(tmp_path, text, encoding="utf-8", name="f.csv"):
    p = tmp_path / name
    p.write_bytes(text.encode(encoding))
    return p


def txs(settings):
    with db.session(settings.db_path) as con:
        return con.execute("SELECT date, amount_cents, label, flow FROM transactions ORDER BY date, amount_cents").fetchall()


def test_point_virgule_dates_francaises_montant_signe(settings, tmp_path):
    p = write(tmp_path, "Date;Libellé;Montant\n03/02/2026;CARTE BOULANGERIE;-12,50\n05/02/2026;VIR SALAIRE ACME;1 234,56\n")
    r = imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "amount": "Montant"})
    assert (r["lignes"], r["nouvelles"], r["doublons"]) == (2, 2, 0)
    assert [(t["date"], t["amount_cents"], t["flow"]) for t in txs(settings)] == [
        ("2026-02-03", -1250, "depense"), ("2026-02-05", 123456, "revenu")]


def test_virgule_iso_decimal_point(settings, tmp_path):
    p = write(tmp_path, 'date,label,amount\n2026-03-01,"Shop, Paris",-5.20\n2026-03-02,Refund,10.00\n')
    reglages = {"account": "cmb_courant", "delimiter": ",", "date_format": "%Y-%m-%d", "decimal": ".",
                "date": "date", "label": "label", "amount": "amount"}
    imports.csv_generique(settings, p, reglages=reglages)
    assert [t["amount_cents"] for t in txs(settings)] == [-520, 1000]
    assert txs(settings)[0]["label"] == "Shop, Paris"


def test_debit_credit(settings, tmp_path):
    p = write(tmp_path, "Date;Libellé;Débit;Crédit\n01/04/2026;LOYER;650,00;\n02/04/2026;PAIE;;2000,00\n")
    imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "debit": "Débit", "credit": "Crédit"})
    assert [t["amount_cents"] for t in txs(settings)] == [-65000, 200000]


def test_virement_entre_comptes_est_interne(settings, tmp_path):
    p = write(tmp_path, "Date;Libellé;Montant\n01/04/2026;VIR VERS LIVRET CMB;-100,00\n")
    imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "amount": "Montant"})
    assert txs(settings)[0]["flow"] == "interne"


def test_doublons_reimportes_et_lignes_identiques_le_meme_jour(settings, tmp_path):
    text = "Date;Libellé;Montant\n01/04/2026;CAFE;-2,00\n01/04/2026;CAFE;-2,00\n"
    reglages = {"account": "cmb_courant", "amount": "Montant"}
    p = write(tmp_path, text)
    assert imports.csv_generique(settings, p, reglages=reglages)["nouvelles"] == 2
    again = imports.csv_generique(settings, p, reglages=reglages)
    assert (again["nouvelles"], again["doublons"]) == (0, 2)
    p2 = write(tmp_path, text + "02/04/2026;CAFE;-2,00\n", name="g.csv")
    assert imports.csv_generique(settings, p2, reglages=reglages)["nouvelles"] == 1
    assert len(txs(settings)) == 3


def test_windows_1252_accents(settings, tmp_path):
    p = write(tmp_path, "Date;Libellé;Montant\n01/04/2026;PRÉLÈVEMENT ÉLECTRICITÉ €;-45,00\n", encoding="cp1252")
    imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "amount": "Montant", "encoding": "cp1252"})
    assert txs(settings)[0]["label"] == "PRÉLÈVEMENT ÉLECTRICITÉ €"


def test_profil_enregistre_puis_reutilise(settings, tmp_path):
    reglages = {"account": "cmb_courant", "amount": "Montant", "skip": 1}
    p = write(tmp_path, "Export banque\nDate;Libellé;Montant\n01/04/2026;A;-1,00\n")
    imports.csv_generique(settings, p, profil="maBanque", reglages=reglages, enregistrer=True)
    assert imports.csv_profiles(settings)["maBanque"]["skip"] == 1
    p2 = write(tmp_path, "Export banque\nDate;Libellé;Montant\n02/04/2026;B;-3,00\n", name="h.csv")
    assert imports.csv_generique(settings, p2, profil="maBanque")["nouvelles"] == 1


def test_sans_entete_par_numero_de_colonne(settings, tmp_path):
    p = write(tmp_path, "01/04/2026;X;-1,00\n")
    imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "header": False, "date": "0", "label": "1",
                                                 "amount": "2"})
    assert txs(settings)[0]["amount_cents"] == -100


def test_erreurs_claires(settings, tmp_path):
    p = write(tmp_path, "Date;Libellé;Montant\n99/99/2026;A;-1,00\n")
    with pytest.raises(ValueError, match="date illisible"):
        imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "amount": "Montant"})
    with pytest.raises(ValueError, match="colonne introuvable"):
        imports.csv_generique(settings, p, reglages={"account": "cmb_courant", "amount": "Autre"})
    with pytest.raises(ValueError, match="Compte inconnu"):
        imports.csv_generique(settings, p, reglages={"account": "nope", "amount": "Montant"})
    with pytest.raises(ValueError, match="profil inconnu"):
        imports.csv_generique(settings, p, profil="x")
    with pytest.raises(ValueError):
        gen.Profile.from_dict({"account": "a"})


def test_cents():
    assert gen.cents("1 234,56") == 123456
    assert gen.cents("-12.5", ".") == -1250
    assert gen.cents("(12,00)") == -1200
    assert gen.cents("") == 0
