"""Parser tests on anonymised events copied from a real Trade Republic dump (September 2026)."""
from patrimoine import db, sync
from patrimoine.categories import NON_CASH_FLOWS
from patrimoine.sources.tr_parse import number, parse

MAIN_CASH, PEA_CASH, CTO = "0000000011", "0000000013", "0000000002"


def ev(id, et, ts, title, value, icon="logos/merchant-x/v2", subtitle=None, status="EXECUTED", cash=None):
    return {"id": id, "eventType": et, "timestamp": ts, "title": title, "subtitle": subtitle, "icon": icon,
            "amount": None if value is None else {"currency": "EUR", "value": value}, "status": status,
            "cashAccountNumber": cash, "deleted": False}


def detail(rows, isin=None, title="Synthèse"):
    sections = [{"type": "header", "title": "…",
                 "action": {"type": "instrumentDetail", "payload": isin} if isin else None}]
    sections.append({"type": "table", "title": title,
                     "data": [{"title": k, "detail": {"text": v}} for k, v in rows.items()]})
    return {"sections": sections}


def dump(events, details, positions=None):
    return {
        "account": {"name": {"first": "Jean Marc", "last": "Dupré"}, "securitiesAccountNumber": CTO},
        "transactions": events, "activity": [], "details": details,
        "cash": [{"accountNumber": MAIN_CASH, "currencyId": "EUR", "amount": 610.81}],
        "portfolios": {CTO: {"categories": [{"categoryType": "stocksAndETFs", "positions": positions or []}]}},
    }


def sample():
    E, D = [], {}

    def add(e, d=None):
        E.append(e)
        D[e["id"]] = d or {"sections": []}

    add(ev("in", "BANK_TRANSACTION_INCOMING", "2026-01-02T09:00:00.000+0000", "DUPRE JEAN MARC", 1000.0, cash=MAIN_CASH),
        detail({"Expéditeur": "DUPRE JEAN MARC"}))
    add(ev("card", "CARD_TRANSACTION", "2026-01-03T22:30:00.000+0000", "Lidl", -26.21),
        detail({"Commerçant": "Lidl", "Total": "26,21 €"}))
    add(ev("card-x", "CARD_TRANSACTION", "2026-01-03T22:31:00.000+0000", "Lidl", -26.21, status="CANCELED"))
    add(ev("refund", "CARD_REFUND", "2026-01-04T10:00:00.000+0000", "BlaBlaCar", 40.0),
        detail({"Commerçant": "BlaBlaCar"}))
    add(ev("verif", "CARD_VERIFICATION", "2026-01-04T10:00:00.000+0000", "Shop", 0.0))
    add(ev("fail", "TRADING_SAVINGSPLAN_EXECUTION_FAILED", "2026-01-05T10:00:00.000+0000", "Nasdaq", -2000.0,
           status="CANCELED", cash=PEA_CASH))
    # Old detail layout, buy of a turbo whose icon is the underlying (Airbus).
    add(ev("turbo", "ORDER_EXECUTED", "2026-01-06T10:00:00.000+0000", "Long 151,6547 €", -204.0,
           icon="logos/NL0000235190/v2", subtitle="Ordre d'achat"),
        detail({"Portefeuille": "Compte-Titres Ordinaire", "Titres": "700", "Cours du titre": "0,29 €",
                "Frais": "1,00 €", "Total": "204,00 €"}, isin="DE000SW7DJS3", title="Transaction"))
    # Knock-out paid as a "cash corporate action", no quantity given.
    add(ev("ko", "SSP_CORPORATE_ACTION_CASH", "2026-01-20T10:00:00.000+0000", "Long 151,6547 €", 0.7,
           icon="logos/NL0000235190/v2", subtitle="Exercice de warrant", cash=MAIN_CASH),
        detail({"Événement": "Exercice de warrant", "Total": "0,70 €"}))
    # New layout, savings plan on the compte-titres.
    add(ev("plan", "TRADING_SAVINGSPLAN_EXECUTED", "2026-02-01T10:00:00.000+0000", "Energy Transition", -50.0,
           icon="logos/IE000KHX9DX6/v2", cash=MAIN_CASH),
        detail({"Transaction": "1,050751 ×  47,585 €", "Frais": "Gratuit", "Total": "50,00 €"},
               isin="IE000KHX9DX6"))
    # Cash sent to the PEA, then a PEA plan paid from the PEA cash account.
    add(ev("payin", "PEA_SAVINGS_PLAN_PAY_IN", "2026-02-09T10:00:00.000+0000", "Nasdaq", -150.0,
           icon="logos/FR0010342592/v2", cash=MAIN_CASH),
        detail({"Compte": "Plan Épargne en Actions"}, isin="FR0010342592"))
    add(ev("pea-buy", "TRADING_SAVINGSPLAN_EXECUTED", "2026-02-10T10:00:00.000+0000", "Nasdaq", -150.0,
           icon="logos/FR0010342592/v2", cash=PEA_CASH),
        detail({"Transaction": "2 ×  75,00 €", "Frais": "Gratuit"}, isin="FR0010342592"))
    add(ev("div", "CREDIT", "2026-03-01T10:00:00.000+0000", "Starbucks", 0.32, icon="logos/US8552441094/v2"),
        detail({"Événement": "Dividende", "Titres": "0,713765", "Impôt": "0,06 €", "Total": "+ 0,32 €"},
               title="Transaction"))
    add(ev("sb", "SAVEBACK_AGGREGATE", "2026-03-02T10:00:00.000+0000", "S&P 500", -6.38,
           icon="logos/FR0011550185/v2"),
        detail({"Accumulé": "+ 6,38 €", "Transaction": "0.190726 x  33,45 €", "Total": "+ 6,38 €"},
               isin="FR0011550185"))
    add(ev("split", "SSP_CORPORATE_ACTION_NO_CASH", "2026-03-10T10:00:00.000+0000", "Nasdaq", None,
           icon="logos/FR0010342592/v2"),
        detail({"Actif": "Nasdaq", "Actions ajoutées": "398.000000"}))
    add(ev("migr", "SSP_SECURITIES_TRANSFER_INCOMING", "2026-03-11T10:00:00.000+0000", "NVIDIA", None,
           icon="logos/US67066G1040/v2"),
        detail({"BIC": "TRBKDEBBXXX", "Actions": "13"}))
    add(ev("new", "SOME_FUTURE_EVENT", "2026-03-12T10:00:00.000+0000", "?", 1.0))
    positions = [{"isin": "IE000KHX9DX6", "averageBuyIn": "47.585", "netSize": "1.050751", "instrumentType": "fund",
                  "name": "Energy Transition", "derivativeInfo": None}]
    return dump(E, D, positions)


def test_numbers_in_both_web_formats():
    assert number("1 851,00 €") == 1851.0
    assert number("2.684,43 €") == 2684.43
    assert number("0.190726") == 0.190726
    assert number("+ 6,38 €") == 6.38
    assert number("Gratuit") == 0.0
    assert number("-0,02 €") == -0.02


def test_flows_and_accounts():
    p = parse(sample())
    by_id = {r.id: r for r in p.rows}
    assert by_id["in"].flow == "interne"                      # from Jean Marc himself, accents ignored
    assert by_id["card"].flow == "depense" and by_id["card"].amount_cents == -2621
    assert by_id["refund"].flow == "depense" and by_id["refund"].amount_cents == 4000
    assert {"card-x", "verif", "fail"}.isdisjoint(by_id)      # cancelled / no money
    assert by_id["turbo"].isin == "DE000SW7DJS3"              # the product, not the underlying
    assert by_id["turbo"].quantity == 700 and by_id["turbo"].fees_cents == 100
    ko = by_id["ko"]
    assert (ko.flow, ko.isin, ko.quantity) == ("vente_titre", "DE000SW7DJS3", 700)
    plan = by_id["plan"]
    assert (plan.holding_account_id, plan.quantity, plan.price) == ("tr_cto", 1.050751, 47.585)
    assert by_id["payin"].account_id == "tr_especes" and by_id["payin:pea"].amount_cents == 15000
    pea = by_id["pea-buy"]
    assert (pea.account_id, pea.holding_account_id, pea.quantity) == ("tr_pea", "tr_pea", 2)
    assert by_id["div"].flow == "dividende" and by_id["div"].tax_cents == 6
    sb = by_id["sb"]
    assert (sb.flow, sb.amount_cents, sb.quantity) == ("saveback", 638, 0.190726)
    assert by_id["split"].holding_account_id == "tr_pea"      # where the line is held
    assert "migr" not in by_id                                # TR Germany -> France, same shares
    assert p.unknown == {"SOME_FUTURE_EVENT": 1}


def test_cash_reconciles_with_reported_balance():
    p = parse(sample())
    total = sum(r.amount_cents for r in p.rows if r.account_id == "tr_especes" and r.flow not in NON_CASH_FLOWS)
    assert total == p.cash["tr_especes"] == 61081  # 1000 - 26.21 + 40 - 204 + 0.70 - 50 - 150 + 0.32


def test_import_is_idempotent_and_keeps_manual_category():
    con = db.connect(":memory:")
    db.init(con)
    p = parse(sample())
    first = sync.import_trade_republic(con, p, as_of="2026-03-12")
    assert first.new == len(p.rows) and first.unknown == {"SOME_FUTURE_EVENT": 1}
    con.execute("UPDATE transactions SET category_override = 'Sport et loisirs' WHERE id = 'card'")
    again = sync.import_trade_republic(con, p, as_of="2026-03-12")
    assert again.new == 0 and again.updated == len(p.rows)
    row = con.execute("SELECT category, category_override FROM transactions WHERE id = 'card'").fetchone()
    assert tuple(row) == ("Courses", "Sport et loisirs")
    assert con.execute("SELECT quantity FROM positions WHERE account_id = 'tr_cto'").fetchone()[0] == 1.050751
    assert con.execute("SELECT quantity FROM positions WHERE account_id = 'peg_airbus'").fetchone()[0] == 109.4
