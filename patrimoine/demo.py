"""Jeu de données fictif : remplit une base avec un foyer imaginaire, pour développer et photographier l'appli
sans aucune donnée personnelle. Déterministe (même graine, même base)."""
from __future__ import annotations

import json
import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path

from . import cartes, db, portfolio

# (isin, nom, symbole Yahoo, type, prix de départ, dérive annuelle, volatilité annuelle) — noms et cours inventés.
TITRES = [
    ("DE000DEMO001", "Aérostar Industries", "AERO.PA", "action", 95.0, 0.12, 0.28),
    ("FR000DEMO002", "Solvéo Énergie", "SLVO.PA", "action", 42.0, 0.06, 0.32),
    ("US000DEMO003", "Nimbus Compute", "NMBS", "action", 310.0, 0.25, 0.42),
    ("US000DEMO004", "Helix Santé", "HLXS", "action", 128.0, -0.04, 0.30),
    ("IE000DEMO005", "ETF Monde (démo)", "WRLD.PA", "etf", 78.0, 0.08, 0.15),
    ("IE000DEMO006", "ETF S&P 500 (démo)", "SPXD.PA", "etf", 480.0, 0.10, 0.17),
]
SALAIRE = 2_850_00
LOYER = 780_00
DEPENSES = [  # (vendeur, catégorie, montant moyen en centimes, fois par mois)
    ("Supermarché Verger", "Courses", 3_800, 7), ("Boulangerie Dupain", "Courses", 650, 6),
    ("Café du Port", "Restaurants et bars", 1_450, 4), ("Bistro Lumière", "Restaurants et bars", 3_600, 2),
    ("Pass Métro", "Transport", 8_600, 1), ("Station Énergie", "Transport", 5_400, 1),
    ("Cinéma Étoile", "Loisirs", 1_300, 2), ("Pharmacie Centrale", "Santé", 1_900, 1),
]
ABONNEMENTS = [("Musique+", "Abonnements", 1_299), ("Vidéo Flux", "Abonnements", 1_799), ("Forme Club", "Sport", 3_490)]


def _tx(con, n, day, account, flow, cents, label="", counterparty="", category=None, isin=None, qty=None, price=None,
        fees=0, holding=None):
    con.execute(
        "INSERT INTO transactions (id, account_id, holding_account_id, date, amount_cents, label, counterparty, flow,"
        " category, isin, quantity, price, fees_cents, raw_json, imported_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (f"demo{n}", account, holding, day.isoformat(), cents, label or counterparty, counterparty, flow, category,
         isin, qty, price, fees, json.dumps({"timestamp": f"{day.isoformat()}T12:00:00.000+0000"}), "demo"),
    )


def build(db_path: Path | str, seed: int = 7, today: date | None = None) -> dict:
    """Crée (ou complète) la base `db_path` avec le jeu fictif. Retourne un résumé."""
    rnd = random.Random(seed)
    today = today or date.today()
    start = today.replace(day=1) - timedelta(days=365 * 2)
    with db.session(db_path) as con:
        db.init(con)
        if con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]:
            raise SystemExit(f"{db_path} contient déjà des opérations : le jeu fictif ne s'écrit que dans une base vide.")
        n = 0

        def nxt() -> int:
            nonlocal n
            n += 1
            return n

        for isin, name, sym, kind, *_ in TITRES:
            con.execute("INSERT OR REPLACE INTO instruments VALUES (?,?,?,?,'EUR')", (isin, name, sym, kind))
        # cours quotidiens (marche aléatoire déterministe), jours ouvrés seulement
        prices: dict[str, dict[date, float]] = {}
        for isin, _, _, _, p0, mu, sigma in TITRES + [(db.AIRBUS[0], "", "", "", 120.0, 0.10, 0.25)]:
            p, series, d = p0, {}, start - timedelta(days=5)
            while d <= today:
                if d.weekday() < 5:
                    p *= 1 + mu / 252 + sigma / 252 ** 0.5 * rnd.gauss(0, 1)
                    series[d] = round(p, 2)
                d += timedelta(days=1)
            prices[isin] = series
            con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?, 'demo')", [(isin, k.isoformat(), v) for k, v in series.items()])

        def px(isin: str, d: date) -> float:
            while d not in prices[isin]:
                d -= timedelta(days=1)
            return prices[isin][d]

        # mois par mois : salaire, loyer, dépenses, virement d'épargne, achats
        month = start
        while month <= today:
            def at(day: int) -> date:
                return min(month.replace(day=day), today)

            _tx(con, nxt(), at(27), "cmb_courant", "revenu", SALAIRE, "Virement salaire", "Aérostar Industries", "Salaire")
            _tx(con, nxt(), at(3), "cmb_courant", "depense", -LOYER, "Loyer", "Agence Immo Centrale", "Logement")
            for vendor, cat, cents in ABONNEMENTS:
                _tx(con, nxt(), at(8), "cmb_courant", "depense", -cents, vendor, vendor, cat)
            for vendor, cat, avg, times in DEPENSES:
                for _ in range(times):
                    _tx(con, nxt(), at(rnd.randint(1, 28)), "cmb_courant", "depense",
                        -int(avg * rnd.uniform(0.6, 1.5)), vendor, vendor, cat)
            saved = 600_00
            _tx(con, nxt(), at(28), "cmb_courant", "interne", -saved, "Virement épargne", "")
            _tx(con, nxt(), at(28), "tr_especes", "interne", saved, "Virement épargne", "")
            if month.month in (3, 12):
                _tx(con, nxt(), at(15), "cmb_courant", "revenu", 1_400_00, "Prime d'intéressement", "Aérostar Industries",
                    "Primes et intéressement")
            # achats mensuels de titres
            for isin, acc in ((TITRES[4][0], "tr_pea"), (TITRES[rnd.randint(0, 3)][0], "tr_cto")):
                d = at(rnd.randint(5, 20))
                q = round(rnd.uniform(1.5, 4.0), 3)
                p = px(isin, d)
                _tx(con, nxt(), d, "tr_especes", "achat_titre", -int(q * p * 100) - 100, "Achat", "", None, isin, q, p, 100, acc)
            month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        # une vente avec plus-value, un dividende
        v = today - timedelta(days=120)
        _tx(con, nxt(), v, "tr_especes", "vente_titre", int(2 * px(TITRES[2][0], v) * 100), "Vente", "", None, TITRES[2][0], 2, px(TITRES[2][0], v), 100, "tr_cto")
        _tx(con, nxt(), today - timedelta(days=45), "tr_especes", "dividende", 34_20, "Dividende", "", None, TITRES[0][0])

        # livrets : soldes saisis à la main, comme dans l'appli
        db.set_balance(con, "cmb_livret_a", today.isoformat(), 6_200_00)
        db.set_balance(con, "cmb_livret_jeune", today.isoformat(), 1_600_00)

        # positions détenues dans les comptes-titres, d'après les opérations
        con.commit()
        df, _ = portfolio.valuations(con)
        portfolio.store(con, df)
        book, _p = portfolio.replay(con)
        for (acc, isin), line in book.lines.items():
            if line.quantity > 1e-9:
                con.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?,?,?,'demo')",
                            (acc, isin, round(line.quantity, 4), round(line.unit_cost, 4) if line.unit_cost else None, today.isoformat()))

        # carte prépayée (titres-restaurant)
        card = cartes.create(con, "Titres-restaurant", 0, start.isoformat())["id"]
        d = start
        while d <= today:
            if d.day == 1:
                cartes.add_operation(con, card, d.isoformat(), 180.0, "Versement employeur", "credit")
            if d.weekday() < 5 and rnd.random() < 0.9:
                cartes.add_operation(con, card, d.isoformat(), round(rnd.uniform(8, 10), 2), rnd.choice(["Boulangerie Dupain", "Café du Port", "Bistro Lumière"]), "paiement", True)
            d += timedelta(days=1)

        # budgets, une règle d'alerte et une idée d'ordre
        con.executemany("INSERT OR REPLACE INTO budgets VALUES (?,?)", [("Courses", 450_00), ("Restaurants et bars", 220_00), ("Loisirs", 100_00)])
        con.execute("INSERT INTO alert_rules (kind, isin, threshold, window_days, note) VALUES ('baisse_pct', NULL, 8, 1, 'Baisse de 8 % sur une ligne')")
        con.execute(
            "INSERT INTO order_ideas (created_at, account_id, isin, name, side, quantity, limit_price, rationale, risks)"
            " VALUES (?, 'tr_cto', ?, ?, 'achat', 3, ?, 'Renforcer la ligne après repli, valorisation redevenue raisonnable.', 'Secteur cyclique, concentration.')",
            (db.now_iso(), TITRES[1][0], TITRES[1][1], px(TITRES[1][0], today) * 0.97))
        db.set_meta(con, "demo", True)
        return {"operations": con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], "base": str(db_path)}
