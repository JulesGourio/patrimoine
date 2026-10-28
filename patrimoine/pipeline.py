"""Everything the daily task does, in order, each step isolated so one failure does not stop the rest.

1. Trade Republic: resume the saved session; when it has expired, start a login and push a
   notification asking Jules to confirm it in the app (the sync waits up to two minutes).
2. CMB through Enable Banking; a notice when the 180-day consent is about to end.
3. Prices, daily valuation.
4. Other investors: new 13F filings of the followed funds (and how copying them did), new trades of US members
   of Congress (and the automatic selection of the best ones), the fast filings (funds' Form 4 and 13D/13G, ARK's
   daily trades, insiders of the watched companies), the radar; sent as a single digest.
5. The alert rules (spending budgets are recorded, never sent).
"""
from __future__ import annotations

import json
import logging
import time
import traceback
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timezone

import pandas as pd

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


def usd(x: float | None) -> str:
    if x is None:
        return "?"
    return f"{x / 1e6:.1f} M$".replace(".", ",") if x >= 1e6 else f"{x / 1e3:.0f} k$"


def pct(x: float, sign: bool = False) -> str:
    return (f"{x:+.0%}" if sign else f"{x:.1%}").replace(".", ",")


def _investors(con, lines: list[str]) -> list[str]:
    """New 13F filings of the followed funds (at most one check a day), as digest sections."""
    from . import investors
    from .sources import sec13f

    last = db.get_meta(con, "last_13f_check")
    if last and last[:10] == date.today().isoformat():
        return []
    new = sec13f.sync(con)
    investors.update_performance(con)
    lines.append(f"13F : {len(new)} nouvelle(s) déclaration(s)")
    out = []
    for f in new:
        m, _ = investors.portfolio(con, f["cik"])
        m = m[m.put_call == ""]
        moves = m[m.change.isin(["nouvelle", "renforcée", "allégée", "vendue"])]
        moves = moves.assign(v=moves[["value_usd", "value_usd_prev"]].max(axis=1)).sort_values("v", ascending=False)
        total = f"{f['total_usd'] / 1e9:.1f}".replace(".", ",")
        out.append(f"**{f['name']}** (13F au {f['period']}) : {f['positions']} lignes, {total} Md$\n" + "\n".join(
            f"- {r.change} : {r.ticker or r.issuer} ({pct(r.weight)} du portefeuille)" for r in moves.head(6).itertuples()))
    return out


def _congress(con, lines: list[str]) -> list[str]:
    """New trades of US members of Congress; the followed ones (and the largest others) as digest sections.
    The first run imports the whole history quietly."""
    from . import politicians
    from .sources import congress

    last = db.get_meta(con, "last_congress_check")
    if last and last[:10] == date.today().isoformat():
        return []
    first_run = last is None
    res = congress.sync(con)
    congress.update_returns(con)
    politicians.auto_follow(con)
    lines.append(f"Élus américains : {len(res['new'])} nouvelle(s) transaction(s)"
                 + "".join(f" ({e})" for e in res["errors"]))
    if first_run or not res["new"]:
        return []
    t = politicians.trades(con)
    t = t[t.id.isin(res["new"])]
    out = []

    def line(r) -> str:
        perf = (f" · depuis {pct(r.ret, True)} (S&P {pct(r.bench_ret, True)})"
                if pd.notna(r.ret) and pd.notna(r.bench_ret) else "")
        what = "option sur " if r.asset_type == "option" else ""
        amount = f"{usd(r.amount_min)}–{usd(r.amount_max)}" if pd.notna(r.amount_max) else f"plus de {usd(r.amount_min)}"
        title = r.ticker if pd.notna(r.ticker) else r.asset[:45]
        day = pd.Timestamp(r.tx_date).strftime("%d/%m/%y") if pd.notna(r.tx_date) else "?"
        return f"- {r.action} {what}{title} ({str(r.owner).lower()}) · {amount} · le {day}{perf}"

    for _, g in t[t.followed == 1].groupby("politician_id"):
        out.append(f"**{g.name.iloc[0]}** ({g.chamber_label.iloc[0]})\n"
                   + "\n".join(line(r) for r in g.head(10).itertuples()))
    big = t[(t.followed == 0) & (t.amount_min >= 250_000) & t.ticker.notna()].sort_values("amount_min", ascending=False)
    if not big.empty:
        out.append("**Autres grosses transactions d'élus**\n" + "\n".join(
            line(r).replace("- ", f"- {r.name} : ", 1) for r in big.head(8).itertuples()))
    return out


def _fresh(con, lines: list[str]) -> list[str]:
    """The fast filings, once a day: the followed funds' Form 4 and 13D/13G, ARK's daily trades, open-market trades
    of the watched companies' insiders. The first run imports the history quietly."""
    from . import fresh
    from .sources import ownership

    last = db.get_meta(con, "last_ownership_check")
    if last and last[:10] == date.today().isoformat():
        return []
    res = ownership.sync(con, fresh.watchlist(con))
    lines.append(f"Déclarations rapides : {len(res['funds'])} des fonds suivis, {len(res['ark'])} mouvement(s) ARK, "
                 f"{len(res['insiders'])} opération(s) de dirigeants" + "".join(f" ({e})" for e in res["errors"]))
    if last is None:
        return []
    out = []
    new = {f["accession"] for f in res["funds"]}
    m = fresh.fund_moves(con, days=30)
    m = m[m.accession.isin(new) & (m.action != "inchangée")] if not m.empty else m
    if not m.empty:
        out.append("**Fonds suivis : déclarations rapides** (Form 4, 13D/13G)\n" + "\n".join(
            f"- {r.fund} : {r.action} {r.ticker or r.issuer}"
            + (f" · {usd(abs(r.value_usd))}" if pd.notna(r.value_usd) and r.value_usd else "")
            + (f" · {r.pct:.1f} % de la société".replace(".", ",") if pd.notna(r.pct) else "")
            + f" ({r.kind}, le {pd.Timestamp(r.event_date):%d/%m})" for r in m.head(10).itertuples()))
    mine = set(db.get_meta(con, "exposure") or {})
    if res["ark"]:
        a = pd.DataFrame(res["ark"]).groupby("ticker", as_index=False).agg(v=("value_usd", "sum"),
                                                                          change=("change", "first"))
        a = a[(a.v.abs() >= 5e6) | a.ticker.isin(mine)].sort_values("v", key=abs, ascending=False)
        if not a.empty:
            out.append("**ARK Invest aujourd'hui**\n" + "\n".join(
                f"- {'achat' if r.v > 0 else 'vente'} {r.ticker} · {usd(abs(r.v))} ({r.change})"
                for r in a.head(6).itertuples()))
    if res["insiders"]:
        ids = {x["id"] for x in res["insiders"]}
        t = fresh.insider_trades(con, days=30)
        t = fresh.insider_days(t[t.id.isin(ids)]) if not t.empty else t
        if not t.empty:
            t = t[~t.holder & (((t.action == "achat") & (t.value_usd >= 100_000))
                               | ((t.action == "vente") & (t.value_usd >= 5e6) & t.ticker.isin(mine)))]
        if not t.empty:
            out.append("**Dirigeants** (achats sur le marché, grosses ventes sur tes titres)\n" + "\n".join(
                f"- {r.ticker} : {r.action} de {usd(r.value_usd)} par {r.who} ({r.role}), le "
                f"{pd.Timestamp(r.tx_date):%d/%m}" for r in t.head(8).itertuples()))
    return out


def _radar(con, lines: list[str]) -> list[str]:
    """Recompute the radar once a day; report the ideas that just entered its top 5 and the signals on Jules's
    own lines that were not there yesterday."""
    from . import radar

    last = db.get_meta(con, "radar_at")
    if last and last[:10] == date.today().isoformat():
        return []
    r = radar.build(con)
    lines.append(f"Radar : {len(r)} titres")
    if r.empty:
        return []
    top = r.head(5)
    mine = r[r.mine_eur >= 250]  # below that, a stock is a rounding error of an index fund
    before = db.get_meta(con, "radar_seen") or {"top": [], "mine": []}
    db.set_meta(con, "radar_seen", {"top": list(top.ticker), "mine": list(mine.ticker)})
    con.commit()
    out = []
    new_top = top[~top.ticker.isin(before["top"])]
    if before["top"] and not new_top.empty:
        out.append("**Radar : nouvelles idées dans le top 5**\n" + "\n".join(
            f"- {x.ticker} ({x['name']}) : {x.why}" for _, x in new_top.iterrows()))
    new_mine = mine[~mine.ticker.isin(before["mine"])]
    if not new_mine.empty:
        out.append("**Sur tes lignes**\n" + "\n".join(
            f"- {x.ticker} ({x['name']}, {x.mine_eur:.0f} € chez toi via {x.mine_via}) : {x.why}"
            for _, x in new_mine.iterrows()))
    return out


class _Skip(Exception):
    """Step not part of this run."""


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


def run(settings: Settings | None = None, interactive: bool = False, send_alerts: bool = True,
        part: str = "tout") -> list[str]:
    """``part``: ``rapide`` (banks, prices, valuation, alerts: seconds), ``lourd`` (other investors and radar: minutes,
    network-heavy) or ``tout`` (the PC's daily task)."""
    settings = settings or Settings()
    fast, heavy = part in ("rapide", "tout"), part in ("lourd", "tout")
    lines: list[str] = []
    _durations.clear()
    started = time.monotonic()
    with db.session(settings.db_path) as con:
        db.init(con)
        for name, step in ((("Trade Republic", lambda: _trade_republic(settings, con, lines, interactive)),
                            ("CMB", lambda: _cmb(settings, con, lines))) if fast else ()):
            try:
                with _timed(name):
                    step()
            except Exception as e:  # noqa: BLE001 - keep going, report it
                log.error("%s: %s", name, traceback.format_exc())
                lines.append(f"{name} : ÉCHEC — {e}")
                notify.send(f"Synchronisation {name} en échec", str(e)[:300], priority=3, email=False)
            con.commit()  # release the write lock: the app's screens read the database during the sync
        try:
            if not fast:
                raise _Skip
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
        except _Skip:
            pass
        except Exception as e:  # noqa: BLE001
            log.error("valuation: %s", traceback.format_exc())
            lines.append(f"Valorisation : ÉCHEC — {e}")
        # One digest for everything about other investors (funds and members of Congress), not one mail each.
        digest: list[str] = []
        for name, step in (("13F", _investors), ("Élus américains", _congress), ("Déclarations rapides", _fresh),
                           ("Radar", _radar)) if heavy else ():
            try:
                with _timed(name):
                    digest += step(con, lines)
            except Exception as e:  # noqa: BLE001
                log.error("%s: %s", name, traceback.format_exc())
                lines.append(f"{name} : ÉCHEC — {e}")
            con.commit()
        if digest and send_alerts:
            notify.send("Suivi des investisseurs", "\n\n".join(digest), priority=3, tags=["busts_in_silhouette"],
                        markdown_body=True)
        done = {"at": db.now_iso(), "summary": lines, "durations": dict(_durations),
                "total_s": round(time.monotonic() - started, 1)}
        if fast:
            fired = alerts.run(con, send=send_alerts)
            lines.append(f"Alertes : {len(fired)} nouvelle(s)" + "".join(f"\n  - {f.title}" for f in fired))
            done["total_s"] = round(time.monotonic() - started, 1)
        db.set_meta(con, "last_sync" if fast else "last_heavy_sync", done)
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
