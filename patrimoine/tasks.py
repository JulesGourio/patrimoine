"""Scheduled work: the daily sync and the market analyses written by Claude Code (daily on the previous session,
Tuesday to Saturday; weekly on Sunday).

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
WEEKLY = "Patrimoine - rapport hebdo"
BRIEF = "Patrimoine - analyse du jour"


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


def install() -> list[str]:
    uvw = shutil.which("uvw") or shutil.which("uv")
    if not uvw:
        raise FileNotFoundError("uv introuvable")
    jobs = [
        (DAILY, "sync", "New-ScheduledTaskTrigger -Daily -At 7:30"),
        (WEEKLY, "rapport", "New-ScheduledTaskTrigger -Weekly -DaysOfWeek Sunday -At 18:00"),
        (BRIEF, "analyse", "New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Wednesday,Thursday,Friday,Saturday"
                           " -At 8:00"),
    ]
    out = []
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
