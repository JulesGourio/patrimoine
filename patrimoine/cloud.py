"""Bridge to the Claude cloud routines (claude.ai/code/routines), which cannot reach this machine.

- ``export`` (end of every sync) force-pushes one commit to the ``donnees`` branch of the private GitHub repo:
  ``jour.json`` and ``semaine.json``, what the MCP tools would have answered. One commit, no history kept there.
- The routine (``scripts/analyse_cloud.md``) reads it, researches, and pushes its analysis as a JSON file to
  ``claude/analyses`` (cloud sessions may only push to ``claude/`` branches).
- ``pull`` (Windows task, every 15 minutes) fetches that branch and publishes the new files: Analyses page, mail,
  push, prepared orders.

Two ways to reach GitHub, same result: the ``git`` command on the PC (its saved credentials), or the GitHub REST
API with a token (`vault` ``github_token``), used whenever the token is set and always on the phone, which has no
git. Blob ids are git's in both cases, so the list of imported files carries over from one to the other.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import threading

import requests

from . import db, notify, vault
from .config import ROOT, Settings

log = logging.getLogger(__name__)

DATA_BRANCH = "donnees"
ANALYSES_BRANCH = "claude/analyses"
ANALYSES_DIR = "cloud/analyses"
DRAFT_DAYS = 7                          # unpublished drafts older than this are dropped
_pull_lock = threading.Lock()  # the phone's sync and its hourly worker may both pull
REPO = os.getenv("PATRIMOINE_GITHUB_REPO") or "JulesGourio/patrimoine"
API = "https://api.github.com"


def _git(*args: str, stdin: str | None = None, timeout: int = 120) -> str:
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    # Bytes, not text: Windows text mode would turn the "\n" of the tree entries into "\r\n".
    done = subprocess.run(["git", *args], cwd=ROOT, input=(stdin or "").encode(), capture_output=True,
                          timeout=timeout, creationflags=flags, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if done.returncode:
        raise RuntimeError(f"git {args[0]} : {(done.stderr or done.stdout).decode(errors='replace').strip()[:300]}")
    return done.stdout.decode().strip()


class GitTransport:
    """The git command line, with the PC's saved credentials."""

    def write_branch(self, branch: str, files: dict[str, str], message: str) -> None:
        entries = [f"100644 blob {_git('hash-object', '-w', '--stdin', stdin=text)}\t{name}"
                   for name, text in files.items()]
        tree = _git("mktree", stdin="\n".join(entries) + "\n")
        commit = _git("commit-tree", tree, "-m", message)
        _git("push", "--force", "origin", f"{commit}:refs/heads/{branch}")

    def list_dir(self, branch: str, folder: str) -> list[tuple[str, str]] | None:
        """[(path, blob id)] under ``folder`` of ``branch``; None when the branch cannot be fetched."""
        ref = f"refs/remotes/origin/{branch}"
        try:
            _git("fetch", "--quiet", "origin", f"+refs/heads/{branch}:{ref}")
        except RuntimeError as e:  # no routine has pushed yet, or no network
            log.info("%s", e)
            return None
        out = []
        for entry in _git("ls-tree", "-r", ref, "--", folder).splitlines():
            meta, path = entry.split("\t", 1)
            out.append((path, meta.split()[2]))
        return out

    def read_blob(self, blob: str) -> str:
        return _git("cat-file", "blob", blob)


class ApiTransport:
    """The GitHub REST API (git data endpoints) with a token: no git needed, works on the phone."""

    def __init__(self, token: str, repo: str = REPO, http: requests.Session | None = None) -> None:
        self.repo = repo
        self.http = http or requests.Session()
        self.http.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                                  "X-GitHub-Api-Version": "2022-11-28"})

    def _call(self, method: str, path: str, ok: tuple[int, ...] = (200, 201), **kw) -> requests.Response:
        r = self.http.request(method, f"{API}/repos/{self.repo}/{path}", timeout=60, **kw)
        if r.status_code not in ok:
            raise RuntimeError(f"GitHub {method} {path} : {r.status_code} {r.text[:200]}")
        return r

    def write_branch(self, branch: str, files: dict[str, str], message: str) -> None:
        tree = self._call("POST", "git/trees", json={"tree": [
            {"path": name, "mode": "100644", "type": "blob", "content": text} for name, text in files.items()]})
        commit = self._call("POST", "git/commits", json={"message": message, "tree": tree.json()["sha"],
                                                        "parents": []}).json()["sha"]
        r = self._call("PATCH", f"git/refs/heads/{branch}", ok=(200, 404, 422), json={"sha": commit, "force": True})
        if r.status_code != 200:  # the branch does not exist yet
            self._call("POST", "git/refs", json={"ref": f"refs/heads/{branch}", "sha": commit})

    def list_dir(self, branch: str, folder: str) -> list[tuple[str, str]] | None:
        """None when the branch is missing or GitHub cannot be reached (offline, token expired): next time."""
        try:
            ref = self._call("GET", f"git/ref/heads/{branch}", ok=(200, 404, 409))
            if ref.status_code != 200:
                log.info("GitHub : branche %s absente (%s)", branch, ref.status_code)
                return None
            head = self._call("GET", f"git/commits/{ref.json()['object']['sha']}").json()
            r = self._call("GET", f"git/trees/{head['tree']['sha']}", params={"recursive": "1"})
        except (requests.RequestException, RuntimeError) as e:
            log.info("GitHub injoignable : %s", e)
            return None
        prefix = folder.rstrip("/") + "/" if folder else ""
        return [(e["path"], e["sha"]) for e in r.json().get("tree", [])
                if e.get("type") == "blob" and e["path"].startswith(prefix)]

    def read_blob(self, blob: str) -> str:
        data = self._call("GET", f"git/blobs/{blob}").json()
        return base64.b64decode(data["content"]).decode("utf-8")


def transport() -> GitTransport | ApiTransport:
    token = vault.get("github_token")
    return ApiTransport(token) if token else GitTransport()


def dossier(period: str) -> dict:
    """What the routine needs for one period, under the names of the MCP tools scripts/analyse.md refers to."""
    from . import api as tools

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
    files = {f"{period}.json": json.dumps(dossier(period), ensure_ascii=False, indent=1, default=str)
             for period in briefing.PERIODS}
    transport().write_branch(DATA_BRANCH, files, f"Données du {db.now_iso()[:10]}")
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
        from . import api as tools

        try:
            orders += "erreur" not in tools.preparer_ordre(**o)
        except TypeError as e:
            log.error("ordre ignoré : %s", e)
    return f"analyse {bid} publiée ({row['kind']}, séance du {row['session']})" + (f", {orders} ordre(s) préparé(s)"
                                                                                 if orders else "")


def pull(settings: Settings | None = None) -> list[str]:
    """Publish the new analyses; one pull at a time, so a file is never published twice."""
    with _pull_lock:
        return _pull(settings or Settings())


def _pull(settings: Settings) -> list[str]:
    git = transport()
    listing = git.list_dir(ANALYSES_BRANCH, ANALYSES_DIR)
    if listing is None:
        return []
    out = []
    with db.session(settings.db_path) as con:
        db.init(con)
        seen = set(db.get_meta(con, "cloud_imported") or [])
        for path, blob in listing:
            if blob in seen or not path.endswith(".json"):
                continue
            try:
                line = _publish(con, json.loads(git.read_blob(blob)))
            except Exception as e:  # noqa: BLE001 - one bad file must not block the next ones
                line = f"{path} illisible : {e}"
            if "publiée" not in line:
                notify.send("Analyse cloud non publiée", line[:300], priority=3, email=False)
            out.append(line)
            seen.add(blob)
            db.set_meta(con, "cloud_imported", sorted(seen))
            con.commit()
    return out
