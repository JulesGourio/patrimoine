"""Bridge to the Claude cloud routines (claude.ai/code/routines), which cannot reach this machine.

- ``export`` (end of every sync) force-pushes one commit to the ``donnees`` branch of the private GitHub repo:
  ``jour.json`` and ``semaine.json``, what the MCP tools would have answered. One commit, no history kept there.
- The routine (``scripts/analyse_cloud.md``) reads it, researches, and pushes its analysis as a JSON file to
  ``claude/analyses`` (cloud sessions may only push to ``claude/`` branches).
- ``pull`` (Windows task, every 15 minutes) fetches that branch and publishes the new files: Analyses page, mail,
  push, prepared orders.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess

from . import db, notify
from .config import ROOT, Settings

log = logging.getLogger(__name__)

DATA_BRANCH = "donnees"
ANALYSES_BRANCH = "claude/analyses"
ANALYSES_DIR = "cloud/analyses"
DRAFT_DAYS = 7                          # unpublished drafts older than this are dropped


def _git(*args: str, stdin: str | None = None, timeout: int = 120) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Bytes, not text: Windows text mode would turn the "\n" of the tree entries into "\r\n".
    done = subprocess.run(["git", *args], cwd=ROOT, input=(stdin or "").encode(), capture_output=True,
                          timeout=timeout, creationflags=flags, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if done.returncode:
        raise RuntimeError(f"git {args[0]} : {(done.stderr or done.stdout).decode(errors='replace').strip()[:300]}")
    return done.stdout.decode().strip()


def dossier(period: str) -> dict:
    """What the routine needs for one period, under the names of the MCP tools scripts/analyse.md refers to."""
    from . import mcp_server as tools

    f = tools.faits_du_jour(period)
    doc = {"exporte_le": db.now_iso(), "periode": period, "id": f["id"], "faits_du_jour": f["faits"],
           "analyses": tools.analyses(3), "ordres_proposes": tools.ordres_proposes(), "radar": tools.radar(15)}
    if period == "semaine":
        doc |= {"patrimoine": tools.patrimoine(), "fiscalite": tools.fiscalite(), "positions": tools.positions()}
    return doc


def export(settings: Settings | None = None) -> str:
    from . import briefing

    settings = settings or Settings()
    with db.session(settings.db_path) as con:
        con.executescript(briefing.SCHEMA)
        con.execute("DELETE FROM briefings WHERE analysis IS NULL AND substr(created_at, 1, 10) < date('now', ?)",
                    (f"-{DRAFT_DAYS} day",))
    entries = []
    for period in briefing.PERIODS:
        text = json.dumps(dossier(period), ensure_ascii=False, indent=1, default=str)
        blob = _git("hash-object", "-w", "--stdin", stdin=text)
        entries.append(f"100644 blob {blob}\t{period}.json")
    tree = _git("mktree", stdin="\n".join(entries) + "\n")
    commit = _git("commit-tree", tree, "-m", f"Données du {db.now_iso()[:10]}")
    _git("push", "--force", "origin", f"{commit}:refs/heads/{DATA_BRANCH}")
    return f"Cloud : données exportées ({DATA_BRANCH})"


def _publish(con, doc: dict) -> str:
    from . import briefing

    bid = int(doc["id"])
    row = con.execute("SELECT kind, session, facts, analysis FROM briefings WHERE id = ?", (bid,)).fetchone()
    if not row:
        return f"analyse {bid} : brouillon introuvable (export trop ancien)"
    if row["analysis"]:  # a second run on the same facts: keep both
        bid = con.execute("INSERT INTO briefings (created_at, kind, session, facts) VALUES (?, ?, ?, ?)",
                          (db.now_iso(), row["kind"], row["session"], row["facts"])).lastrowid
        con.commit()
    res = briefing.publish(con, bid, doc.get("analyse") or {})
    if res.get("erreurs"):
        return f"analyse {bid} refusée : " + " ; ".join(res["erreurs"][:5])
    orders = 0
    for o in doc.get("ordres") or []:
        from . import mcp_server as tools

        try:
            orders += "erreur" not in tools.preparer_ordre(**o)
        except TypeError as e:
            log.error("ordre ignoré : %s", e)
    return f"analyse {bid} publiée ({row['kind']}, séance du {row['session']})" + (f", {orders} ordre(s) préparé(s)"
                                                                                 if orders else "")


def pull(settings: Settings | None = None) -> list[str]:
    settings = settings or Settings()
    ref = f"refs/remotes/origin/{ANALYSES_BRANCH}"
    try:
        _git("fetch", "--quiet", "origin", f"+refs/heads/{ANALYSES_BRANCH}:{ref}")
    except RuntimeError as e:  # no routine has pushed yet, or no network
        log.info("%s", e)
        return []
    listing = _git("ls-tree", "-r", ref, "--", ANALYSES_DIR)
    out = []
    with db.session(settings.db_path) as con:
        db.init(con)
        seen = set(db.get_meta(con, "cloud_imported") or [])
        for entry in listing.splitlines():
            meta, path = entry.split("\t", 1)
            blob = meta.split()[2]
            if blob in seen or not path.endswith(".json"):
                continue
            try:
                line = _publish(con, json.loads(_git("cat-file", "blob", blob)))
            except Exception as e:  # noqa: BLE001 - one bad file must not block the next ones
                line = f"{path} illisible : {e}"
            if "publiée" not in line:
                notify.send("Analyse cloud non publiée", line[:300], priority=3, email=False)
            out.append(line)
            seen.add(blob)
            db.set_meta(con, "cloud_imported", sorted(seen))
            con.commit()
    return out
