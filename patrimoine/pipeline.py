"""Everything the daily task does, in order, each step isolated so one failure does not stop the rest.

1. Trade Republic: resume the saved session; when it has expired, start a login and push a
   notification asking Jules to confirm it in the app (the sync waits up to two minutes).
2. CMB through Enable Banking; a notice when the 180-day consent is about to end.
3. Prices, daily valuation.
4. The alert rules (spending budgets are recorded, never sent).
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timezone

from . import alerts, db, notify, portfolio, prices, sync
from .config import Settings

log = logging.getLogger(__name__)


def _trade_republic(settings: Settings, con, lines: list[str], interactive: bool) -> None:
    from .sources import tr_parse, trade_republic

    try:
        path = trade_republic.dump(settings, interactive=False)
    except trade_republic.LoginRequired:
        notify.send("Trade Republic : confirme la connexion",
                    "La synchronisation du jour attend ta confirmation dans l'appli Trade Republic (2 min).",
                    priority=4, email=False)
        path = trade_republic.dump(settings, interactive=True)
    dump = json.loads(path.read_text(encoding="utf-8"))
    report = sync.import_trade_republic(con, tr_parse.parse(dump), as_of=path.stem,
                                        owner=(dump.get("account") or {}).get("name"))
    lines += ["Trade Republic : " + " / ".join(report.lines())]
    if report.unknown:
        notify.send("Trade Republic a changé un format", report.lines()[-1], priority=3, email=True)


def _cmb(settings: Settings, con, lines: list[str]) -> None:
    from .sources import enable_banking as eb

    path = eb.dump(settings)
    report = sync.import_cmb(con, json.loads(path.read_text(encoding="utf-8")))
    lines.append("CMB : " + " / ".join(report.lines()))
    until = db.get_meta(con, "cmb_consent_until")
    if until:
        left = (datetime.fromisoformat(until) - datetime.now(timezone.utc)).days
        if left <= 14 and db.get_meta(con, "cmb_consent_warned") != until:
            notify.send("Accès CMB bientôt expiré", f"L'accès aux comptes CMB expire dans {left} jours : "
                        "demande à Claude de le renouveler.", priority=4)
            db.set_meta(con, "cmb_consent_warned", until)


_durations: dict[str, float] = {}  # step -> seconds, of the sync in progress


@contextmanager
def _timed(name: str) -> Generator[None]:
    start = time.monotonic()
    try:
        yield
    finally:
        took = time.monotonic() - start
        _durations[name] = round(took, 1)
        log.info("%s : %.1f s", name, took)


def run(settings: Settings | None = None, interactive: bool = False, send_alerts: bool = True) -> list[str]:
    """Banks, prices, valuation, alerts (the PC's daily task and the phone's sync)."""
    settings = settings or Settings()
    lines: list[str] = []
    _durations.clear()
    started = time.monotonic()
    with db.session(settings.db_path) as con:
        db.init(con)
        for name, step in (("Trade Republic", lambda: _trade_republic(settings, con, lines, interactive)),
                           ("CMB", lambda: _cmb(settings, con, lines))):
            try:
                with _timed(name):
                    step()
            except Exception as e:  # noqa: BLE001 - keep going, report it
                log.error("%s: %s", name, traceback.format_exc())
                lines.append(f"{name} : ÉCHEC — {e}")
                notify.send(f"Synchronisation {name} en échec", str(e)[:300], priority=3, email=False)
            con.commit()  # release the write lock: the app's screens read the database during the sync
        try:
            got = prices.update(con)
            missing = [i for i, v in got.items() if "aucune" in v]
            lines.append(f"Cours : {len(got) - len(missing)} titres à jour" + (f", {len(missing)} sans cotation"
                                                                             if missing else ""))
            df, _ = portfolio.valuations(con)
            portfolio.store(con, df)
            last = df[df.date == df.date.max()]
            con.commit()
            lines.append(f"Patrimoine au {df.date.max()} : {(last.cash + last.securities).sum():,.0f} €"
                         .replace(",", " "))
        except Exception as e:  # noqa: BLE001
            log.error("valuation: %s", traceback.format_exc())
            lines.append(f"Valorisation : ÉCHEC — {e}")
        done = {"at": db.now_iso(), "summary": lines, "durations": dict(_durations),
                "total_s": round(time.monotonic() - started, 1)}
        fired = alerts.run(con, send=send_alerts)
        lines.append(f"Alertes : {len(fired)} nouvelle(s)" + "".join(f"\n  - {f.title}" for f in fired))
        done["total_s"] = round(time.monotonic() - started, 1)
        db.set_meta(con, "last_sync", done)
    # The export to the cloud routines (branch ``donnees``) is gone: the analyses are on demand now, and a push to
    # GitHub in every sync cost seconds (and minutes when the network was bad).
    return lines


def main() -> None:
    settings = Settings()
    logdir = settings.data_dir / "logs"
    logdir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=logdir / f"sync-{date.today().isoformat()}.log", level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s", encoding="utf-8")
    for line in run(settings):
        log.info(line)
        print(line)
