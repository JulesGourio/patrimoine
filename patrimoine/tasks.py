"""Scheduled work: the daily sync, and the publication of the market analyses written by the Claude cloud routines
(claude.ai/code/routines: daily on the previous session, Tuesday to Saturday; weekly on Sunday; see `cloud`).
`analysis` still writes one locally, on demand (Analyses page, `patrimoine analyse`).

The Windows tasks call `uvw` (uv without a console window) on the `patrimoine` commands directly,
with no PowerShell script in between.
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import date
from pathlib import Path

from . import db, pipeline
from .config import ROOT, Settings

DAILY = "Patrimoine - synchronisation"
CLOUD = "Patrimoine - analyses cloud"
REPLACED = ("Patrimoine - rapport hebdo", "Patrimoine - analyse du jour")  # now cloud routines


def claude_exe() -> Path:
    """Claude Code ships inside the VS Code extension; take the newest installed version."""
    found = shutil.which("claude")
    if found:
        return Path(found)
    exts = sorted((Path.home() / ".vscode" / "extensions").glob("anthropic.claude-code-*"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    for ext in exts:
        exe = ext / "resources" / "native-binary" / "claude.exe"
        if exe.exists():
            return exe
    raise FileNotFoundError("Claude Code introuvable")


def analysis(period: str = "jour", settings: Settings | None = None, sync_first: bool = True) -> int:
    """Claude Code writes and publishes the analysis (scripts/analyse.md). The sync runs first unless it
    already ran today (the 7:30 task)."""
    settings = settings or Settings()
    logs = settings.data_dir / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if sync_first:
        con = db.connect(settings.db_path)
        last = (db.get_meta(con, "last_sync") or {}).get("at", "")
        con.close()
        if last[:10] != date.today().isoformat():
            pipeline.run(settings)
    prompt = (ROOT / "scripts" / "analyse.md").read_text(encoding="utf-8").replace("{periode}", period)
    with open(logs / f"analyse-{period}-{date.today().isoformat()}.txt", "a", encoding="utf-8") as out:
        # The prompt goes through stdin, untouched by any shell quoting.
        done = subprocess.run(
            [str(claude_exe()), "-p", "--mcp-config", str(ROOT / ".mcp.json"),
             "--allowedTools", "mcp__patrimoine__*", "WebSearch", "WebFetch"],
            input=prompt, text=True, encoding="utf-8", stdout=out, stderr=subprocess.STDOUT, cwd=ROOT)
    return done.returncode


def remove() -> list[str]:
    """When the phone has taken over the daily sync: remove the PC's tasks, so alerts are not sent twice."""
    out = []
    for name in (DAILY, CLOUD, *REPLACED):
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                            f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        out.append(f"{name} : {'retirée' if r.returncode == 0 else (r.stderr or r.stdout).strip()}")
    return out


def install() -> list[str]:
    uvw = shutil.which("uvw") or shutil.which("uv")
    if not uvw:
        raise FileNotFoundError("uv introuvable")
    jobs = [
        (DAILY, "sync", "New-ScheduledTaskTrigger -Daily -At 7:30"),
        (CLOUD, "cloud", "New-ScheduledTaskTrigger -Once -At 00:05 -RepetitionInterval (New-TimeSpan -Minutes 15)"),
    ]
    out = []
    for name in REPLACED:
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                        f"Unregister-ScheduledTask -TaskName '{name}' -Confirm:$false -ErrorAction SilentlyContinue"],
                       capture_output=True, stdin=subprocess.DEVNULL, timeout=60)
    for name, command, trigger in jobs:
        # schtasks.exe waits on stdin when started from Python; the ScheduledTasks cmdlets do not.
        script = (
            f"$a = New-ScheduledTaskAction -Execute '{uvw}' -Argument 'run --directory \"{ROOT}\" patrimoine {command}'"
            f" -WorkingDirectory '{ROOT}'; "
            "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries"
            " -ExecutionTimeLimit (New-TimeSpan -Hours 1); "
            f"Register-ScheduledTask -TaskName '{name}' -Action $a -Trigger ({trigger}) -Settings $s -Force | Out-Null"
        )
        r = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=60)
        out.append(f"{name} : {'ok' if r.returncode == 0 else (r.stderr or r.stdout).strip()}")
    return out
