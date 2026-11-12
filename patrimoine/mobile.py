"""Bridge for the Android app, which runs this package on the phone through Chaquopy.

Kotlin calls a handful of functions, always with plain strings and always getting a JSON string back:
``{"ok": true, "data": …}`` or ``{"ok": false, "erreur": "…"}``. Nothing here is Android-specific: the Kotlin side
hands over its secret store (Android Keystore) and its notifier, everything else is the same code as on the PC.

- ``init(data_dir, secrets, notifier)`` once at start;
- ``call(name, args_json)`` for every tool of `api` and the screens below (`SCREENS`);
- ``sync()``, ``pull_analyses()`` from the background worker (and the « Synchroniser » button);
- the few actions that need the phone: importing a picked file, Trade Republic login, CMB consent.

Never an order: like `api`, this module has nothing that could place one.
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import threading
import time
import traceback
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable

from . import api, db, notify, vault
from .config import Settings

log = logging.getLogger(__name__)

_sync_lock = threading.Lock()
SCREENS: dict[str, Callable[..., Any]] = {}


def screen(fn: Callable[..., Any]) -> Callable[..., Any]:
    SCREENS[fn.__name__] = fn
    return fn


def settings() -> Settings:
    return Settings()


def _reply(fn: Callable[[], Any]) -> str:
    try:
        data = fn()
        if isinstance(data, dict) and "erreur" in data and len(data) == 1:
            return json.dumps({"ok": False, "erreur": str(data["erreur"])}, ensure_ascii=False)
        return json.dumps({"ok": True, "data": api._clean(data)}, ensure_ascii=False, default=str)
    except Exception as e:  # noqa: BLE001 - the app shows the message; the log keeps the trace
        log.error("%s", traceback.format_exc())
        return json.dumps({"ok": False, "erreur": str(e) or e.__class__.__name__}, ensure_ascii=False)


class _ForeignVault:
    """Wrap the Kotlin secret store; Java strings and nulls come back as str and None."""

    def __init__(self, store: Any) -> None:
        self.store = store

    def get(self, name: str) -> str | None:
        v = self.store.get(name)
        return None if v is None else str(v)

    def set(self, name: str, value: str) -> None:  # noqa: A003
        self.store.set(name, value)

    def delete(self, name: str) -> None:
        self.store.delete(name)


def init(data_dir: str, secrets: Any = None, notifier: Any = None) -> str:
    """Point the package at the app's private folder, install the phone's secret store and notifications.
    ``notifier.show(title, message, priority)`` returns whether it was shown."""

    def run() -> dict:
        os.environ["PATRIMOINE_DATA_DIR"] = data_dir
        if secrets is not None:
            vault.use(_ForeignVault(secrets))
        if notifier is not None:
            notify.set_local(lambda t, m, p: bool(notifier.show(t, m, int(p))))
        s = settings()
        logs = s.data_dir / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        root = logging.getLogger()
        if not any(isinstance(h, logging.FileHandler) for h in root.handlers):
            h = logging.FileHandler(logs / f"app-{date.today().isoformat()}.log", encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
            root.addHandler(h)
            root.setLevel(logging.INFO)
        with db.session(s.db_path) as con:
            # Readers (screens) never wait for the writer (sync); the mode stays with the file.
            con.execute("PRAGMA journal_mode = WAL")
            db.init(con)
        return etat()

    return _reply(run)


def tools() -> str:
    """Name, parameters and description of everything ``call`` accepts (for the app's debug screen)."""
    def describe(fn: Callable) -> dict:
        params = [p.name for p in inspect.signature(fn).parameters.values()]
        return {"nom": fn.__name__, "parametres": params, "description": inspect.getdoc(fn) or ""}

    return _reply(lambda: [describe(f) for f in [*api.TOOLS, *SCREENS.values()]])


# Read-only functions computed from the database alone (no network): their answer only changes when the database
# does, so a tab opened twice is instant (pandas on a phone takes seconds per screen).
_CACHEABLE = {"accueil", "portefeuille", "depenses_ecran", "ventes_realisees", "analyses", "analyse", "positions",
              "synthese", "patrimoine", "historique", "depenses", "flux", "fiscalite", "alertes", "ordres_proposes", "references"}
_cache: dict[tuple, str] = {}


def _db_stamp() -> tuple:
    """Changes whenever the database file or its write-ahead log is written."""
    path = settings().db_path
    stamp = []
    for p in (path, path.with_name(path.name + "-wal")):
        try:
            st = p.stat()
            stamp.append((st.st_mtime_ns, st.st_size))
        except OSError:
            stamp.append(None)
    return tuple(stamp)


def call(name: str, args_json: str = "{}") -> str:
    """Run one tool or screen by name with JSON keyword arguments."""
    key = (name, args_json, _db_stamp()) if name in _CACHEABLE else None
    if key and key in _cache:
        return _cache[key]
    started = time.monotonic()
    reply = _call(name, args_json)
    took = time.monotonic() - started
    if took > 0.5:
        log.info("écran %s : %.1f s (%d ko)", name, took, len(reply) // 1024)
    if key and reply.startswith('{"ok": true'):
        if len(_cache) >= 24:
            _cache.pop(next(iter(_cache)))
        _cache[key] = reply
    return reply


def _call(name: str, args_json: str) -> str:
    def run() -> Any:
        fn = SCREENS.get(name) or next((f for f in api.TOOLS if f.__name__ == name), None)
        if fn is None:
            raise ValueError(f"fonction inconnue : {name}")
        args = json.loads(args_json or "{}")
        if not isinstance(args, dict):
            raise ValueError("les arguments doivent être un objet JSON")
        return fn(**args)

    return _reply(run)


# --- Screens: what a phone screen needs in one call, on top of the tools --------------------------------------


@screen
def etat() -> dict:
    """État de l'appli : base, dernière synchro, connexions Trade Republic et CMB, secrets renseignés."""
    s = settings()
    with db.session(s.db_path) as con:
        db.init(con)
        n = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        last = db.get_meta(con, "last_sync") or {}
        cmb_until = db.get_meta(con, "cmb_consent_until")
        ages = {k: db.get_meta(con, m) for k, m in (("trade_republic", "last_sync_tr"), ("cmb", "last_sync_cmb"))}
    return {
        "sources_maj": ages,
        "durees_synchro": last.get("durations") or {},
        "duree_totale_s": last.get("total_s"),
        "base": str(s.db_path),
        "operations": n,
        "derniere_synchro": last.get("at"),
        "resume_synchro": last.get("summary") or [],
        "trade_republic_session": (s.data_dir / "tr_cookies.txt").exists(),
        "cmb_acces_jusqu_au": cmb_until,
        "cmb_cle": any((s.data_dir / "enablebanking").glob("*.pem")),
        "secrets": {name: bool(vault.get(name)) for name in vault.KNOWN},
        "synchro_en_cours": _sync_lock.locked(),
    }


_SECURITIES_ACCOUNTS = ("tr_cto", "tr_pea")  # same accounts as api.patrimoine's cost basis


def _points(s) -> list:
    """Daily series as [[ISO date, value rounded to the cent]]."""
    step = max(1, len(s) // 400)  # a chart cannot show more than a few hundred points: 10 years of days weigh 700 KB
    keep = list(range(len(s) - 1, -1, -step))[::-1]  # always ends on the last day
    return [[s.index[i].date().isoformat(), round(float(s.iloc[i]), 2)] for i in keep]


@screen
def accueil(jours: int = 3650) -> dict:
    """Écran d'accueil : patrimoine total et par compte, courbe du total, dernière analyse, ordres et alertes."""
    import pandas as pd

    from . import queries

    out: dict[str, Any] = {"patrimoine": api.patrimoine()}
    with db.session(settings().db_path) as con:
        h = queries.history(con)
    if not h.empty:
        total = h.groupby("date")["value"].sum()
        total = total[total.index >= total.index.max() - pd.Timedelta(days=jours)]
        since = total.index.min()
        out["courbe"] = _points(total)
        w = h[h.date >= since]
        out["courbes_comptes"] = {name: _points(g.set_index("date")["value"]) for name, g in w.groupby("account")}
        inv = w[w.account_id.isin(_SECURITIES_ACCOUNTS)].groupby("date")[["securities", "cost"]].sum()
        out["courbe_titres"] = {"valeur": _points(inv["securities"]), "cout": _points(inv["cost"])}
    else:
        out["courbe"] = []
        out["courbes_comptes"] = {}
        out["courbe_titres"] = {"valeur": [], "cout": []}
    out["comptes_titres"] = [queries.ACCOUNT_LABELS[a] for a in _SECURITIES_ACCOUNTS]
    out["synthese"] = api.synthese()  # {"erreur": ...} si l'historique est vide
    last = api.analyses(1)
    out["derniere_analyse"] = (last.get("analyses") or [None])[0]
    out["ordres_proposes"] = len(api.ordres_proposes().get("ordres") or [])
    out["alertes_30j"] = len(api.alertes().get("recentes") or [])
    return out


@screen
def references() -> dict:
    """Listes des écrans : catégories de dépenses et de revenus, comptes (les livrets prennent un solde saisi)."""
    from .categories import INCOME, SPENDING

    with db.session(settings().db_path) as con:
        db.init(con)
        accounts = [dict(r) for r in con.execute("SELECT id, institution, name, kind FROM accounts WHERE active = 1"
                                                 " ORDER BY institution, id")]
    return {"categories_depenses": SPENDING, "categories_revenus": INCOME, "comptes": accounts,
            "comptes_solde_manuel": [a["id"] for a in accounts if a["kind"] == "livret"]}


@screen
def analyse(id: int) -> dict:
    """Une analyse publiée en entier (marché, thèmes, lignes, idées, conseils, sources), avec les faits utiles
    à l'écran : nom, variation et effet en euros de chaque ligne (sans les séries de cours)."""
    from . import briefing

    with db.session(settings().db_path) as con:
        b = briefing.load(con)
    rows = b[b.id == int(id)]
    if rows.empty:
        return {"erreur": f"analyse {id} introuvable"}
    r = rows.iloc[0]
    facts = r.facts or {}
    keep = ("nom", "compte", "valeur", "poids", "move", "impact_eur", "indice", "indice_move")
    return {"id": int(r.id), "type": r.kind, "seance": r.session, "analyse": r.analysis,
            "patrimoine": facts.get("patrimoine"),
            "lignes": {l["isin"]: {k: l.get(k) for k in keep} for l in facts.get("lignes", []) if l.get("isin")},
            "marche": [{k: m.get(k) for k in ("nom", "groupe", "move")} for m in facts.get("marche", [])][:12]}


# --- Background work ------------------------------------------------------------------------------------------


def _sync(send_alerts: bool = True) -> dict:
    if not _sync_lock.acquire(blocking=False):
        return {"deja_en_cours": True, "lignes": []}
    try:
        from . import pipeline

        return {"deja_en_cours": False, "lignes": pipeline.run(settings(), send_alerts=send_alerts)}
    finally:
        _sync_lock.release()


def sync(send_alerts: bool = True) -> str:
    """The daily sync (same steps as the PC's 7:30 task), then the cloud analyses. One at a time."""
    return _reply(lambda: _sync(send_alerts))


@screen
def synchroniser() -> dict:
    """Relance la synchronisation complète (comme le bouton) ; une seule à la fois sur le téléphone."""
    return _sync()


def _market_hours(now: datetime | None = None) -> bool:
    """Weekdays 8:00–22:00 in Paris: the only time prices move for the lines held (Europe, then the US close)."""
    from zoneinfo import ZoneInfo

    now = now or datetime.now(ZoneInfo("Europe/Paris"))
    return now.weekday() < 5 and 8 <= now.hour < 22


def veille(force: bool = False) -> str:
    """Light, frequent pass for the price alerts: prices, valuation, alert rules. No bank."""
    def run() -> dict:
        if not force and not _market_hours():
            return {"ignoree": "hors des heures de marché", "alertes": 0}
        if not _sync_lock.acquire(blocking=False):
            return {"ignoree": "synchronisation en cours", "alertes": 0}
        try:
            from . import alerts, portfolio, prices

            with db.session(settings().db_path) as con:
                db.init(con)
                book, _ = portfolio.replay(con)
                held = sorted({isin for (_, isin), line in book.lines.items() if line.quantity > 1e-6})
                if held:  # only the lines held: the full history of every instrument is the daily sync's job
                    prices.update(con, held)
                df, _ = portfolio.valuations(con)
                portfolio.store(con, df)
                con.commit()
                fired = alerts.run(con, send=True)
            return {"alertes": len(fired), "titres": [f.title for f in fired]}
        finally:
            _sync_lock.release()

    return _reply(run)


def pull_analyses() -> str:
    """Publish the analyses the Claude cloud routines pushed since last time (every hour or so)."""
    from . import cloud

    return _reply(lambda: {"lignes": cloud.pull(settings())})


# --- Actions that need the phone ------------------------------------------------------------------------------


def import_file(kind: str, path: str) -> str:
    """A file Jules picked, copied by the app into its cache: ``peg`` (Amundi AVO*.pdf), ``cmb_csv``
    (RELEVE_*.csv), ``base`` (a whole patrimoine.db, from the PC) or ``cle_cmb`` (Enable Banking .pem)."""
    def run() -> Any:
        from . import imports

        p = Path(path)
        if kind == "peg":
            return imports.peg(settings(), [p])
        if kind == "cmb_csv":
            return imports.cmb_csv(settings(), [p])
        if kind == "base":
            if not _sync_lock.acquire(blocking=False):
                raise RuntimeError("synchronisation en cours : réessaie quand elle est finie")
            try:
                return imports.database(settings(), p)
            finally:
                _sync_lock.release()
        if kind == "cle_cmb":
            from .sources import enable_banking as eb

            return {"application": eb.install_key(settings(), p)}
        raise ValueError(f"type de fichier inconnu : {kind}")

    return _reply(run)


def export_database(dest: str) -> str:
    """A consistent copy of the database at ``dest`` (the app then shares or saves it)."""
    from . import imports

    return _reply(lambda: {"fichier": str(imports.backup(settings(), Path(dest)))})


def set_balance(account: str, amount: str) -> str:
    from . import imports

    return _reply(lambda: {"centimes": imports.balance(settings(), account, amount)})


def set_secret(name: str, value: str) -> str:
    def run() -> dict:
        if name not in vault.KNOWN:
            raise ValueError(f"secret inconnu : {name}")
        value_ = (value or "").strip()
        if value_:
            vault.set(name, value_)
        else:
            vault.delete(name)
        return {name: bool(value_)}

    return _reply(run)


def tr_login() -> str:
    """Log in to Trade Republic: blocks until Jules confirms in the Trade Republic app (2 minutes at most)."""
    def run() -> dict:
        from .sources import trade_republic

        def no_code() -> str:
            raise trade_republic.LoginRequired("Ce compte demande un code d'authentification : connecte-toi une "
                                               "fois depuis le PC (`patrimoine tr login`).")

        trade_republic.connect(settings(), interactive=True, ask_code=no_code)
        return {"connecte": True}

    return _reply(run)


def cmb_consent_url() -> str:
    """Where Jules signs in to the CMB; the app opens it and watches for the redirect (`enable_banking`)."""
    from .sources import enable_banking as eb

    return _reply(lambda: {"url": eb.start_consent(settings()), "retour": eb.REDIRECT_URL})


def cmb_consent_finish(redirected_to: str) -> str:
    from .sources import enable_banking as eb

    return _reply(lambda: {"comptes": len(eb.finish_consent(settings(), redirected_to))})


def test_notification() -> str:
    return _reply(lambda: {"canaux": notify.send("Test Patrimoine", "Les notifications fonctionnent.", email=False)})


@screen
def depenses_ecran(mois: int = 13) -> dict:
    """Écran Dépenses en un appel : opérations des N derniers mois, totaux par mois, budgets du mois en cours,
    revenus/dépenses/épargne par mois et liste des catégories de dépenses."""
    from .categories import SPENDING

    dep = api.depenses(mois)
    return {"operations": api.depenses_operations(mois)["operations"], "par_mois": dep["par_mois"],
            "mois_en_cours": dep["mois_en_cours"], "flux": api.flux(mois)["flux"], "categories": SPENDING}


@screen
def portefeuille() -> dict:
    """Écran Portefeuille : lignes (comme `positions`), mini-séries de cours sur 3 mois par ISIN et patrimoine
    total (pour dire la part d'une ligne dans le patrimoine)."""
    import pandas as pd

    from . import portfolio, queries

    out = api.positions()
    with db.session(settings().db_path) as con:
        h = queries.history(con)
        _, prices = portfolio.replay(con) if out["positions"] else (None, None)
    series: dict[str, list] = {}
    for isin in {p["isin"] for p in out["positions"]}:
        s = prices.series.get(isin)
        if s is None or not len(s):
            continue
        days = s.index[s.index >= s.index[-1] - pd.Timedelta(days=91)]
        vals = [prices.get(isin, d) for d in days]
        series[isin] = [round(v, 4) for v in vals if v is not None]
    out["series"] = series
    out["patrimoine_total"] = float(h[h.date == h.date.max()]["value"].sum()) if not h.empty else None
    return out
