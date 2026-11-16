"""Une connexion d'un appel d'outil ne doit pas garder le verrou de la base après l'appel (appli Android)."""
import sqlite3

from patrimoine import api, bourse, db, demo, mobile


def test_les_connexions_d_un_appel_sont_fermees_et_liberent_le_verrou(tmp_path, monkeypatch):
    monkeypatch.setenv("PATRIMOINE_DATA_DIR", str(tmp_path))
    demo.build(tmp_path / "patrimoine.db")

    @api.tool
    def _ecriture_oubliee() -> dict:
        con = api._con()
        con.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('test_verrou', '1')")  # jamais validée
        return {"ok": True}

    try:
        mobile._call("_ecriture_oubliee", "{}")
        autre = sqlite3.connect(tmp_path / "patrimoine.db", timeout=0.2)
        autre.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('autre', '2')")  # échouerait si verrouillée
        autre.commit()
        autre.close()
    finally:
        api.TOOLS[:] = [f for f in api.TOOLS if f.__name__ != "_ecriture_oubliee"]


def test_fin_de_mois_compatible_avec_l_ancien_pandas():
    assert bourse.FIN_DE_MOIS in ("ME", "M")
