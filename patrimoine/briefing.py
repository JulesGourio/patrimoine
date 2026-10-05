"""Market analyses, daily (the last session) and weekly (the last five): facts computed here, analysis by Claude.

1. ``facts`` gathers what happened, from the database and Yahoo, with no judgement: Jules's lines against their
   index, the market (indices, rates, currencies, commodities, US sectors and themes), the stocks behind his ETFs
   that moved them most, analysts' rating changes, earnings coming up, the followed money's fresh filings and the
   radar. Each unusual move (large against the line's own daily volatility) is listed in ``to_explain``.
2. Claude (``scripts/analyse.md``, MCP tools ``faits_du_jour`` then ``publier_analyse``) researches those moves
   on the web, 24 to 72 hours back, and fills a fixed structure (``validate``): every claim cites a source.
3. ``publish`` stores it, sends a short mail with a chart (``brief_mail``) and a one-line push; the Analyses page
   shows the whole of it.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import date, timedelta

import pandas as pd

from . import db, queries

log = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS briefings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,                 -- quotidien, hebdo
    session TEXT NOT NULL,              -- last US session covered, YYYY-MM-DD
    facts TEXT NOT NULL,                -- JSON, see facts()
    analysis TEXT,                      -- JSON written by Claude, see validate(); NULL while a draft
    published_at TEXT,
    sent_to TEXT
);
"""

# (Yahoo symbol, label, group). ^TNX is the US 10-year yield in percent: its move is shown in basis points.
MARKET = [
    ("^GSPC", "S&P 500", "Indices"), ("^NDX", "Nasdaq 100", "Indices"), ("^FCHI", "CAC 40", "Indices"),
    ("^STOXX", "Stoxx 600", "Indices"), ("^KS11", "Kospi", "Indices"), ("^N225", "Nikkei 225", "Indices"),
    ("^VIX", "VIX (peur)", "Indices"),
    ("^TNX", "Taux US 10 ans", "Taux et devises"), ("EURUSD=X", "Euro / dollar", "Taux et devises"),
    ("GC=F", "Or", "Matières premières"), ("BZ=F", "Pétrole Brent", "Matières premières"),
    ("HG=F", "Cuivre", "Matières premières"), ("BTC-EUR", "Bitcoin", "Crypto"),
]
SECTORS = [
    ("XLK", "Technologie"), ("SMH", "Semi-conducteurs"), ("XLC", "Communication"), ("XLY", "Conso. cyclique"),
    ("XLF", "Finance"), ("XLV", "Santé"), ("XLI", "Industrie"), ("ITA", "Aéro et défense"), ("XLE", "Énergie"),
    ("XLB", "Matériaux"), ("XLP", "Conso. de base"), ("XLU", "Services publics"), ("XLRE", "Immobilier"),
    ("UFO", "Spatial"), ("REMX", "Terres rares et métaux"), ("EWY", "Corée"),
]
# Jules's lines -> the index or theme each should be read against (and the line's leverage on it).
BENCH = {
    "NL0000235190": ("^FCHI", 1.0),     # Airbus: against the Paris market (ITA is in the sectors)
    "FR0011550185": ("^GSPC", 1.0),
    "FR0010342592": ("^NDX", 2.0),
    "IE00BHZRR030": ("^KS11", 1.0),
    "IE000YU9K6K2": ("UFO", 1.0),
    "IE000KHX9DX6": ("REMX", 1.0),
}
NAMES = dict([(s, n) for s, n, _ in MARKET] + SECTORS)
UNUSUAL_Z = 1.5                         # a move this many daily standard deviations away is worth explaining
PERIODS = {"jour": 1, "semaine": 5}


def _download(tickers: list[str], start: date) -> pd.DataFrame:
    """Raw daily closes, one column per ticker, holidays left empty (no forward fill: a closed market did not
    move)."""
    import yfinance as yf

    tickers = list(dict.fromkeys(t for t in tickers if t))
    if not tickers:
        return pd.DataFrame()
    try:
        got = yf.download(tickers, start=start.isoformat(), auto_adjust=True, progress=False, threads=True)["Close"]
    except Exception as e:  # noqa: BLE001 - network or Yahoo format change
        log.warning("Yahoo: %s", e)
        return pd.DataFrame()
    df = got if isinstance(got, pd.DataFrame) else got.to_frame(tickers[0])
    df.index = pd.to_datetime(df.index).tz_localize(None).normalize()
    return df[df.index < session_cutoff()]


def session_cutoff() -> pd.Timestamp:
    """Today's session counts once Wall Street has closed (22:00 Paris, 22:30 for margin); before that its
    prices are intraday."""
    now = pd.Timestamp.now(tz="Europe/Paris")
    today = now.tz_localize(None).normalize()
    return today + pd.Timedelta(days=1) if now.hour * 60 + now.minute >= 22 * 60 + 30 else today


def stats(s: pd.Series, days: int, level: bool = False) -> dict | None:
    """Move over the last ``days`` sessions, 1 month, and how unusual it is (z: move over the daily standard
    deviation of the 60 sessions before, scaled by sqrt(days)). ``level``: a rate, whose move is a difference."""
    s = s.dropna()
    if len(s) < days + 2:
        return None
    last, prev = float(s.iloc[-1]), float(s.iloc[-1 - days])
    month = float(s.iloc[-22]) if len(s) > 22 else float(s.iloc[0])
    if level:
        move, m1 = last - prev, last - month
        daily = s.diff().iloc[-61 - days:-days].dropna()
    else:
        move, m1 = last / prev - 1, last / month - 1
        daily = s.pct_change().iloc[-61 - days:-days].dropna()
    sd = float(daily.std()) if len(daily) > 10 else float("nan")
    z = move / (sd * math.sqrt(days)) if sd and sd == sd else None
    return {"date": s.index[-1].date().isoformat(), "depuis": s.index[-1 - days].date().isoformat(),
            "last": round(last, 4), "move": round(move, 5),
            "m1": round(m1, 5), "z": round(z, 2) if z is not None else None}


def _series(s: pd.Series, n: int = 66) -> list[list]:
    s = s.dropna().tail(n)
    return [[d.date().isoformat(), round(float(v), 4)] for d, v in s.items()]


def _lines(con: sqlite3.Connection) -> pd.DataFrame:
    pos = queries.positions(con)
    if pos.empty:
        return pos
    g = pos.groupby("isin").agg(name=("name", "first"), value=("value", "sum"), cost=("cost", "sum"),
                                account=("account", lambda a: ", ".join(sorted(set(a)))))
    g["weight"] = g["value"] / g["value"].sum()
    return g.sort_values("value", ascending=False)


def _prices(con: sqlite3.Connection, isin: str) -> pd.Series:
    df = pd.read_sql_query("SELECT date, close FROM prices WHERE isin = ? AND date >= ? ORDER BY date", con,
                           params=(isin, (date.today() - timedelta(days=150)).isoformat()), parse_dates=["date"])
    s = df.set_index("date")["close"]
    return s[s.index < session_cutoff()]


def _analysts(tickers: list[str], since: date) -> list[dict]:
    import yfinance as yf

    out = []
    for t in tickers:
        try:
            ud = yf.Ticker(t).upgrades_downgrades
        except Exception:  # noqa: BLE001
            continue
        if ud is None or ud.empty:
            continue
        ud = ud[pd.to_datetime(ud.index).tz_localize(None) >= pd.Timestamp(since)]
        for d, r in ud.iterrows():
            moved = r.get("currentPriceTarget") != r.get("priorPriceTarget")
            if r.get("Action") not in ("up", "down", "init") and not moved:
                continue  # a rating merely reiterated says nothing new
            out.append({"ticker": t, "date": pd.Timestamp(d).date().isoformat(), "firme": r.get("Firm"),
                        "action": r.get("Action"), "avant": r.get("FromGrade") or None, "apres": r.get("ToGrade"),
                        "objectif": r.get("currentPriceTarget") or None,
                        "objectif_avant": r.get("priorPriceTarget") or None})
    return out


def _earnings(tickers: list[str], until: date) -> list[dict]:
    import yfinance as yf

    out = []
    for t in tickers:
        try:
            cal = yf.Ticker(t).calendar or {}
        except Exception:  # noqa: BLE001
            continue
        for d in cal.get("Earnings Date") or []:
            d = pd.Timestamp(d).date()
            if date.today() <= d <= until:
                out.append({"ticker": t, "date": d.isoformat(), "evenement": "résultats",
                            "bpa_attendu": cal.get("Earnings Average")})
                break
    return sorted(out, key=lambda e: e["date"])


def facts(con: sqlite3.Connection, period: str = "jour") -> dict:
    """Everything the analysis starts from, as JSON-ready data. ``period``: 'jour' (last session) or 'semaine'
    (last five)."""
    from . import fresh, radar

    days = PERIODS[period]
    start = date.today() - timedelta(days=150)
    lines = _lines(con)
    exposure = db.get_meta(con, "exposure") or {}
    top_exp = [t for t, e in sorted(exposure.items(), key=lambda x: -x[1]["eur"]) if t != "EADSY"][:25]
    # Yahoo files Korean ordinary shares under .KS (KOSPI); the ETF holdings sometimes say .KQ.
    yahoo = {t: t.replace(".KQ", ".KS") for t in top_exp}
    px = _download([s for s, _, _ in MARKET] + [s for s, _ in SECTORS] + [b for b, _ in BENCH.values()]
                   + list(yahoo.values()), start)

    def col(t: str) -> pd.Series:
        return px[t] if t in px else pd.Series(dtype=float)

    market = []
    for sym, label, group in MARKET:
        st = stats(col(sym), days, level=sym == "^TNX")
        if st:
            market.append({"symbole": sym, "nom": label, "groupe": group, **st})
    sectors = []
    for sym, label in SECTORS:
        st = stats(col(sym), days)
        if st:
            sectors.append({"symbole": sym, "nom": label, **st})
    sectors.sort(key=lambda x: -x["move"])

    session = next((m["date"] for m in market if m["symbole"] == "^GSPC"), date.today().isoformat())
    out_lines, series = [], {}
    for isin, r in lines.iterrows():
        s = _prices(con, isin)
        st = stats(s, days)
        bench, lev = BENCH.get(isin, (None, 1.0))
        bst = stats(col(bench), days) if bench else None
        row = {"isin": isin, "nom": r["name"], "compte": r["account"], "valeur": round(float(r["value"]), 2),
               "poids": round(float(r["weight"]), 4),
               "plus_value_latente_pct": (round(float(r["value"] / r["cost"] - 1), 4)
                                          if r["cost"] and r["cost"] == r["cost"] else None),
               "indice": NAMES.get(bench, bench), "indice_symbole": bench, "levier": lev}
        if st:
            row.update(st)
            row["impact_eur"] = round(float(r["value"]) - float(r["value"]) / (1 + st["move"]), 2)
            series[isin] = _series(s)
        if bst:
            row["indice_move"], row["indice_date"] = bst["move"], bst["date"]
            series[bench] = _series(col(bench))
        out_lines.append(row)

    movers = []
    for t in top_exp:
        st = stats(col(yahoo[t]), days)
        if not st:
            continue
        e = exposure[t]
        movers.append({"ticker": t, "via": e["via"], "exposition_eur": round(e["eur"], 2), "move": st["move"],
                       "z": st["z"], "contribution_eur": round(e["eur"] * st["move"], 2), "date": st["date"]})
    movers.sort(key=lambda m: -abs(m["contribution_eur"]))

    since = date.fromisoformat(session) - timedelta(days=days + 2)
    watch = ["AIR.PA"] + [yahoo[t] for t in top_exp[:12]]
    analysts = _analysts(watch, since)
    earnings = _earnings(["AIR.PA"] + [yahoo[t] for t in top_exp[:20]], date.today() + timedelta(days=14))

    hist = queries.history(con)
    total = hist.groupby("date")["value"].sum() if not hist.empty else pd.Series(dtype=float)
    feed = fresh.feed(con, days=3 if days == 1 else 8)
    if not feed.empty:
        feed = feed.sort_values("value_usd", ascending=False, na_position="last").head(12)
    rad = radar.load(con)

    to_explain = []
    for r in out_lines:
        if r.get("z") is not None and (abs(r["z"]) >= UNUSUAL_Z or abs(r["move"]) >= 0.02 * math.sqrt(days)):
            gap = (f", indice {r['indice']} {r['indice_move']:+.2%}" if r.get("indice_move") is not None else "")
            to_explain.append(f"Ligne {r['nom']} : {r['move']:+.2%} (z = {r['z']:+.1f}{gap})")
    for m in market + sectors:
        if m.get("z") is not None and abs(m["z"]) >= 2:
            unit = f"{m['move'] * 100:+.0f} pb" if m["symbole"] == "^TNX" else f"{m['move']:+.2%}"
            to_explain.append(f"Marché {m['nom']} : {unit} (z = {m['z']:+.1f})")
    for m in movers[:8]:
        if abs(m["move"]) >= 0.03 * math.sqrt(days):
            to_explain.append(f"Dans tes ETF, {m['ticker']} : {m['move']:+.2%} ({m['contribution_eur']:+.0f} € pour toi)")

    accounts = []
    if not hist.empty:
        now = hist[hist.date == hist.date.max()]
        accounts = [{"compte": r.account, "id": r.account_id, "valeur": round(r.value, 2), "especes": round(r.cash, 2),
                     "titres": round(r.securities, 2), "versements_nets": round(r.deposits, 2)}
                    for r in now.itertuples() if r.value]

    return _clean({
        "periode": period, "seance": session, "calcule_le": db.now_iso(),
        "patrimoine": {
            "total": round(float(total.iloc[-1]), 2) if len(total) else None,
            "date": total.index[-1].date().isoformat() if len(total) else None,
            "effet_marche_eur": round(sum(r.get("impact_eur", 0) for r in out_lines), 2),
            "titres": round(float(lines["value"].sum()), 2) if not lines.empty else None,
        },
        "comptes": accounts, "lignes": out_lines, "marche": market, "secteurs": sectors, "moteurs_etf": movers[:10],
        "analystes": analysts, "resultats_a_venir": earnings,
        "argent_suivi": [] if feed.empty else feed[["date", "kind", "who", "ticker", "name", "what", "value_usd",
                                                     "since", "mine", "link"]].to_dict("records"),
        "radar": [] if rad.empty else [
            {"ticker": r.ticker, "nom": r.name, "score": r.score, "pourquoi": radar._why(r),
             "depuis_signal": getattr(r, "since_signal", None), "r1m": r.r1m}
            for r in rad.head(5).itertuples()],
        "a_expliquer": to_explain,
        "series": series,
    })


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, float):
        return None if math.isnan(x) else x
    if isinstance(x, pd.Timestamp):
        return x.date().isoformat()
    if hasattr(x, "item"):
        return _clean(x.item())
    return x


def draft(con: sqlite3.Connection, period: str = "jour") -> tuple[int, dict]:
    con.executescript(SCHEMA)
    f = facts(con, period)
    cur = con.execute("INSERT INTO briefings (created_at, kind, session, facts) VALUES (?, ?, ?, ?)",
                      (db.now_iso(), "hebdo" if period == "semaine" else "quotidien", f["seance"], json.dumps(f)))
    con.commit()
    return cur.lastrowid, f


# ---------- what Claude writes ----------

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


def load(con: sqlite3.Connection, published: bool = True) -> pd.DataFrame:
    con.executescript(SCHEMA)
    q = "SELECT * FROM briefings" + (" WHERE analysis IS NOT NULL" if published else "") + " ORDER BY id DESC"
    df = pd.read_sql_query(q, con)
    for c in ("facts", "analysis"):
        df[c] = df[c].map(lambda s: json.loads(s) if s else None)
    return df


def publish(con: sqlite3.Connection, briefing_id: int, analysis: dict, send: bool = True) -> dict:
    con.executescript(SCHEMA)
    row = con.execute("SELECT kind, facts FROM briefings WHERE id = ?", (briefing_id,)).fetchone()
    if not row:
        return {"erreurs": [f"analyse {briefing_id} introuvable : appeler d'abord faits_du_jour"]}
    problems = validate(analysis)
    if problems:
        return {"erreurs": problems}
    con.execute("UPDATE briefings SET analysis = ?, published_at = ? WHERE id = ?",
                (json.dumps(analysis, ensure_ascii=False), db.now_iso(), briefing_id))
    con.commit()
    sent = None
    if send:
        from . import brief_mail

        sent = brief_mail.send(row["kind"], json.loads(row["facts"]), analysis)
        con.execute("UPDATE briefings SET sent_to = ? WHERE id = ?", (sent, briefing_id))
        con.commit()
    return {"ok": True, "id": briefing_id, "envoye": sent}


def verdicts(con: sqlite3.Connection) -> pd.DataFrame:
    """Every verdict given on a line, with the line's move since (and its index's): is the advice any good?"""
    b = load(con)
    rows = []
    for r in b.itertuples():
        lines = {l["isin"]: l for l in r.facts.get("lignes", [])}
        for v in r.analysis.get("lignes", []):
            l = lines.get(v.get("isin"), {})
            rows.append({"date": r.session, "isin": v.get("isin"), "nom": l.get("nom", v.get("isin")),
                         "verdict": v.get("verdict"), "confiance": v.get("confiance"), "action": v.get("action"),
                         "cours": l.get("last")})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    last = {isin: c for isin, c in con.execute(
        "SELECT isin, close FROM prices p WHERE date = (SELECT MAX(date) FROM prices WHERE isin = p.isin)")}
    df["cours_actuel"] = df["isin"].map(last)
    df["depuis"] = df["cours_actuel"] / df["cours"] - 1
    return df


def advice(con: sqlite3.Connection) -> pd.DataFrame:
    """Every piece of advice with a ticker, and its price then: the page adds the price now."""
    rows = []
    for r in load(con).itertuples():
        for c in r.analysis.get("conseils", []):
            if c.get("ticker") and c.get("cours_ref"):
                rows.append({"date": r.session, "action": c["action"], "cible": c["cible"], "ticker": c["ticker"],
                             "montant_eur": c.get("montant_eur"), "confiance": c.get("confiance"),
                             "cours_ref": c["cours_ref"]})
    return pd.DataFrame(rows)
