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
import traceback
from datetime import date
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


def call(name: str, args_json: str = "{}") -> str:
    """Run one tool or screen by name with JSON keyword arguments."""
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
    return {
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


@screen
def accueil(jours: int = 365) -> dict:
    """Écran d'accueil : patrimoine total et par compte, courbe du total, dernière analyse, ordres et alertes."""
    import pandas as pd

    from . import queries

    out: dict[str, Any] = {"patrimoine": api.patrimoine()}
    with db.session(settings().db_path) as con:
        h = queries.history(con)
    if not h.empty:
        total = h.groupby("date")["value"].sum()
        total = total[total.index >= total.index.max() - pd.Timedelta(days=jours)]
        out["courbe"] = [[d.date().isoformat(), round(float(v), 2)] for d, v in total.items()]
    else:
        out["courbe"] = []
    last = api.analyses(1)
    out["derniere_analyse"] = (last.get("analyses") or [None])[0]
    out["ordres_proposes"] = len(api.ordres_proposes().get("ordres") or [])
    out["alertes_30j"] = len(api.alertes().get("recentes") or [])
    return out


# --- Background work ------------------------------------------------------------------------------------------


def _sync(send_alerts: bool = True) -> dict:
    if not _sync_lock.acquire(blocking=False):
        return {"deja_en_cours": True, "lignes": []}
    try:
        from . import cloud, pipeline

        lines = pipeline.run(settings(), send_alerts=send_alerts)
        try:
            lines += cloud.pull(settings())
        except Exception as e:  # noqa: BLE001 - the sync itself went through
            log.error("cloud pull: %s", traceback.format_exc())
            lines.append(f"Analyses cloud : ÉCHEC — {e}")
        return {"deja_en_cours": False, "lignes": lines}
    finally:
        _sync_lock.release()


def sync(send_alerts: bool = True) -> str:
    """The daily sync (same steps as the PC's 7:30 task), then the cloud analyses. One at a time."""
    return _reply(lambda: _sync(send_alerts))


@screen
def synchroniser() -> dict:
    """Relance la synchronisation complète (comme le bouton) ; une seule à la fois sur le téléphone."""
    return _sync()


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
