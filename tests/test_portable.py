"""The engine must run on the phone, where the PC-only libraries are absent."""
import subprocess
import sys
import textwrap

PC_ONLY = ["mcp", "keyring", "matplotlib"]
ENGINE = ["api", "mobile", "pipeline", "sync", "cloud", "imports", "briefing", "brief_mail", "alerts", "radar",
          "fresh", "politicians", "investors", "portfolio", "queries", "analytics", "notify", "vault",
          "sources.trade_republic", "sources.enable_banking", "sources.amundi", "sources.cmb_csv",
          "sources.congress", "sources.ownership", "sources.sec13f"]


def test_engine_imports_without_pc_only_libraries():
    code = textwrap.dedent(f"""
        import importlib, importlib.abc, sys

        class Block(importlib.abc.MetaPathFinder):
            def find_spec(self, name, path=None, target=None):
                if name.split(".")[0] in {PC_ONLY!r}:
                    raise ImportError("absent sur le téléphone : " + name)

        sys.meta_path.insert(0, Block())
        for m in {ENGINE!r}:
            importlib.import_module("patrimoine." + m)
    """)
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
