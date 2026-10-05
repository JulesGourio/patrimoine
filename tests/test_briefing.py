import pandas as pd

from patrimoine import brief_mail, briefing

FACTS = {
    "periode": "jour", "seance": "2026-09-29",
    "patrimoine": {"total": 71450.0, "date": "2026-09-29", "effet_marche_eur": 247.5, "titres": 61550.0},
    "lignes": [
        {"isin": "FR0010342592", "nom": "Nasdaq 100 2x", "move": 0.0168, "impact_eur": 103.9, "indice": "Nasdaq 100",
         "indice_symbole": "^NDX", "indice_move": 0.0067, "levier": 2.0, "last": 10.4},
        {"isin": "NL0000235190", "nom": "Airbus SE", "move": -0.012, "impact_eur": -250.0, "indice": "CAC 40",
         "indice_symbole": "^FCHI", "indice_move": -0.0089, "levier": 1.0, "last": 190.6},
    ],
    "marche": [{"symbole": "^GSPC", "nom": "S&P 500", "move": 0.003, "m1": 0.001, "z": 0.4, "last": 7694.0},
               {"symbole": "^TNX", "nom": "Taux US 10 ans", "move": 0.04, "m1": 0.5, "z": 0.9, "last": 5.3}],
    "secteurs": [{"symbole": "XLK", "nom": "Technologie", "move": 0.01, "z": 0.6},
                 {"symbole": "ITA", "nom": "Aéro et défense", "move": -0.008, "z": -0.6}],
    "series": {},
}
ANALYSIS = {
    "titre": "La tech porte tes titres, Airbus recule", "ton": "mitigé",
    "points_cles": ["Tes titres +248 € (+0,4 %).", "Airbus -1,2 % sur un problème de fournisseur."],
    "lignes": [{"isin": "NL0000235190", "cause": "Retard de moteurs.", "these": "Intacte.", "verdict": "surveiller",
                "confiance": "moyenne", "sources": [1]}],
    "marche": {"resume": "Séance calme.", "themes": [{"titre": "Taux", "detail": "Le 10 ans monte.", "sources": [1]}]},
    "conseils": [{"action": "renforcer", "cible": "Airbus", "ticker": "AIR.PA", "cours_ref": 190.5, "montant_eur": 500,
                  "horizon": "6 mois", "pourquoi": "Baisse excessive.", "risque": "Retards.", "invalidation": "< 170 €",
                  "confiance": "moyenne", "sources": [1]},
                 {"action": "attendre", "cible": "Nasdaq x2", "horizon": "1 semaine", "pourquoi": "Micron.",
                  "risque": "Aucun.", "invalidation": "–", "confiance": "faible"}],
    "idees": [], "agenda": [{"date": "2026-10-02", "evenement": "Emploi US", "enjeu": "Taux."}], "a_faire": [],
    "sources": [{"id": 1, "titre": "Airbus", "media": "Reuters", "url": "https://reuters.com/x", "date": "2026-09-29"}],
}


def test_validate_accepts_a_complete_analysis():
    assert briefing.validate(ANALYSIS) == []


def test_validate_catches_missing_sources_and_bad_verdicts():
    bad = {**ANALYSIS, "lignes": [{**ANALYSIS["lignes"][0], "verdict": "acheter", "sources": [9]}],
           "points_cles": ["x" * 300]}
    err = briefing.validate(bad)
    assert any("verdict" in e for e in err)
    assert any("source 9" in e for e in err)
    assert any("points_cles[0]" in e for e in err)


def test_stats_scales_the_move_by_usual_volatility():
    s = pd.Series([100.0, 101.0] * 40 + [110.0], index=pd.bdate_range("2026-01-01", periods=81))
    st = briefing.stats(s, 1)
    assert round(st["move"], 3) == round(110 / 101 - 1, 3)
    assert st["z"] > 3


def test_mail_renders_and_escapes():
    html = brief_mail.render("quotidien", FACTS, {**ANALYSIS, "titre": "<b>x</b>"})
    assert "&lt;b&gt;x&lt;/b&gt;" in html and "cid:lignes" in html and "surveiller" in html
    assert "+4 pb" in html  # rates in basis points
    assert brief_mail.chart(FACTS)[:4] == b"\x89PNG"


def test_advice_needs_an_amount_and_a_price_to_follow_it():
    bad = {**ANALYSIS, "conseils": [{**ANALYSIS["conseils"][0], "montant_eur": None, "ticker": None}]}
    err = briefing.validate(bad)
    assert any("montant_eur" in e for e in err) and any("cours_ref" in e for e in err)
    assert "Mes conseils" in brief_mail.render("quotidien", FACTS, ANALYSIS)
