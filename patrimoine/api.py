"""The read and write operations on Jules's data, as plain functions returning JSON-safe dicts.

One list (`TOOLS`) serves the MCP server (`mcp_server`), the mobile app (`mobile`) and the cloud export
(`cloud`); none of them needs the others' libraries (no `mcp` import here).
"""
from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from typing import Any, Callable

import pandas as pd

from . import alerts, db, portfolio, queries
from .categories import CATEGORIES, SPENDING
from .config import Settings

INSTRUCTIONS = (
    "Patrimoine de l'utilisateur : dépenses, portefeuille, comptes d'épargne, patrimoine total. Montants en "
    "euros. Le profil d'investisseur (tolérance au risque, horizon) est dans CLAUDE.local.md s'il existe ; "
    "sinon le demander avant de conseiller. Rester honnête sur les risques, la concentration et la fiscalité. "
    "Toujours partir de ces données ; utiliser `marche` pour les cours et fondamentaux, la recherche web pour "
    "l'actualité. Jamais d'ordre passé : proposer avec `preparer_ordre`, l'utilisateur exécute. Analyse de marché "
    "(quotidienne ou hebdo) : `faits_du_jour` puis `publier_analyse` (format fixe, mail court avec graphique, "
    "écran Analyses). Rapport libre à la demande : `enregistrer_rapport`."
)

RISKY_ACCOUNTS = {"PEA", "Compte-titres", "PEG Airbus"}  # libellés de queries.ACCOUNT_LABELS

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
    replayed = portfolio.replay(con)
    pos = queries.positions(con, replayed)
    if pos.empty:
        return {"positions": [], "note": "Aucune ligne détenue."}
    prices = replayed[1]
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
        "par_mois_et_categorie": _records(sp.fillna({"category": "Non catégorisé"}).groupby(["month", "category"], as_index=False)["amount"].sum()),
        "mois_en_cours": {c: {"depense": float(cur.get(c, 0)), "budget": budgets.get(c)} for c in
                          set(cur.index) | set(budgets)},
        "top_commercants": _records(sp.groupby("merchant")["amount"].agg(["sum", "count"])
                                    .sort_values("sum", ascending=False).head(20).reset_index()),
    })


@tool
def flux(mois: int = 12) -> dict:
    """Par mois : revenus (salaire, aides, intérêts, dividendes), dépenses nettes des remboursements (amis qui
    rendent leur part, sécu), épargne (revenus - dépenses), taux d'épargne, héritages et donations (à part : ni
    revenu ni épargne), montants investis (achats nets de titres) et Saveback. Mêmes chiffres que l'écran Dépenses de l'appli."""
    from . import analytics

    con = _con()
    ref = queries.data_date(con)
    since = ref.to_period("M").to_timestamp() - pd.DateOffset(months=mois)
    out = analytics.monthly_balance(con)
    out = out[out.index >= since].rename(columns={"taux": "taux_epargne"})
    f = queries.flows_by_month(con).reindex(out.index, fill_value=0.0)
    col = lambda c: f[c] if c in f else 0.0  # noqa: E731
    out["investi_net"] = -(col("achat_titre") + col("vente_titre"))
    out["saveback"] = col("saveback")
    # The month of the data date is incomplete unless the data reaches its last day: no savings rate for it.
    out["partiel"] = (out.index + pd.offsets.MonthEnd(0)) > ref
    out.loc[out["partiel"], "taux_epargne"] = float("nan")
    return _clean({"donnees_au": ref.date().isoformat(), "flux": _records(out.reset_index())})


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
def operations(recherche: str = "", jours: int = 90, compte: str = "", flux_type: str = "",
               categorie: str = "", mois: str = "") -> dict:
    """Recherche dans les opérations (libellé ou commerçant), sur N jours, filtrables par compte
    (tr_especes, tr_cto, tr_pea, cmb_courant…), par flux (depense, revenu, interne, achat_titre…), par catégorie
    et par mois (« 2026-10 », remplace alors la période en jours)."""
    con = _con()
    q = ("SELECT id, date, account_id, flow, COALESCE(category_override, category) AS categorie, counterparty, label,"
         " amount_cents / 100.0 AS montant, isin, quantity FROM transactions WHERE date >= ?")
    args: list[Any] = [(date.today() - timedelta(days=jours)).isoformat()]
    if mois:
        q = q.replace("date >= ?", "substr(date, 1, 7) = ?")
        args = [mois[:7]]
    if categorie == "Non catégorisé":
        q += " AND COALESCE(category_override, category) IS NULL"
    elif categorie:
        q += " AND COALESCE(category_override, category) = ?"
        args.append(categorie)
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
    """Reclasse une dépense ou un revenu (catégories de dépenses ou de revenus, ex. « Remboursements ») ; avec
    tout_le_commercant, apprend la règle pour toutes ses lignes."""
    if categorie not in CATEGORIES:
        return {"erreur": f"catégorie inconnue, choisir parmi {CATEGORIES}"}
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
def statut_ordre(id: int, statut: str) -> dict:
    """Note ce que Jules a fait d'un ordre préparé : 'passé' (il l'a exécuté dans Trade Republic), 'abandonné', ou
    'proposé' pour annuler. Ne passe aucun ordre."""
    if statut not in ("proposé", "passé", "abandonné"):
        return {"erreur": "statut : proposé, passé ou abandonné"}
    con = _con()
    done = con.execute("UPDATE order_ideas SET status = ? WHERE id = ?", (statut, id)).rowcount
    con.commit()
    return {"ok": True, "id": id, "statut": statut} if done else {"erreur": f"ordre {id} introuvable"}


@tool
def faits_du_jour(periode: str = "jour") -> dict:
    """Point de départ d'une analyse de marché. periode 'jour' (dernière séance) ou 'semaine' (5 séances).
    Calcule et enregistre un brouillon : lignes de Jules contre leur indice (move = variation, z = écart en
    écarts-types habituels, impact_eur), marchés, secteurs US, actions de ses ETF qui l'ont fait bouger
    (moteurs_etf), changements d'avis d'analystes, résultats à venir, et `a_expliquer` :
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
    """Publie l'analyse du brouillon `id` (de `faits_du_jour`) : écran Analyses, mail court avec graphique et push.
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


GROUPES = queries.ACCOUNT_GROUPS


@tool
def synthese(avec_peg: bool = True) -> dict:
    """Les chiffres de l'accueil de l'appli : patrimoine total (30 j, 1 an, depuis le 1er janvier), après
    impôts si tout était vendu, épargne moyenne, part investie, gains d'investissement bruts et nets d'impôt estimé
    (PFU 30 % sur le compte-titres, les dividendes hors PEA et les intérêts ; prélèvements sociaux 17,2 % sur le PEA
    et le PEG), et la valeur par compte avec sa variation sur 30 jours. Mêmes règles que la page Patrimoine du PC."""
    from . import analytics

    con = _con()
    h = queries.history(con)
    if h.empty:
        return {"erreur": "historique vide : lancer synchroniser"}
    if not avec_peg:
        h = h[h.account_id != "peg_airbus"]
    total = h.groupby("date")["value"].sum()
    today = total.index.max()
    at = lambda d: float(total.asof(d)) if d >= total.index.min() else None  # noqa: E731
    now = float(total.iloc[-1])
    jan1 = at(pd.Timestamp(today.year - 1, 12, 31))
    year_ago = at(today - pd.DateOffset(years=1))
    month_ago = at(today - pd.Timedelta(days=30))
    bal = analytics.monthly_balance(con)
    full = queries.complete_months(bal, queries.data_date(con)).tail(12)
    last = h[h.date == today]
    by_group = last.assign(g=last.account.map(GROUPES)).groupby("g")["value"].sum()
    replayed = portfolio.replay(con)
    pos = queries.positions(con, replayed)
    real = queries.realised(con, replayed)
    income = queries.investment_income(con)
    ps, pfu = 0.172, 0.30
    wrapper = (pos.groupby("account").gain.sum() if not pos.empty else pd.Series(dtype=float)).add(
        real.groupby("account").gain.sum() if not real.empty else pd.Series(dtype=float), fill_value=0.0)
    gain_cto, gain_pea, gain_peg = (float(wrapper.get(a, 0.0)) for a in ("Compte-titres", "PEA", "PEG Airbus"))
    div_pea = float(income[(income.flow == "dividende") & (income.account == "PEA")].amount.sum()) if len(income) else 0.0
    div_other = float(income[(income.flow == "dividende") & (income.account != "PEA")].amount.sum()) if len(income) else 0.0
    interest = float(income[income.flow == "interets"].amount.sum()) if len(income) else 0.0
    if not avec_peg:
        gain_peg = 0.0
    gain = gain_cto + gain_pea + gain_peg + div_pea + div_other + interest
    net = (gain_cto + div_other + interest) * (1 - pfu) + (gain_pea + div_pea + gain_peg) * (1 - ps)
    pea_open = queries.account_open_dates(con).get("tr_pea")
    pea_5y = bool(pea_open and (today - pd.Timestamp(pea_open)).days >= 365.25 * 5)
    invested = float(by_group.get("Bourse", 0) + by_group.get("Épargne salariale", 0))
    comptes = [{"compte": r.account, "groupe": GROUPES.get(r.account), "valeur": float(r.value),
                "var_30j": float(r.value) - float(h[(h.account == r.account)].set_index("date")["value"]
                                                    .asof(today - pd.Timedelta(days=30)) or 0.0)}
               for r in last.itertuples()]
    return _clean({
        "date": today, "total": now, "variation_30j": now - month_ago if month_ago is not None else None,
        "depuis_1er_janvier": now - jan1 if jan1 else None, "depuis_1er_janvier_pct": now / jan1 - 1 if jan1 else None,
        "sur_1_an": now - year_ago if year_ago else None,
        "apres_impots": now - (gain - net), "impots_latents": gain - net,
        "epargne_moyenne": float(full.epargne.mean()) if len(full) else None,
        "epargne_pct_revenus": float(full.epargne.sum() / full.revenus.sum()) if full.revenus.sum() else None,
        "part_investie": invested / now if now else None, "investi": invested,
        "gains_bruts": gain, "gains_nets": net, "interets_et_dividendes": interest + div_pea + div_other,
        "pea_ouverture": pea_open, "pea_5_ans": pea_5y,
        "comptes": sorted(comptes, key=lambda c: -c["valeur"]),
    })


@tool
def depenses_operations(mois: int = 13) -> dict:
    """Toutes les dépenses des N derniers mois plus le mois en cours (même fenêtre que `depenses` et `flux`) : id,
    date, commerçant, `contrepartie` brute (null si vide), catégorie (remplacement manuel prioritaire), indicateur
    « modifiée » et montant en euros. Seuls les avoirs carte figurent en négatif ; les remboursements d'amis et de
    la sécu (flux `revenu`, catégorie `Remboursements`) ne sont pas dans ces lignes."""
    con = _con()
    sp = queries.spending(con)
    start = pd.Timestamp.today().to_period("M").to_timestamp() - pd.DateOffset(months=mois)
    sp = sp[sp.month >= start].sort_values(["date", "id"], ascending=[False, True])
    rows = [{"id": r.id, "date": r.date.date().isoformat(), "commercant": r.merchant,
             "contrepartie": r.counterparty if isinstance(r.counterparty, str) and r.counterparty.strip() else None,
             "categorie": r.category if isinstance(r.category, str) else "Non catégorisé",
             "modifiee": isinstance(r.category_override, str), "montant": float(r.amount)}
            for r in sp.itertuples()]
    return {"operations": rows}


@tool
def cours(isin: str, jours: int = 400) -> dict:
    """Série de cours d'une ligne (ISIN, ou ticker Yahoo d'un titre connu) en euros, sur l'échelle des quantités
    détenues, le PMP de la ligne (tous comptes, frais inclus) et ses opérations (achats, ventes, saveback)."""
    con = _con()
    if not (len(isin) == 12 and isin[:2].isalpha() and isin[2:].isalnum()):
        row = con.execute("SELECT isin FROM instruments WHERE symbol = ?", (isin,)).fetchone()
        isin = row["isin"] if row else isin
    txs = portfolio.rows(con)
    book, prices = portfolio.replay(con)
    s = prices.series.get(isin)
    points: list[list] = []
    today_factor = prices.factors[isin][-1][1] if s is not None and len(s) else 1.0
    later_splits = sorted((d, r) for (i, d), r in prices.split_ratio.items() if i == isin)
    if s is not None and len(s):
        for d in s.index[s.index >= s.index[-1] - pd.Timedelta(days=jours)]:
            # Today's scale: Yahoo back-adjusts splits, `Prices.get` would rescale to the shares held back then.
            points.append([d.date().isoformat(), round(float(s.asof(d)) * today_factor, 4)])
    qty = sum(ln.quantity for (_, i), ln in book.lines.items() if i == isin and ln.quantity > 1e-6)
    cost = sum(ln.cost for (_, i), ln in book.lines.items() if i == isin and ln.quantity > 1e-6)
    ops = []
    for r in txs:
        if r["isin"] != isin or not r["quantity"] or r["flow"] not in (
                "achat_titre", "saveback", "vente_titre", "titres_offerts", "transfert_titres"):
            continue
        fees = (r["fees_cents"] or 0) / 100
        value = abs(r["amount_cents"]) / 100
        sale = r["flow"] == "vente_titre"
        if value == 0 and r["flow"] in ("titres_offerts", "transfert_titres"):
            continue
        # Quantities and prices of the operations are put on today's scale (divide by later splits).
        ratio = math.prod(x for d, x in later_splits if d > pd.Timestamp(r["date"])) or 1.0
        ops.append({"date": r["date"], "sens": "vente" if sale else "achat", "quantite": r["quantity"] * ratio,
                    "prix": (value + fees if sale else value - fees) / r["quantity"] / ratio})
    return _clean({"isin": isin, "cours": points, "pmp": cost / qty if qty > 1e-6 and cost else None,
                   "operations": ops})


@tool
def projection(horizon_ans: int = 20, epargne_mensuelle: float | None = None, hausse_epargne_pct: float = 2.0,
               objectif_eur: float = 500000, part_actions_pct: float | None = None, rendement_actions_pct: float = 7.0,
               volatilite_pct: float = 18.0, rendement_livrets_pct: float = 2.4, inflation_pct: float = 2.0) -> dict:
    """Projection Monte-Carlo du patrimoine (2000 scénarios, graine fixe) : médiane et scénarios prudent/favorable
    (1 sur 10) à l'horizon, en euros courants et d'aujourd'hui, versé de la poche, chance d'atteindre l'objectif,
    trajectoires et leviers (effet sur la médiane de ±200 €/mois, ±10 points d'actions, ±1 point de rendement).
    Par défaut : épargne = moyenne des 12 derniers mois complets (arrondie à 50 €, sinon 1000), part d'actions =
    part actuelle de PEA, compte-titres et PEG. Avant impôts ; une simulation, pas une promesse."""
    import numpy as np

    from . import analytics
    from .projection import project

    con = _con()
    try:
        valeurs = {"horizon_ans": float(horizon_ans), "hausse_epargne_pct": float(hausse_epargne_pct),
                   "objectif_eur": float(objectif_eur), "rendement_actions_pct": float(rendement_actions_pct),
                   "volatilite_pct": float(volatilite_pct), "rendement_livrets_pct": float(rendement_livrets_pct),
                   "inflation_pct": float(inflation_pct)}
        if epargne_mensuelle is not None:
            valeurs["epargne_mensuelle"] = float(epargne_mensuelle)
        if part_actions_pct is not None:
            valeurs["part_actions_pct"] = float(part_actions_pct)
    except (TypeError, ValueError):
        return {"erreur": "les paramètres de la projection doivent être des nombres"}
    if not all(math.isfinite(v) for v in valeurs.values()):
        return {"erreur": "les paramètres de la projection doivent être des nombres finis"}
    v = valeurs
    if not 1 <= v["horizon_ans"] <= 40 or v["horizon_ans"] != int(v["horizon_ans"]):
        return {"erreur": "horizon_ans doit être un entier entre 1 et 40"}
    if not 0 <= v.get("part_actions_pct", 0) <= 100:
        return {"erreur": "part_actions_pct doit être entre 0 et 100"}
    if not 0 < v["volatilite_pct"] <= 100:
        return {"erreur": "volatilite_pct doit être entre 0 (exclu) et 100"}
    for k in ("rendement_actions_pct", "rendement_livrets_pct", "inflation_pct"):
        if v[k] <= -100:
            return {"erreur": f"{k} doit être supérieur à -100"}
    if v.get("epargne_mensuelle", 0) < 0 or v["objectif_eur"] < 0:
        return {"erreur": "epargne_mensuelle et objectif_eur doivent être positifs ou nuls"}
    horizon_ans = int(v["horizon_ans"])
    h = queries.history(con)
    if h.empty:
        return {"erreur": "historique vide : lancer synchroniser"}
    last = h[h.date == h.date.max()]
    risky = float(last[last.account.isin(RISKY_ACCOUNTS)].value.sum())
    safe = float(last[~last.account.isin(RISKY_ACCOUNTS)].value.sum())
    total = risky + safe
    if epargne_mensuelle is None:
        epargne_mensuelle = 1000.0
        try:
            bal = analytics.monthly_balance(con)
            saving = queries.complete_months(bal, queries.data_date(con)).tail(12).epargne.mean()
            if saving > 0:
                epargne_mensuelle = float(round(saving / 50) * 50)
        except Exception:  # noqa: BLE001 - pas encore d'opérations : on garde 1000
            pass
    if part_actions_pct is None:
        part_actions_pct = round(100 * risky / total) if total > 0 else 0
    try:
        with np.errstate(all="ignore"):
            res = project(risky, safe, horizon_ans=horizon_ans, monthly=epargne_mensuelle,
                          growth_pct=hausse_epargne_pct, goal=objectif_eur, share_pct=part_actions_pct,
                          mu_pct=rendement_actions_pct, vol_pct=volatilite_pct, safe_pct=rendement_livrets_pct,
                          inflation_pct=inflation_pct)
    except (OverflowError, ValueError, FloatingPointError):  # paramètres si extrêmes que le calcul déborde
        return {"erreur": "paramètres trop extrêmes pour la projection"}
    return _clean({**res, "donnees_au": queries.data_date(con).date().isoformat()})


# ---------- outils restaurés de l'ancien tableau de bord (frais, fiscalité de fin d'année, performance, risques) ----------

@tool
def frais() -> dict:
    """Frais payés par année (banque, courtage, frais des fonds estimés sur leur valeur moyenne de l'année) et frais
    des fonds au rythme actuel : TER × valeur de chaque ligne détenue (prélevés dans le cours, invisibles sur les
    relevés). Montants en euros ; TER en %. Les lignes sans TER connu (table queries.TER) sont absentes des frais de
    fonds : elles figurent dans `isin_sans_ter` (frais sous-estimés). `ordres_payants` : ordres avec frais ;
    `executions_plans` : exécutions gratuites (plans d'épargne, versements PEG)."""
    con = _con()
    f = queries.fees_by_year(con)
    if f.empty:
        return {"erreur": "aucune opération : lancer synchroniser"}
    f = f.assign(ordres_payants=f["ordres_payants"].astype(int), executions_plans=f["executions_plans"].astype(int))         if "ordres_payants" in f else f.assign(ordres_payants=0, executions_plans=0)
    sans_ter = queries.lines_without_ter(con)
    pos = queries.positions(con)
    held = pos[pos["isin"].isin(queries.TER)] if not pos.empty else pos
    detail = []
    for r in held.itertuples():
        if r.value == r.value and r.value:
            detail.append({"nom": r.name, "isin": r.isin, "compte": r.account, "valeur": r.value,
                           "ter_pct": queries.TER[r.isin] * 100, "cout_annuel": r.value * queries.TER[r.isin]})
    return _clean({
        "annees": f[["banque", "courtage", "ordres_payants", "executions_plans", "frais_fonds", "total"]].to_dict("index"),
        "frais_fonds_rythme_actuel": sum(d["cout_annuel"] for d in detail),
        "detail_fonds": detail,
        "isin_sans_ter": sans_ter,
        "note_isin_sans_ter": "frais des fonds sous-estimés pour ces lignes (TER inconnu, lignes détenues à un moment "
                              "sur la période) ; les actions n'ont pas de TER." if sans_ter else None,
        "note": "frais_fonds = estimation (TER × valeur moyenne) ; TER à vérifier dans les DIC. courtage : 1 € par "
                "ordre chez Trade Republic, plans d'épargne gratuits.",
    })


@tool
def pistes_fiscales() -> dict:
    """Pistes de fin d'année du compte-titres (le PEA et le PEG ne sont pas imposés tant qu'on n'en retire rien) :
    plus-values réalisées de l'année, lignes en moins-value latente qu'on pourrait vendre avant le 31/12 pour les
    compenser, économie d'impôt estimée = min(moins-values latentes, plus-values réalisées) × 30 %, moins-values
    reportables, impôt latent si on vendait tout le compte-titres, et date des 5 ans du PEA. Estimation PFU 30 %,
    à vérifier avec l'IFU ; pas un conseil fiscal."""
    con = _con()
    tax = queries.taxes(con)
    pos = queries.positions(con)
    if tax.empty and (pos.empty or pos["value"].isna().all()):
        return {"erreur": "aucune donnée fiscale ni position : lancer synchroniser"}
    today = pd.Timestamp.today().normalize()
    year = str(today.year)
    if not tax.empty:
        tax.index = tax.index.astype(str)
    cur = tax.loc[year] if year in tax.index else pd.Series(dtype=float)

    def g(k: str) -> float:
        return float(cur.get(k, 0.0) or 0.0)

    cto = pos[pos.account == queries.ACCOUNT_LABELS["tr_cto"]] if not pos.empty else pos
    latent = float(cto.gain.sum()) if not cto.empty else 0.0
    if year in tax.index:
        carry = g("moins_values_reportables")
    elif not tax.empty and "plus_values" in tax:
        # Année sans ligne (aucune vente, dividende ni intérêt) : report des années passées, moins de 10 ans.
        carry = portfolio.carry_into({int(k): float(v or 0.0) for k, v in tax["plus_values"].items()}, today.year)
    else:
        carry = 0.0
    gains = g("plus_values")
    taxable = g("plus_values_imposables")  # après imputation des moins-values reportables
    losers = cto[cto.gain < 0] if not cto.empty else cto
    latent_losses = float(-losers.gain.sum()) if not losers.empty else 0.0
    saving = min(latent_losses, taxable) * 0.30 if taxable > 0 else 0.0
    pistes = []
    if not losers.empty and taxable > 0:
        pistes.append(f"{taxable:.0f} € de plus-values imposables (après moins-values reportées) et "
                      f"{latent_losses:.0f} € de moins-values latentes : "
                      f"vendre les lignes en perte avant le 31/12 (puis les racheter si la conviction reste) "
                      f"économiserait jusqu'à {saving:.0f} € d'impôt.")
    elif not losers.empty:
        pistes.append("Lignes en perte sur le compte-titres : à vendre seulement si des plus-values sont réalisées "
                      "ailleurs cette année, pour les compenser.")
    if carry > 0:
        pistes.append(f"{carry:.0f} € de moins-values reportables : autant de plus-values réalisables sans impôt.")
    pea = None
    pea_open = queries.account_open_dates(con).get("tr_pea")
    if pea_open:
        five = pd.Timestamp(pea_open) + pd.DateOffset(years=5)
        left = (five - today).days
        pea = {"premiere_operation": pd.Timestamp(pea_open).date().isoformat(), "cinq_ans": five.date().isoformat(),
               "jours_restants": max(left, 0), "atteint": left <= 0}
        pistes.append("PEA : avant 5 ans, un retrait clôture le PEA et les gains sont taxés à 30 %." if left > 0 else
                      "PEA : 5 ans atteints, retraits possibles sans clôture (17,2 % de prélèvements sociaux sur les gains).")
    return _clean({
        "annee": int(year),
        "plus_values_realisees": gains,
        "dividendes_interets": g("dividendes") + g("interets"),
        "impot_estime_a_ce_jour": max(g("pfu_estime"), 0.0),
        "moins_values_reportables": carry,
        "plus_value_latente_cto": latent,
        "impot_si_tout_vendu": max(latent - carry, 0.0) * 0.30,
        "moins_values_latentes": latent_losses,
        "economie_estimee": saving,
        "lignes_en_perte": [{"nom": r.name, "isin": r.isin, "valeur": r.value, "moins_value": r.gain}
                            for r in losers.sort_values("gain").itertuples()],
        "pea": pea,
        "pistes": pistes,
        "note": "Estimation PFU 30 % sur le compte-titres uniquement ; vérifier avec l'IFU de Trade Republic.",
    })


@tool
def performance(compte: str = "", indice: str = "") -> dict:
    """Performance des placements Trade Republic : valeur, net investi, gain total, TRI (rendement de ton argent selon
    les dates de versement), TWR (rendement des placements, neutre aux versements : total, annualisé, 1 mois, depuis
    le 1er janvier, 1 an), volatilité annualisée, pire baisse et baisse actuelle depuis le plus haut. Rendements en
    fractions (0,05 = 5 %). `compte` : vide (compte-titres + PEA), "tr_cto" ou "tr_pea". `indice` (optionnel) :
    MSCI World, S&P 500, CAC 40 ou Nasdaq 100 ; compare à ce que les mêmes achats et ventes vaudraient placés dans
    l'indice (nécessite Internet pour les cours). Le PEG Airbus est exclu."""
    from . import analytics

    ids = {"": analytics.INVESTED, "tr_cto": ("tr_cto",), "cto": ("tr_cto",), "compte-titres": ("tr_cto",),
           "tr_pea": ("tr_pea",), "pea": ("tr_pea",)}
    accounts = ids.get(compte.strip().lower())
    if accounts is None:
        return {"erreur": f"compte inconnu : {compte!r} (tr_cto, tr_pea ou vide)"}
    bench_key = next((k for k in analytics.BENCHMARKS if k.lower() == indice.strip().lower()), None)
    if indice.strip() and bench_key is None:
        return {"erreur": f"indice inconnu : {indice!r} ({', '.join(analytics.BENCHMARKS)})"}
    con = _con()
    v = analytics.invested_series(con, accounts)
    if v.empty:
        return {"erreur": "aucun historique de titres : lancer synchroniser"}
    out: dict[str, Any] = {"donnees_au": queries.data_date(con).date().isoformat(), "comptes": list(accounts), "depuis": v.index[0].date().isoformat(),
                           "jusqu_au": v.index[-1].date().isoformat(), **analytics.stats(v)}
    if bench_key:
        try:
            b = analytics.benchmark(con, v, analytics.BENCHMARKS[bench_key])
        except Exception:  # noqa: BLE001 - pas de réseau, symbole indisponible
            b = None
        if b is None or b.empty:
            out["indice"] = {"nom": bench_key, "erreur": "cours indisponibles"}
        else:
            out["indice"] = {"nom": bench_key, "symbole": analytics.BENCHMARKS[bench_key],
                             "valeur_memes_versements": float(b.iloc[-1]),
                             "ecart_portefeuille": float(v.value.iloc[-1] - b.iloc[-1]),
                             "note": "Valeur si chaque achat et vente avait porté sur l'indice ; écart > 0 : le "
                                     "portefeuille a fait mieux."}
    return _clean(out)


@tool
def risques(baisse_pct: float = 20) -> dict:
    """Risques du portefeuille (PEA, compte-titres, PEG) : exposition réelle aux actions (valeur × levier : un ETF x2
    compte double), part à levier, part exposée au dollar (devise des actifs sous-jacents), plus grosse ligne en % du
    patrimoine total, et perte estimée si les actions baissent de `baisse_pct` % (chaque ligne baisse comme le marché,
    × levier, sans pouvoir perdre plus que sa valeur) avec le nombre de mois d'épargne (12 derniers mois complets)
    pour la combler. Détail par ligne. Estimation simple, sans corrélations ni effet de volatilité des ETF à levier."""
    from . import analytics

    if not 0 < baisse_pct <= 100:
        return {"erreur": "baisse_pct doit être entre 0 et 100"}
    con = _con()
    h = queries.history(con)
    pos = queries.positions(con)
    pos = pos[pos["value"].notna()] if not pos.empty else pos
    if h.empty or pos.empty:
        return {"erreur": "aucune position ou historique vide : lancer synchroniser"}
    wealth = float(h[h.date == h.date.max()].value.sum())
    risk = pos.assign(lev=pos["isin"].map(analytics.LEVERAGE).fillna(1.0),
                      cur=pos["isin"].map(analytics.CURRENCY).fillna("?"))
    risk["exposure"] = risk.value * risk.lev
    risk["loss"] = (risk.exposure * baisse_pct / 100).clip(upper=risk.value)
    total_value, exposure = float(risk.value.sum()), float(risk.exposure.sum())
    loss = float(risk.loss.sum())
    top = risk.sort_values("value", ascending=False).iloc[0]
    usd = float(risk[risk.cur == "USD"].exposure.sum())
    saving = None
    try:
        bal = analytics.monthly_balance(con)
        s = queries.complete_months(bal, queries.data_date(con)).epargne.tail(12).mean()
        saving = float(s) if s == s else None
    except Exception:  # noqa: BLE001 - pas encore de revenus ni de dépenses
        pass
    lignes = [{"nom": r.name, "compte": r.account, "devise_actifs": r.cur, "levier": r.lev, "valeur": r.value,
               "part_patrimoine": r.value / wealth if wealth else None, "perte_si_baisse": -r.loss}
              for r in risk.sort_values("loss", ascending=False).itertuples()]
    return _clean({
        "donnees_au": queries.data_date(con).date().isoformat(),
        "patrimoine_total": wealth,
        "valeur_investie": total_value,
        "exposition_reelle": exposure,
        "part_a_levier": float(risk[risk.lev > 1].value.sum()) / total_value if total_value else None,
        "exposition_dollar": usd,
        "part_dollar": usd / exposure if exposure else None,
        "plus_grosse_ligne": {"nom": top["name"], "valeur": top["value"],
                              "part_patrimoine": top["value"] / wealth if wealth else None},
        "baisse_pct": baisse_pct,
        "perte_estimee": -loss,
        "perte_pct_patrimoine": -loss / wealth if wealth else None,
        "epargne_mensuelle_moyenne": saving,
        "mois_epargne_pour_combler": loss / saving if saving and saving > 0 else None,
        "lignes": lignes,
        "note": "part_* en fractions. devise_actifs '?' : devise inconnue (analytics.CURRENCY). Au-delà de 20 % du "
                "patrimoine sur une seule action, un accident propre à l'entreprise pèse lourd.",
    })


@tool
def abonnements() -> dict:
    """Charges récurrentes encore actives (abonnements, loyer, assurances…) : commerçants payés d'un montant stable
    dans au moins 3 mois distincts et vus dans les 45 derniers jours. Pour chacun : montant mensuel médian, coût
    annuel (× 12), catégorie, nombre de mois, dernier paiement ; plus le total mensuel et annuel. Montants en euros.
    Le montant est celui du dernier paiement ; `ancien_montant` et `modifie_le` signalent une hausse ou baisse de prix."""
    from . import analytics

    con = _con()
    sp = queries.spending(con)
    if sp.empty:
        return {"erreur": "aucune dépense : lancer synchroniser"}
    rec = analytics.recurring(sp, include_ended=True)
    allitems = [{"marchand": r.merchant, "categorie": r.category, "montant_mensuel": r.amount, "cout_annuel": r.annual,
                 "mois": r.months, "depuis": r.since, "dernier_paiement": r.last, "statut": r.status,
                 "ancien_montant": None if pd.isna(r.previous_amount) else r.previous_amount,
                 "modifie_le": None if pd.isna(r.changed_on) else r.changed_on}
                for r in rec.itertuples()] if not rec.empty else []
    items = [i for i in allitems if i["statut"] == "actif"]
    ended = sorted((i for i in allitems if i["statut"] != "actif"), key=lambda i: i["dernier_paiement"], reverse=True)
    return _clean({"donnees_au": queries.data_date(con).date().isoformat(), "abonnements": items, "resilies": ended, "total_annuel": sum(i["cout_annuel"] for i in items),
                   "total_mensuel": sum(i["montant_mensuel"] for i in items),
                   "note": "Détection automatique : un marchand régulier mais de montant variable n'apparaît pas. "
                           "Résiliés : plus payés depuis plus de 45 jours (sur 24 mois)."})
