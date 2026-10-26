"""Hook PreToolUse : lance `uv run pytest` avant chaque `git commit` et le bloque si un test échoue.

Fonctionne avec l'outil Bash comme avec l'outil PowerShell (Windows).
"""

import json
import os
import re
import subprocess
import sys


def main() -> int:
    try:
        # utf-8-sig : PowerShell peut préfixer l'entrée d'un BOM.
        data = json.loads(sys.stdin.buffer.read().decode("utf-8-sig"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    command = (data.get("tool_input") or {}).get("command") or ""
    if not re.search(r"\bgit\b[^;&|]*\bcommit\b", command):
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or "."
    result = subprocess.run(
        ["uv", "run", "pytest", "-q", "-x"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode == 0:
        return 0
    tail = (result.stdout + result.stderr)[-4000:]
    print(f"Commit bloqué : `uv run pytest` échoue. Corrige avant de committer.\n\n{tail}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
