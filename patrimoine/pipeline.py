"""Everything the daily task does, in order, each step isolated so one failure does not stop the rest.

1. Trade Republic: resume the saved session; when it has expired, start a login and push a
   notification asking Jules to confirm it in the app (the sync waits up to two minutes).
2. CMB through Enable Banking; a notice when the 180-day consent is about to end.
3. Prices, daily valuation, then the alert rules.
"""
from __future__ import annotations

import json
import logging
import traceback
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


def _investors(con, lines: list[str], send: bool) -> None:
    """New 13F filings of the followed investors: at most one check a day, one notification per filing."""
    from . import investors
    from .sources import sec13f

    last = db.get_meta(con, "last_13f_check")
    if last and last[:10] == date.today().isoformat():
        return
    new = sec13f.sync(con)
    lines.append(f"13F : {len(new)} nouvelle(s) déclaration(s)")
    for f in new if send else []:
        m, meta = investors.portfolio(con, f["cik"])
        m = m[m.put_call == ""]
        moves = m[m.change.isin(["nouvelle", "renforcée", "allégée", "vendue"])]
        moves = moves.assign(v=moves[["value_usd", "value_usd_prev"]].max(axis=1)).sort_values("v", ascending=False)
        text = "
".join(f"- {r.change} : {r.ticker or r.issuer} ({r.weight:.1%} du portefeuille)" for r in
                         moves.head(8).itertuples())
        notify.send(f"13F {f['name']} ({f['period']})", f"Nouvelle déclaration, {f['positions']} lignes, "
                    f"{f['total_usd'] / 1e9:.1f} Md$.
Principaux mouvements :
{text}", priority=3)


def run(settings: Settings | None = None, interactive: bool = False, send_alerts: bool = True) -> list[str]:
    settings = settings or Settings()
    lines: list[str] = []
    with db.session(settings.db_path) as con:
        db.init(con)
        for name, step in (("Trade Republic", lambda: _trade_republic(settings, con, lines, interactive)),
                           ("CMB", lambda: _cmb(settings, con, lines))):
            try:
                step()
            except Exception as e:  # noqa: BLE001 - keep going, report it
                log.error("%s: %s", name, traceback.format_exc())
                lines.append(f"{name} : ÉCHEC — {e}")
                notify.send(f"Synchronisation {name} en échec", str(e)[:300], priority=3, email=False)
        try:
            got = prices.update(con)
            missing = [i for i, v in got.items() if "aucune" in v]
            lines.append(f"Cours : {len(got) - len(missing)} titres à jour" + (f", {len(missing)} sans cotation"
                                                                             if missing else ""))
            df, _ = portfolio.valuations(con)
            portfolio.store(con, df)
            last = df[df.date == df.date.max()]
            lines.append(f"Patrimoine au {df.date.max()} : {(last.cash + last.securities).sum():,.0f} €"
                         .replace(",", " "))
        except Exception as e:  # noqa: BLE001
            log.error("valuation: %s", traceback.format_exc())
            lines.append(f"Valorisation : ÉCHEC — {e}")
        try:
            _investors(con, lines, send_alerts)
        except Exception as e:  # noqa: BLE001
            log.error("13F: %s", traceback.format_exc())
            lines.append(f"13F : ÉCHEC — {e}")
        fired = alerts.run(con, send=send_alerts)
        lines.append(f"Alertes : {len(fired)} nouvelle(s)" + "".join(f"\n  - {f.title}" for f in fired))
        db.set_meta(con, "last_sync", {"at": db.now_iso(), "summary": lines})
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
