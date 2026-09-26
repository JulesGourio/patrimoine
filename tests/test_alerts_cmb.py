from datetime import date

from patrimoine import alerts, db, sync
from patrimoine.sources import cmb_parse
from tests.test_portfolio import buy, con_with


def tx(day, amount, indicator, *label):
    return {"booking_date": day, "status": "BOOK", "credit_debit_indicator": indicator,
            "transaction_amount": {"currency": "EUR", "amount": str(amount)}, "remittance_information": list(label),
            "entry_reference": f"{day}T00:00:01-0"}


def test_cmb_labels_give_flows_and_counterparties():
    dump = {"accounts": [{"transactions": [
        tx("2026-09-23", 700, "DBIT", "VIR INST VIR JULES GOURIO TRADER  de GOURIO JULES  26266IP1RT500269162"),
        tx("2026-09-23", 750, "CRDT", "VIR de LIVRET CMB  de LIVRET CMB  2626609459620001"),
        tx("2026-08-28", 2453.08, "CRDT", "VIR MP DATA SUD-OUEST  000068-Paye 08 2026  2623949470160432"),
        tx("2026-09-09", 4.7, "DBIT", "F COTISATION OFFRE JEUNES 09/26"),
        tx("2025-12-28", 4.83, "DBIT", "CARTE 28/12 GAMSGO Hong Kong 4,83 EUR"),
        tx("2026-09-25", 77.5, "DBIT", "VIR vers LE POTTIER SEBASTIEN /  de GOURIO JULES  2626814443850001"),
        tx("2026-09-25", 77.5, "DBIT", "VIR vers LE POTTIER SEBASTIEN /  de GOURIO JULES  2626814443850001"),
    ], "balances": [{"balance_amount": {"amount": "191.41"}, "reference_date": "2026-09-25"}]}]}
    rows, _ = cmb_parse.parse(dump, owner={"GOURIO", "JULES"})
    flows = [(r.flow, r.counterparty, r.amount_cents) for r in rows]
    assert flows[:5] == [
        ("interne", "VIR JULES GOURIO TRADER", -70000),
        ("interne", "LIVRET CMB", 75000),
        ("revenu", "MP DATA SUD-OUEST", 245308),
        ("frais", "F COTISATION OFFRE JEUNES 09/26", -470),
        ("depense", "GAMSGO Hong Kong", -483),
    ]
    assert rows[5].flow == "depense" and rows[5].id != rows[6].id  # two identical transfers the same day
    mirror = cmb_parse.livret_mirror(rows)
    assert [(m.account_id, m.amount_cents) for m in mirror] == [("cmb_livret_a", -75000)]
    assert cmb_parse.balance(dump) == ("2026-09-25", 19141)

    con = db.connect(":memory:")
    db.init(con)
    db.set_meta(con, "owner", {"first": "Jules André", "last": "Gourio"})
    first = sync.import_cmb(con, dump)
    again = sync.import_cmb(con, dump)
    assert first.new == 8 and again.new == 0
    cat = con.execute("SELECT category FROM transactions WHERE counterparty = 'MP DATA SUD-OUEST'").fetchone()[0]
    assert cat == "Salaire"


def test_alerts_fire_once_per_key():
    con = con_with([buy("2026-09-01", "X", 10, 100_000)],
                   prices=[("X", "2026-09-21", 100.0), ("X", "2026-09-22", 100.0), ("X", "2026-09-23", 90.0)])
    con.execute("INSERT INTO alert_rules (kind, threshold, window_days) VALUES ('baisse_ligne', 8, 1)")
    con.execute("INSERT INTO alert_rules (kind, isin, threshold) VALUES ('seuil_haut', 'X', 150)")
    db.set_meta(con, "alerts_seeded", True)
    fired = alerts.run(con, send=False, today=date(2026, 9, 23))
    assert [f.title.split(" ")[1] for f in fired] == ["chute"]
    assert alerts.run(con, send=False, today=date(2026, 9, 23)) == []  # already sent today


def test_budget_alert():
    con = con_with([{"date": date.today().replace(day=1).isoformat(), "flow": "depense", "amount_cents": -30_000,
                     "isin": None, "holding_account_id": None, "category": "Courses"}])
    con.execute("INSERT INTO budgets VALUES ('Courses', 20000)")
    con.execute("INSERT INTO alert_rules (kind, threshold) VALUES ('budget', 100)")
    db.set_meta(con, "alerts_seeded", True)
    fired = alerts.run(con, send=False)
    assert len(fired) == 1 and "Courses" in fired[0].title
