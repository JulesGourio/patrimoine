from patrimoine.sources import amundi

INTERESSEMENT = """Relevé
d'Intéressement
Pour nous contacter
Valence, le 28/07/2026
A l'issue de cette opération, la valeur de vos avoirs au 28/07/2026 s'élève à : 22 343,43 €.
Récapitulatif de votre opération
30/06/2026
INVESTISSEMENT DE VOTRE INTERESSEMENT SUR PEG - AIRBUS EN ACTIONS : 13,8034 (Quantité) le
30/06/2026 à 191,50 € - DISPONIBLES LE 01/06/2031 2 643,36 € 0,00 €
Récapitulatif de votre épargne :
Support de placement Disponible Indisponible Total
ESOP SOUSCRIPTIONS 15 680,94 € 15 680,94 €
AIRBUS EN ACTIONS 6 662,49 € 6 662,49 €
Total 22 343,43 € 22 343,43 €"""

TRANSFERT = """Relevé de Transfert
Valence, le 08/04/2025
Récapitulatif de votre épargne :
ESOP SOUSCRIPTIONS 3 623,99 € 3 623,99 €
ESOP AIRBUS RELAIS 2025 5 949,89 € 5 949,89 €
AIRBUS EN ACTIONS 1 362,29 € 1 362,29 €"""


def test_statement_parsing():
    st = amundi.parse(INTERESSEMENT)
    assert st.date == "2026-07-28" and st.kind.startswith("Relevé d'Intéressement")
    (b,) = st.buys
    assert (b["quantity"], b["price"], b["amount"], b["date"]) == (13.8034, 191.5, 2643.36, "2026-06-30")
    assert st.supports == {"ESOP SOUSCRIPTIONS": 15680.94, "AIRBUS EN ACTIONS": 6662.49}
    # "RELAIS 2025" must not leak into the amount
    assert amundi.parse(TRANSFERT).supports["ESOP AIRBUS RELAIS 2025"] == 5949.89


def test_esop_becomes_share_equivalents():
    old = amundi.parse(TRANSFERT)
    new = amundi.parse(INTERESSEMENT)
    # direct shares before 2026: 10 at the 2025 statement (as if bought earlier)
    old.buys = [{"what": "participation", "quantity": 10.0, "date": "2024-06-28", "price": 130.0,
                 "available": "2029-06-01", "amount": 1300.0}]
    rows, summary = amundi.rows([old, new], close=lambda d: None)
    esop = [e for e in summary["esop_events"]]
    assert esop[0]["type"] == "souscription ESOP"          # 2025: 9573.88 € / 136.23 € ≈ 70.3 shares
    assert round(esop[0]["quantity"], 1) == round(9573.88 / 136.229, 1)
    assert summary["total_actions"] == round(sum(r.quantity for r in rows), 4)
