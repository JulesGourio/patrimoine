"""The read and write operations on Jules's data, as plain functions returning JSON-safe dicts.

One list (`TOOLS`) serves the MCP server (`mcp_server`), the mobile app (`mobile`) and the cloud export
(`cloud`); none of them needs the others' libraries (no `mcp` or Streamlit import here).
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd

from . import alerts, db, portfolio, queries
from .categories import SPENDING
from .config import Settings

INSTRUCTIONS = (
    "Patrimoine de Jules : dépenses (CMB + carte Trade Republic), portefeuille Trade Republic (compte-titres, "
    "PEA), PEG Airbus, livrets. Montants en euros. Profil : recherche la performance, tolère le risque, horizon "
    "long ; rester honnête sur les risques, la concentration (Airbus : PEG + salaire passé) et la fiscalité. "
    "Toujours partir de ces données ; utiliser `marche` pour les cours et fondamentaux, la recherche web pour "
    "l'actualité. Jamais d'ordre passé : proposer avec `preparer_ordre`, Jules exécute. Analyse de marché "
    "(quotidienne ou hebdo) : `faits_du_jour` puis `publier_analyse` (format fixe, mail court avec graphique, "
    "page Analyses). Rapport libre à la demande : `enregistrer_rapport`."
)

TOOLS: list[Callable[..., dict]] = []


def tool(fn: Callable[..., dict]) -> Callable[..., dict]:
    """Mark a function as a tool: MCP server, mobile app and cloud export all go through `TOOLS`."""
    TOOLS.append(fn)
    return fn


def _con() -> sqlite3.Connection:
    con = db.connect(Settings().db_path)
    db.init(con)
    return con


def _clean(x: Any) -> Any:
    """JSON-safe: NaN -> None, Timestamps -> ISO dates, floats rounded."""
    if isinstance(x, dict):
        return {(k.date().isoformat() if isinstance(k, pd.Timestamp) else k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    if isinstance(x, float):
        return None if math.isnan(x) else round(x, 4 if abs(x) < 10 else 2)
    if hasattr(x, "item"):
        return _clean(x.item())
    return x


def _records(df: pd.DataFrame) -> list[dict]:
    return _clean(df.to_dict("records")) if not df.empty else []


@tool
def patrimoine() -> dict:
    """Patrimoine total (somme des avoirs, avant impôts) par compte aujourd'hui, variation sur 30 jours et 1 an, plus-values latentes et réalisées,
    dernière synchronisation."""
    con = _con()
    h = queries.history(con)
    if h.empty:
        return {"erreur": "historique vide : lancer synchroniser"}
    last_day = h.date.max()
    total = h.groupby("date")["value"].sum()
    now = h[h.date == last_day]
    inv = now[now.account_id.isin(["tr_cto", "tr_pea"])]
    return _clean({
        "date": last_day,
        "total": total.iloc[-1],
        "variation_30j": total.iloc[-1] - total.asof(last_day - pd.Timedelta(days=30)),
        "variation_1an": total.iloc[-1] - total.asof(last_day - pd.Timedelta(days=365)),
        "comptes": {r.account: r.value for r in now.itertuples()},
        "plus_values_latentes": (inv.securities - inv.cost).sum(),
        "cout_investi": inv.cost.sum(),
        "plus_values_realisees_cumul": now.realised.sum(),
        "derniere_synchro": db.get_meta(con, "last_sync"),
        "limites": "PEG reconstitué depuis les relevés Amundi (ESOP en équivalent actions, coût ESOP estimé) ; turbos au prix des ordres.",
    })


@tool
def positions() -> dict:
    """Lignes détenues : compte, quantité, PMP (frais inclus), cours, valeur, plus-value, poids, et performance
    du cours sur 1 jour, 1 semaine, 1 mois, 3 mois, depuis le 1er janvier et 1 an."""
    con = _con()
    pos = queries.positions(con)
    _, prices = portfolio.replay(con)
    today = pd.Timestamp.today().normalize()
    perf = []
    for isin in pos["isin"]:
        s = prices.series.get(isin)
        row: dict[str, Any] = {}
        if s is not None and len(s):
            last = s.iloc[-1]
            for label, d in (("1j", timedelta(days=1)), ("1s", timedelta(days=7)), ("1m", timedelta(days=30)),
                             ("3m", timedelta(days=91)), ("1an", timedelta(days=365))):
                past = s[s.index <= s.index[-1] - d]
                row[f"perf_{label}"] = (last / past.iloc[-1] - 1) if len(past) else None
            ytd = s[s.index < pd.Timestamp(today.year, 1, 1)]
            row["perf_ytd"] = (last / ytd.iloc[-1] - 1) if len(ytd) else None
        perf.append(row)
    pos = pd.concat([pos.reset_index(drop=True), pd.DataFrame(perf)], axis=1)
    symbols = dict(con.execute("SELECT isin, symbol FROM instruments"))
    pos["symbole_yahoo"] = pos["isin"].map(symbols)
    return {"positions": _records(pos), "note": "perf_* : variation du cours (pas de la ligne), en fraction."}


@tool
def historique(pas: str = "M") -> dict:
    """Valeur par compte dans le temps (pas : 'W' semaine, 'M' mois), avec coût investi et plus-values."""
    h = queries.history(_con())
    if h.empty:
        return {"historique": []}
    rule = {"M": "ME", "W": "W"}.get(pas.upper(), "ME")
    g = (h.set_index("date").groupby("account").resample(rule)[["value", "cost", "realised", "deposits"]].last()
         .reset_index())
    return {"historique": _records(g)}


@tool
def depenses(mois: int = 12) -> dict:
    """Dépenses des N derniers mois : total par mois, par catégorie et par mois, budgets contre dépensé ce mois-ci,
    commerçants principaux."""
    con = _con()
    sp = queries.spending(con)
    start = pd.Timestamp.today().to_period("M").to_timestamp() - pd.DateOffset(months=mois)
    sp = sp[sp.month >= start]
    this_month = pd.Timestamp.today().to_period("M").to_timestamp()
    budgets = dict(con.execute("SELECT category, monthly_limit_cents / 100.0 FROM budgets"))
    cur = sp[sp.month == this_month].groupby("category")["amount"].sum()
    return _clean({
        "par_mois": sp.groupby("month")["amount"].sum().to_dict(),
        "par_categorie": sp.groupby("category")["amount"].sum().sort_values(ascending=False).to_dict(),
        "par_mois_et_categorie": _records(sp.groupby(["month", "category"], as_index=False)["amount"].sum()),
        "mois_en_cours": {c: {"depense": float(cur.get(c, 0)), "budget": budgets.get(c)} for c in
                          set(cur.index) | set(budgets)},
        "top_commercants": _records(sp.groupby("merchant")["amount"].agg(["sum", "count"])
                                    .sort_values("sum", ascending=False).head(20).reset_index()),
    })


@tool
def flux(mois: int = 12) -> dict:
    """Par mois : revenus (salaire, aides, intérêts, dividendes), dépenses nettes des remboursements (amis qui
    rendent leur part, sécu), épargne (revenus - dépenses), taux d'épargne, héritages et donations (à part : ni
    revenu ni épargne), montants investis (achats nets de titres) et Saveback. Mêmes chiffres que la page Dépenses du tableau de bord."""
    from . import analytics

    con = _con()
    since = pd.Timestamp.today().to_period("M").to_timestamp() - pd.DateOffset(months=mois)
    out = analytics.monthly_balance(con)
    out = out[out.index >= since].rename(columns={"taux": "taux_epargne"})
    f = queries.flows_by_month(con).reindex(out.index, fill_value=0.0)
    col = lambda c: f[c] if c in f else 0.0  # noqa: E731
    out["investi_net"] = -(col("achat_titre") + col("vente_titre"))
    out["saveback"] = col("saveback")
    return {"flux": _records(out.reset_index())}


@tool
def fiscalite() -> dict:
    """Par année, compte-titres : plus-values, moins-values reportées, dividendes, intérêts, PFU estimé."""
    return {"annees": _clean(queries.taxes(_con()).to_dict("index")),
            "note": "Estimation PFU 30 %, à vérifier avec l'IFU. Le PEA n'est pas imposé tant qu'on n'y retire rien."}


@tool
def ventes_realisees() -> dict:
    """Toutes les ventes (et turbos désactivés) avec plus ou moins-value."""
    return {"ventes": _records(queries.realised(_con()))}


@tool
def operations(recherche: str = "", jours: int = 90, compte: str = "", flux_type: str = "") -> dict:
    """Recherche dans les opérations (libellé ou commerçant), sur N jours, filtrables par compte
    (tr_especes, tr_cto, tr_pea, cmb_courant…) et par flux (depense, revenu, interne, achat_titre…)."""
    con = _con()
    q = ("SELECT id, date, account_id, flow, COALESCE(category_override, category) AS categorie, counterparty, label,"
         " amount_cents / 100.0 AS montant, isin, quantity FROM transactions WHERE date >= ?")
    args: list[Any] = [(date.today() - timedelta(days=jours)).isoformat()]
    if recherche:
        q += " AND (UPPER(label) LIKE ? OR UPPER(counterparty) LIKE ?)"
        args += [f"%{recherche.upper()}%"] * 2
    if compte:
        q += " AND account_id = ?"
        args.append(compte)
    if flux_type:
        q += " AND flow = ?"
        args.append(flux_type)
    rows = [dict(r) for r in con.execute(q + " ORDER BY date DESC LIMIT 300", args)]
    return {"operations": rows, "tronque": len(rows) == 300}


@tool
def categoriser(transaction_id: str, categorie: str, tout_le_commercant: bool = False) -> dict:
    """Reclasse une dépense ; avec tout_le_commercant, apprend la règle pour toutes ses lignes."""
    if categorie not in SPENDING:
        return {"erreur": f"catégorie inconnue, choisir parmi {SPENDING}"}
    con = _con()
    row = con.execute("SELECT counterparty FROM transactions WHERE id = ?", (transaction_id,)).fetchone()
    if not row:
        return {"erreur": "opération inconnue"}
    queries.set_category(con, transaction_id, categorie, row["counterparty"] if tout_le_commercant else None)
    return {"ok": True}


@tool
def marche(titre: str, periode: str = "1y") -> dict:
    """Cours et fondamentaux d'un titre (ticker Yahoo comme 'AIR.PA', 'NVDA', ou un ISIN) : dernier cours,
    performances, volatilité annualisée, plus forte baisse, plus haut/bas 52 semaines, valorisation (PER, PER
    anticipé, capitalisation, dividende), secteur, recommandation des analystes, objectifs de cours, actualités."""
    import yfinance as yf

    from .prices import candidates

    symbol = titre
    if len(titre) == 12 and titre[:2].isalpha() and titre[2:].isalnum():
        con = _con()
        row = con.execute("SELECT symbol FROM instruments WHERE isin = ?", (titre,)).fetchone()
        symbol = (row["symbol"] if row and row["symbol"] else None) or next(iter(candidates(titre)), titre)
    t = yf.Ticker(symbol)
    h = t.history(period=periode, auto_adjust=True).dropna(subset=["Close"])
    if h.empty and len(titre) == 12:
        # The listing kept for the portfolio may have no recent quote on Yahoo: try the other listings.
        for alt in candidates(titre):
            t = yf.Ticker(alt)
            h = t.history(period=periode, auto_adjust=True).dropna(subset=["Close"])
            if not h.empty:
                symbol = alt
                break
    if h.empty:
        return {"erreur": f"pas de cours Yahoo pour {symbol}"}
    close = h["Close"]
    rets = close.pct_change().dropna()
    info: dict[str, Any] = {}
    try:
        info = t.info or {}
    except Exception:  # noqa: BLE001
        pass
    keys = ["longName", "currency", "sector", "industry", "country", "marketCap", "trailingPE", "forwardPE",
            "priceToBook", "dividendYield", "beta", "profitMargins", "revenueGrowth", "earningsGrowth",
            "recommendationKey", "numberOfAnalystOpinions", "targetMeanPrice", "targetLowPrice", "targetHighPrice",
            "fiftyTwoWeekHigh", "fiftyTwoWeekLow", "totalExpenseRatio", "category", "longBusinessSummary"]
    news = []
    try:
        for n in (t.news or [])[:8]:
            c = n.get("content", n)
            news.append({"titre": c.get("title"), "date": c.get("pubDate") or c.get("providerPublishTime"),
                         "source": (c.get("provider") or {}).get("displayName") if isinstance(c.get("provider"), dict)
                         else c.get("publisher")})
    except Exception:  # noqa: BLE001
        pass
    perf = {}
    for label, n in (("1m", 21), ("3m", 63), ("6m", 126), ("1an", 252)):
        if len(close) > n:
            perf[label] = close.iloc[-1] / close.iloc[-1 - n] - 1
    summary = info.get("longBusinessSummary")
    return _clean({
        "symbole": symbol, "dernier_cours": close.iloc[-1], "date": close.index[-1].date().isoformat(),
        "performances": perf, "volatilite_annuelle": rets.std() * math.sqrt(252),
        "plus_forte_baisse": (close / close.cummax() - 1).min(),
        "moyenne_mobile_50": close.tail(50).mean(), "moyenne_mobile_200": close.tail(200).mean(),
        **{k: info.get(k) for k in keys if k != "longBusinessSummary" and info.get(k) is not None},
        "activite": summary[:600] if summary else None,
        "actualites": news,
    })


@tool
def alertes() -> dict:
    """Règles d'alerte actives, budgets, et alertes déclenchées ces 30 derniers jours."""
    con = _con()
    alerts.seed(con)
    return {
        "regles": [dict(r) for r in con.execute("SELECT * FROM alert_rules")],
        "budgets": dict(con.execute("SELECT category, monthly_limit_cents / 100.0 FROM budgets")),
        "recentes": [dict(r) for r in con.execute(
            "SELECT triggered_at, message, sent_to FROM alert_events WHERE triggered_at >= ? ORDER BY triggered_at DESC",
            ((date.today() - timedelta(days=30)).isoformat(),))],
        "types": alerts.__doc__,
    }


@tool
def regle_alerte(type: str, seuil: float, isin: str = "", categorie: str = "", jours: int = 1,
                 note: str = "", desactiver_id: int = 0) -> dict:
    """Ajoute une règle (types : baisse_ligne, hausse_ligne, baisse_portefeuille, seuil_bas, seuil_haut,
    concentration, budget ; seuil en % ou en € pour les seuils de prix), ou désactive la règle desactiver_id."""
    con = _con()
    if desactiver_id:
        con.execute("UPDATE alert_rules SET active = 0 WHERE id = ?", (desactiver_id,))
    else:
        con.execute("INSERT INTO alert_rules (kind, isin, target, threshold, window_days, note) VALUES (?, ?, ?, ?, ?, ?)",
                    (type, isin or None, categorie or None, seuil, jours, note or None))
    con.commit()
    return {"ok": True}


@tool
def budget(categorie: str, montant_mensuel: float) -> dict:
    """Fixe le budget mensuel d'une catégorie de dépenses (0 pour le retirer)."""
    if categorie not in SPENDING:
        return {"erreur": f"catégorie inconnue, choisir parmi {SPENDING}"}
    con = _con()
    if montant_mensuel <= 0:
        con.execute("DELETE FROM budgets WHERE category = ?", (categorie,))
    else:
        con.execute("INSERT INTO budgets (category, monthly_limit_cents) VALUES (?, ?) ON CONFLICT(category)"
                    " DO UPDATE SET monthly_limit_cents = excluded.monthly_limit_cents",
                    (categorie, round(montant_mensuel * 100)))
    con.commit()
    return {"ok": True}


@tool
def preparer_ordre(sens: str, titre: str, justification: str, risques: str, compte: str = "tr_cto",
                   isin: str = "", quantite: float = 0, montant_eur: float = 0, limite: float = 0,
                   notifier: bool = True) -> dict:
    """Prépare un ordre (sens 'achat' ou 'vente') pour que Jules le passe lui-même dans l'appli Trade Republic.
    Compte : tr_cto ou tr_pea (vérifier l'éligibilité PEA). Donner la justification chiffrée et les risques."""
    if sens not in ("achat", "vente"):
        return {"erreur": "sens : achat ou vente"}
    con = _con()
    cur = con.execute(
        "INSERT INTO order_ideas (created_at, account_id, isin, name, side, quantity, amount_eur, limit_price,"
        " rationale, risks) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (db.now_iso(), compte, isin or None, titre, sens, quantite or None, montant_eur or None, limite or None,
         justification, risques))
    con.commit()
    if notifier:
        from . import notify

        taille = f"{quantite:g} titres" if quantite else f"{montant_eur:.0f} €"
        notify.send(f"Idée d'ordre : {sens} {titre}", f"{taille}" + (f", limite {limite:.2f} €" if limite else "")
                    + f" sur {compte}.\n{justification[:600]}", priority=3)
    return {"ok": True, "id": cur.lastrowid, "rappel": "Ordre non passé : Jules l'exécute dans Trade Republic."}


@tool
def ordres_proposes(statut: str = "proposé") -> dict:
    """Ordres préparés (statut : proposé, passé, abandonné, ou vide pour tous)."""
    con = _con()
    q = "SELECT * FROM order_ideas" + (" WHERE status = ?" if statut else "") + " ORDER BY created_at DESC"
    return {"ordres": [dict(r) for r in con.execute(q, (statut,) if statut else ())]}


@tool
def faits_du_jour(periode: str = "jour") -> dict:
    """Point de départ d'une analyse de marché. periode 'jour' (dernière séance) ou 'semaine' (5 séances).
    Calcule et enregistre un brouillon : lignes de Jules contre leur indice (move = variation, z = écart en
    écarts-types habituels, impact_eur), marchés, secteurs US, actions de ses ETF qui l'ont fait bouger
    (moteurs_etf), changements d'avis d'analystes, résultats à venir, argent suivi, radar, et `a_expliquer` :
    les mouvements inhabituels à expliquer en priorité. Renvoie l'id à passer à `publier_analyse`."""
    from . import briefing

    if periode not in briefing.PERIODS:
        return {"erreur": "periode : 'jour' ou 'semaine'"}
    con = _con()
    bid, f = briefing.draft(con, periode)
    f = {k: v for k, v in f.items() if k != "series"}
    return {"id": bid, "faits": f}


@tool
def publier_analyse(id: int, analyse: dict, notifier: bool = True) -> dict:
    """Publie l'analyse du brouillon `id` (de `faits_du_jour`) : page Analyses, mail court avec graphique et push.
    Format (voir scripts/analyse.md) : titre, ton, points_cles (3), lignes [{isin, cause, these, verdict,
    confiance, action?, sources}], marche {resume, themes [{titre, detail, sources}]}, idees [{ticker, nom, these,
    risque, sources}], conseils [{action, cible, ticker, cours_ref, montant_eur, prix_limite, horizon, pourquoi, risque,
    invalidation, confiance, sources}] (2 à 4), agenda [{date, evenement, enjeu}], bilan_semaine (hebdo), sources [{id, titre,
    media, url, date}]. Renvoie les erreurs à corriger s'il y en a (rien n'est publié dans ce cas)."""
    from . import briefing

    return briefing.publish(_con(), id, analyse, send=notifier)


@tool
def analyses(n: int = 5) -> dict:
    """Les N dernières analyses publiées (titre, points clés, verdicts par ligne) et le suivi des verdicts
    (cours depuis) : pour assurer la continuité et corriger ce qui s'est révélé faux."""
    from . import briefing

    con = _con()
    b = briefing.load(con).head(n)
    v = briefing.verdicts(con)
    return _clean({
        "analyses": [{"id": r.id, "type": r.kind, "seance": r.session, "titre": r.analysis.get("titre"),
                      "points_cles": r.analysis.get("points_cles"), "lignes": r.analysis.get("lignes"),
                      "idees": [i.get("nom") for i in r.analysis.get("idees", [])],
                      "conseils": r.analysis.get("conseils")} for r in b.itertuples()],
        "suivi_verdicts": _records(v.head(40)) if not v.empty else [],
    })


@tool
def enregistrer_rapport(titre: str, contenu_markdown: str, type: str = "demande", notifier: bool = True) -> dict:
    """Enregistre un rapport (type 'hebdo' ou 'demande') ; il s'affiche dans le dashboard et part sur le
    téléphone de Jules et par mail. Commencer le contenu par 3 à 5 lignes de synthèse."""
    con = _con()
    cur = con.execute("INSERT INTO reports (created_at, kind, title, body_md) VALUES (?, ?, ?, ?)",
                      (db.now_iso(), type, titre, contenu_markdown))
    con.commit()
    if notifier:
        from . import notify

        notify.send(titre, contenu_markdown, priority=3, tags=["memo"], markdown_body=True)
    return {"ok": True, "id": cur.lastrowid}


@tool
def rapports(n: int = 5) -> dict:
    """Les N derniers rapports enregistrés (pour ne pas se répéter d'une semaine à l'autre)."""
    return {"rapports": [dict(r) for r in _con().execute(
        "SELECT id, created_at, kind, title, body_md FROM reports ORDER BY created_at DESC LIMIT ?", (n,))]}


@tool
def synchroniser() -> dict:
    """Relance la synchronisation complète (Trade Republic, CMB, cours, historique, alertes). Peut demander à
    Jules de confirmer la connexion Trade Republic sur son téléphone."""
    from . import pipeline

    return {"resume": pipeline.run()}


# ---------- famous investors (13F) ----------

@tool
def investisseurs() -> dict:
    """Investisseurs suivis via leurs déclarations 13F (SEC) : dernier trimestre déclaré, encours, nombre de lignes,
    poids des 10 premières, 3 plus grosses lignes. Les 13F ont jusqu'à 45 jours de retard et ne montrent que les
    positions longues cotées aux États-Unis (ni ventes à découvert, ni liquidités, ni actions hors US)."""
    from . import investors
    from .sources import sec13f

    con = _con()
    sec13f.init(con)
    return {"investisseurs": _records(investors.overview(con))}


@tool
def investisseur(nom: str, lignes: int = 30) -> dict:
    """Portefeuille d'un investisseur suivi (nom ou gérant, ex. 'Buffett', 'Coatue') au dernier trimestre, avec les
    changements depuis le trimestre précédent : nouvelle, renforcée, allégée, vendue (et variation du nombre d'actions)."""
    from . import investors

    con = _con()
    row = con.execute("SELECT cik FROM investors WHERE name LIKE ? OR manager LIKE ?",
                      (f"%{nom}%", f"%{nom}%")).fetchone()
    if not row:
        return {"erreur": "investisseur non suivi ; voir `investisseurs` ou `suivre_investisseur`"}
    m, meta = investors.portfolio(con, row["cik"])
    cols = ["issuer", "ticker", "put_call", "weight", "value_usd", "shares", "change", "shares_change", "weight_prev"]
    moves = m[m.change != "="]
    return {"meta": _clean(meta), "positions": _records(m[m.change != "vendue"][cols].head(lignes)),
            "mouvements": _records(moves[cols].sort_values("value_usd", ascending=False).head(lignes))}


@tool
def consensus_investisseurs(min_detenteurs: int = 3) -> dict:
    """Actions détenues par plusieurs investisseurs suivis au dernier trimestre, avec combien les ont achetées ou
    renforcées et combien les ont allégées ou vendues. Utile pour repérer les convictions partagées."""
    from . import investors

    return {"consensus": _records(investors.consensus(_con(), min_detenteurs).head(40))}


@tool
def recoupement_investisseurs() -> dict:
    """Parmi les sociétés que Jules détient (en direct), lesquelles sont aussi chez les investisseurs suivis."""
    from . import investors

    con = _con()
    pos = queries.positions(con)
    symbols = dict(con.execute("SELECT isin, symbol FROM instruments WHERE symbol IS NOT NULL"))
    tickers = [symbols[i].split(".")[0] for i in pos["isin"] if i in symbols]
    return {"recoupement": _records(investors.overlap(con, list(pos["name"]), tickers)),
            "note": "Tes lignes sont surtout des ETF européens : le recoupement porte sur les sociétés détenues en direct."}


@tool
def suivre_investisseur(cik: int, nom: str, gerant: str = "", style: str = "", actif: bool = True) -> dict:
    """Ajoute (ou désactive, actif=False) un investisseur à suivre par son CIK SEC ; ses 13F sont téléchargés."""
    from .sources import sec13f

    con = _con()
    sec13f.init(con)
    con.execute("INSERT INTO investors (cik, name, manager, style, active) VALUES (?, ?, ?, ?, ?) ON CONFLICT(cik)"
                " DO UPDATE SET name = excluded.name, manager = excluded.manager, style = excluded.style,"
                " active = excluded.active", (cik, nom, gerant or None, style or None, int(actif)))
    con.commit()
    new = sec13f.sync(con) if actif else []
    return {"ok": True, "nouvelles_declarations": len(new)}


TRADE_FIELDS = ["filed", "tx_date", "name", "chamber_label", "action", "ticker", "asset", "asset_type", "owner",
                "amount_min", "amount_max", "ret", "bench_ret", "comment"]


@tool
def elus(mois: int = 24, suivis_seulement: bool = False) -> dict:
    """Élus du Congrès américain (Chambre et Sénat, déclarations STOCK Act) classés par l'écart de leurs achats
    d'actions au S&P 500 sur les `mois` derniers : perf moyenne pondérée depuis chaque achat (ret), écart à
    l'indice (excess), part d'achats gagnants, part d'options, principaux achats, suivi ou non. Déclarations
    jusqu'à 45 jours en retard, montants en fourchettes : une estimation, pas le rendement de leur compte."""
    from . import politicians

    r = politicians.ranking(_con(), mois)
    if suivis_seulement and not r.empty:
        r = r[r.followed]
    return {"classement": _records(r.head(40))}


@tool
def elu(nom: str, operations: int = 40) -> dict:
    """Opérations déclarées d'un élu américain (nom partiel, ex. 'Pelosi', 'Tuberville'), les plus récentes
    d'abord, avec la variation du cours depuis et celle du S&P 500 sur la même période."""
    from . import politicians

    con = _con()
    found = politicians.find(con, nom)
    if not found:
        return {"erreur": "élu introuvable ; voir `elus`"}
    out = []
    for p in found[:3]:
        t = politicians.trades(con, p["id"])
        out.append({**p, "operations": _records(t[TRADE_FIELDS].head(operations)) if not t.empty else []})
    return {"elus": out}


@tool
def achats_elus(jours: int = 30, suivis_seulement: bool = False) -> dict:
    """Opérations des élus américains déclarées ces `jours` derniers, et les titres traités par plusieurs élus sur
    90 jours (acheteurs, vendeurs, montants estimés)."""
    from . import politicians

    con = _con()
    rec = politicians.recent(con, jours, suivis_seulement)
    return {"operations": _records(rec[TRADE_FIELDS].head(150)) if not rec.empty else [],
            "convergences_90j": _records(politicians.consensus(con, 90).head(25))}


@tool
def suivre_elu(nom: str, suivre: bool = True) -> dict:
    """Suit (ou ne suit plus) un élu américain : ses nouvelles opérations arrivent dans le récapitulatif quotidien
    des investisseurs (un seul message par jour, push et mail)."""
    from . import politicians
    from .sources import congress

    con = _con()
    found = politicians.find(con, nom)
    if len(found) != 1:
        return {"erreur": "préciser le nom", "candidats": found[:10]}
    congress.follow(con, found[0]["id"], suivre)
    return {"ok": True, "elu": found[0]["name"], "suivi": suivre}



@tool
def radar(n: int = 25) -> dict:
    """Radar « quoi regarder » : actions que l'argent suivi achète (déclarations rapides des fonds et achats des
    dirigeants, élus sélectionnés et autres sur 90 jours, fonds 13F au dernier trimestre, les fonds qui battent le
    marché comptant double ; date du dernier signal et cours depuis), avec tendance des cours (1/3/12
    mois, écart au plus haut), avis et objectif des analystes, exposition de Jules via ses ETF (mine_eur) et la
    raison en clair (why) ; plus les titres qu'ils vendent. Idées à creuser, pas des signaux d'achat."""
    from . import radar as rd

    con = _con()
    r = rd.load(con)
    keep = [c for c in ["ticker", "name", "sector", "score", "why", "signal_date", "since_signal", "r1m", "r3m",
                        "r1y", "from_high", "rating", "upside", "mine_eur", "mine_via"] if c in r]
    return {"calcule_le": db.get_meta(con, "radar_at"), "idees": _records(r[keep].head(n)) if not r.empty else [],
            "ventes": _records(rd.selling(con).head(15))}


@tool
def nouveautes(jours: int = 14, mes_titres: bool = False) -> dict:
    """Fil de ce que l'argent suivi a publié récemment, du plus récent au plus ancien : Form 4 et 13D/13G des fonds
    suivis (quelques jours de retard seulement), opérations quotidiennes d'ARK, achats des dirigeants (au moins
    100 k$, hors plans salariés), nouveaux 13F, opérations des élus suivis ou importantes. `since` : variation du
    cours depuis l'opération ; `mine` : Jules détient le titre (en direct ou via ses ETF). Plus la fraîcheur de
    chaque source."""
    from . import fresh

    con = _con()
    f = fresh.feed(con, jours)
    if mes_titres and not f.empty:
        f = f[f.mine]
    return {"sources": _records(fresh.sources_status(con)),
            "fil": _records(f.drop(columns=["link"]).head(80)) if not f.empty else []}


@tool
def positions_actuelles(nom: str) -> dict:
    """Portefeuille estimé aujourd'hui d'un investisseur suivi : son dernier 13F mis à jour par les Form 4 et
    13D/13G publiés depuis (et, pour ARK, ses ETF du jour). Pour chaque ligne : actions au 13F et connues
    aujourd'hui, source et date de l'info, poids estimé, variation du cours depuis le 13F ; plus ses déclarations
    rapides."""
    from . import fresh

    con = _con()
    row = con.execute("SELECT cik FROM investors WHERE name LIKE ? OR manager LIKE ?",
                      (f"%{nom}%", f"%{nom}%")).fetchone()
    if not row:
        return {"erreur": "investisseur non suivi ; voir `investisseurs`"}
    p, meta = fresh.current_positions(con, row["cik"])
    m = fresh.fund_moves(con, 365)
    m = m[m.cik == row["cik"]] if not m.empty else m
    cols = ["ticker", "issuer", "shares_13f", "shares_now", "source", "as_of", "weight_13f", "weight_now", "since_13f"]
    return {"meta": _clean(meta), "positions": _records(p[cols].head(40)) if not p.empty else [],
            "declarations_rapides": _records(m.drop(columns=["url"]).head(30)) if not m.empty else []}


@tool
def dirigeants(ticker: str = "", jours: int = 90) -> dict:
    """Achats et ventes sur le marché des dirigeants et administrateurs (Form 4, 2 jours de retard) : pour un titre,
    le détail par jour ; sans titre, les titres surveillés où plusieurs dirigeants achètent. Les ventes sont souvent
    programmées ou fiscales ; les achats sont le vrai signal."""
    from . import fresh

    con = _con()
    if ticker:
        t = fresh.insider_trades(con, jours, ticker.upper())
        return {"operations": _records(fresh.insider_days(t)) if not t.empty else []}
    s = fresh.insider_signals(con, jours)
    if s.empty:
        return {"achats": []}
    s = s[s.in_buyers > 0].sort_values(["in_buyers", "in_bought"], ascending=False)
    return {"achats": _records(s.reset_index(names="ticker").head(30))}


@tool
def performance_fonds() -> dict:
    """Pour chaque fonds 13F suivi : rendement si on avait copié ses 20-25 premières lignes à chaque publication,
    comparé au S&P 500 sur la même période (ret, bench, excess, annual, last_quarter)."""
    from . import investors

    return {"fonds": _records(investors.performance(_con()))}

