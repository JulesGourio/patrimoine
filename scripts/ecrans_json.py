"""Écrit, pour chaque écran de l'appli, la réponse du moteur (JSON) dans un dossier : `python scripts/ecrans_json.py
SORTIE [--donnees DOSSIER]`. Sans --donnees, un jeu fictif est créé ; avec, la vraie base de ce dossier est lue
(lecture seule, jamais publiée). Ces fichiers alimentent les captures d'écran de l'appli (android/README.md)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from patrimoine import api, db, demo, mobile  # noqa: E402

ECRANS = [
    ("etat", {}), ("accueil", {}), ("references", {}), ("portefeuille", {}), ("depenses_ecran", {"mois": 13}),
    ("alertes", {}), ("analyses", {"n": 20}), ("ordres_proposes", {"statut": "proposé"}),
    ("vendeurs", {"recherche": "", "limite": 100}), ("cartes", {}), ("ventes_realisees", {}), ("positions", {}),
    ("projection", {}), ("abonnements", {}), ("bourse", {}),
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sortie")
    ap.add_argument("--donnees", help="dossier de données réel (copié, jamais modifié)")
    args = ap.parse_args()
    work = Path(tempfile.mkdtemp(prefix="patrimoine-ecrans-"))
    try:
        if args.donnees:
            shutil.copy(Path(args.donnees) / "patrimoine.db", work / "patrimoine.db")
        else:
            demo.build(work / "patrimoine.db")
        reply = json.loads(mobile.init(str(work)))
        if not reply["ok"]:
            raise SystemExit(reply)
        out = Path(args.sortie)
        out.mkdir(parents=True, exist_ok=True)
        calls = list(ECRANS)
        with db.session(work / "patrimoine.db") as con:
            for r in con.execute("SELECT isin FROM positions WHERE quantity > 0 GROUP BY isin"):
                calls.append(("titre", {"isin": r["isin"]}))
        for name, a in calls:
            r = json.loads(mobile.call(name, json.dumps(a)))
            if not r["ok"]:
                print(f"! {name} {a} : {r.get('message') or r}")
                continue
            key = name + ("-" + str(a["isin"]) if name == "titre" else "")
            (out / f"{key}.json").write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{len(list(out.glob('*.json')))} écrans écrits dans {out}")
    finally:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
