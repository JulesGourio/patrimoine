"""The fixed structure of a market analysis (see scripts/analyse.md) and its checks.

Standard library only: the cloud routine validates its analysis with `python -m patrimoine.brief_format file.json`
before pushing it, without installing anything.
"""
from __future__ import annotations

import json
import sys

TONES = ("haussier", "baissier", "mitigé", "calme")
VERDICTS = ("rien à faire", "surveiller", "agir")
CONFIDENCE = ("faible", "moyenne", "forte")
ACTIONS = ("acheter", "renforcer", "alléger", "vendre", "arbitrer", "attendre")


def validate(a: dict) -> list[str]:
    """Problems with an analysis, in French for Claude to fix (empty: fine). See scripts/analyse.md."""
    err = []

    def text(obj, key, where, limit, required=True):
        v = obj.get(key)
        if v is None or v == "":
            if required:
                err.append(f"{where}.{key} manquant")
            return
        if not isinstance(v, str):
            err.append(f"{where}.{key} doit être un texte")
        elif len(v) > limit:
            err.append(f"{where}.{key} trop long ({len(v)} > {limit} caractères) : fais plus court")

    def items(key, limit, required=False):
        v = a.get(key)
        if v is None:
            if required:
                err.append(f"{key} manquant")
            return []
        if not isinstance(v, list):
            err.append(f"{key} doit être une liste")
            return []
        if len(v) > limit:
            err.append(f"{key} : {len(v)} éléments, {limit} au plus")
        return v

    sources = items("sources", 25, required=True)
    ids = set()
    for i, s in enumerate(sources):
        if not isinstance(s, dict) or not s.get("url") or s.get("id") is None:
            err.append(f"sources[{i}] : id et url obligatoires")
            continue
        ids.add(s["id"])
        text(s, "titre", f"sources[{i}]", 200)
        text(s, "date", f"sources[{i}]", 25)

    def cites(obj, where, required=True):
        refs = obj.get("sources") or []
        if required and not refs:
            err.append(f"{where} : aucune source citée")
        for ref in refs:
            if ref not in ids:
                err.append(f"{where} : source {ref} absente de la liste des sources")

    text(a, "titre", "analyse", 90)
    if a.get("ton") not in TONES:
        err.append(f"ton : un de {', '.join(TONES)}")
    for i, p in enumerate(items("points_cles", 3, required=True)):
        if not isinstance(p, str) or len(p) > 200:
            err.append(f"points_cles[{i}] : un texte de 200 caractères au plus")
    for i, l in enumerate(items("lignes", 8)):
        w = f"lignes[{i}]"
        if not isinstance(l, dict):
            err.append(f"{w} doit être un objet")
            continue
        if not l.get("isin"):
            err.append(f"{w}.isin manquant")
        text(l, "cause", w, 280)
        text(l, "these", w, 220)
        if l.get("verdict") not in VERDICTS:
            err.append(f"{w}.verdict : un de {', '.join(VERDICTS)}")
        if l.get("confiance") not in CONFIDENCE:
            err.append(f"{w}.confiance : une de {', '.join(CONFIDENCE)}")
        if l.get("verdict") == "agir":
            text(l, "action", w, 200)
        cites(l, w, required=False)
    m = a.get("marche")
    if not isinstance(m, dict):
        err.append("marche manquant (objet avec resume et themes)")
    else:
        text(m, "resume", "marche", 300)
        for i, t in enumerate(m.get("themes") or []):
            text(t, "titre", f"marche.themes[{i}]", 80)
            text(t, "detail", f"marche.themes[{i}]", 300)
            cites(t, f"marche.themes[{i}]")
        if len(m.get("themes") or []) > 4:
            err.append("marche.themes : 4 au plus")
    for i, idea in enumerate(items("idees", 3)):
        w = f"idees[{i}]"
        for k, n in (("nom", 80), ("these", 300), ("risque", 200)):
            text(idea, k, w, n)
        cites(idea, w)
    for i, e in enumerate(items("agenda", 8)):
        text(e, "date", f"agenda[{i}]", 10)
        text(e, "evenement", f"agenda[{i}]", 120)
        text(e, "enjeu", f"agenda[{i}]", 150)
    for i, c in enumerate(items("conseils", 4, required=True)):
        w = f"conseils[{i}]"
        if not isinstance(c, dict):
            err.append(f"{w} doit être un objet")
            continue
        if c.get("action") not in ACTIONS:
            err.append(f"{w}.action : une de {', '.join(ACTIONS)}")
        if c.get("confiance") not in CONFIDENCE:
            err.append(f"{w}.confiance : une de {', '.join(CONFIDENCE)}")
        for k, n in (("cible", 80), ("pourquoi", 320), ("risque", 200), ("invalidation", 160), ("horizon", 40)):
            text(c, k, w, n)
        for k in ("montant_eur", "prix_limite", "cours_ref"):
            if c.get(k) is not None and not isinstance(c[k], (int, float)):
                err.append(f"{w}.{k} doit être un nombre")
        if c.get("action") != "attendre":
            if c.get("montant_eur") is None:
                err.append(f"{w}.montant_eur manquant : donne un montant en euros")
            if not c.get("ticker") or c.get("cours_ref") is None:
                err.append(f"{w} : ticker Yahoo et cours_ref (cours actuel) obligatoires pour suivre le conseil")
        cites(c, w, required=c.get("action") != "attendre")
    for i, t in enumerate(items("a_faire", 3)):
        if not isinstance(t, str) or len(t) > 240:
            err.append(f"a_faire[{i}] : un texte de 240 caractères au plus")
    text(a, "bilan_semaine", "analyse", 900, required=False)
    return err


if __name__ == "__main__":
    doc = json.loads(open(sys.argv[1], encoding="utf-8").read())
    problems = validate(doc.get("analyse", doc))
    print("\n".join(problems) or "ok")
    raise SystemExit(1 if problems else 0)
