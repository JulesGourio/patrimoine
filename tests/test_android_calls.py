"""Every engine call the Android screens make must exist, with parameters the function accepts.

The Kotlin side names tools by string (`rememberCall("positions")`, `Engine.call("categoriser", args(...))`): a typo
would only show on the phone. This reads the Kotlin sources and checks each name and argument against
`api.TOOLS` and `mobile.SCREENS`.
"""
import inspect
import re
from pathlib import Path

from patrimoine import api, mobile

ROOT = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "java"
# Engine.call / rememberCall, and the screens' own one-line helpers around Engine.call (e.g. `appeler`).
CALL = re.compile(r'\b(?:rememberCall|Engine\.call|appeler)\(\s*"([a-z_]+)"', re.S)
ARG = re.compile(r'"([a-z_]+)"\s+to\b')


def functions() -> dict:
    return {f.__name__: f for f in api.TOOLS} | dict(mobile.SCREENS)


def calls() -> list[tuple[str, str, set[str]]]:
    """(where, name, keyword arguments written as `"k" to v` inside the call)."""
    out = []
    for path in sorted(ROOT.rglob("*.kt")):
        text = path.read_text(encoding="utf-8")
        for m in CALL.finditer(text):
            depth, end = 1, m.end()
            while end < len(text) and depth:
                depth += {"(": 1, ")": -1}.get(text[end], 0)
                end += 1
            line = text.count("\n", 0, m.start()) + 1
            out.append((f"{path.name}:{line}", m.group(1), set(ARG.findall(text[m.end():end]))))
    return out


def test_the_screens_make_calls():
    assert len(calls()) >= 20


def test_every_call_names_an_engine_function_with_valid_arguments():
    known = functions()
    problems = []
    for where, name, args in calls():
        fn = known.get(name)
        if fn is None:
            problems.append(f"{where} : {name} inconnu")
            continue
        params = set(inspect.signature(fn).parameters)
        if args - params:
            problems.append(f"{where} : {name} n'a pas de paramètre {sorted(args - params)}")
    assert not problems, "\n".join(problems)
