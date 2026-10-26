import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "hook", Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "tests_avant_commit.py")
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

G = "git"  # keeps these lines from looking like commands to the hook itself


def test_detects_commit_commands():
    for cmd in (f"{G} commit -m x", f"{G} add -A && {G} commit -m x", f"{G} -C /a/b commit -q", f"cd x; {G} commit",
                f"(cd x && {G} commit)"):
        assert hook.COMMIT.search(cmd), cmd


def test_ignores_the_words_elsewhere():
    for cmd in (f"{G} status", f"echo {G} commit", f'r = call("GET", f"{G}/ref") commit = 1', f"{G} log --grep commit"):
        assert not hook.COMMIT.search(cmd), cmd
