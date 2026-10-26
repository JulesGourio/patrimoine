"""Files Jules brings in by hand, the same way from the command line (a folder such as Downloads) and from the
mobile app (a file picked on the phone): Amundi statements (PEG), CMB CSV exports, savings balances, and the
whole database (moving it from the PC to the phone, or back).
"""
from __future__ import annotations

import shutil
import sqlite3
import urllib.parse
from datetime import date, datetime
from pathlib import Path

from . import db
from .config import Settings


def _copy_new(files: list[Path], folder: Path) -> list[str]:
    """Copy the files not already there (same name and size); returns the names copied."""
    folder.mkdir(parents=True, exist_ok=True)
    done = []
    for f in files:
        target = folder / f.name
        if not target.exists() or target.stat().st_size != f.stat().st_size:
            shutil.copyfile(f, target)
            done.append(f.name)
    return done


def peg(settings: Settings, files: list[Path] = ()) -> dict:
    """Copy new Amundi statements (AVO*.pdf), then rebuild the PEG from all of them."""
    import pandas as pd

    from . import sync
    from .prices import history
    from .sources import amundi

    folder = settings.data_dir / "raw" / "amundi"
    copied = _copy_new([Path(f) for f in files], folder)
    statements = amundi.load(folder)
    if not statements:
        raise ValueError(f"Aucun relevé Amundi dans {folder}")
    closes, _ = history("AIR.PA", date.fromisoformat(min(s.date for s in statements)) - pd.Timedelta(days=10))
    rows, summary = amundi.rows(statements, lambda d: float(closes.asof(pd.Timestamp(d))) if len(closes) else None)
    with db.session(settings.db_path) as con:
        db.init(con)
        new, updated = sync.import_rows(con, rows, amundi.raw_json)
        con.execute("UPDATE positions SET quantity = ?, as_of = ?, source = 'amundi' WHERE account_id = 'peg_airbus'",
                    (summary["total_actions"], summary["as_of"]))
        db.set_meta(con, "peg_summary", summary)
    return {"copies": copied, "releves": len(statements), "nouvelles": new, "mises_a_jour": updated,
            "actions": summary["total_actions"], "au": summary["as_of"], "esop": summary["esop_events"]}


def cmb_csv(settings: Settings, files: list[Path] = ()) -> dict[str, tuple[int, int, str, str]]:
    """Copy new CMB exports (RELEVE_*.csv), then import all of them: {account: (new, updated, first, last)}."""
    from . import sync

    folder = settings.data_dir / "raw" / "cmb_csv"
    folder.mkdir(parents=True, exist_ok=True)
    for f in map(Path, files):
        if not (folder / f.name).exists():
            shutil.copyfile(f, folder / f.name)
    with db.session(settings.db_path) as con:
        db.init(con)
        return sync.import_cmb_csv(con, sorted(folder.glob("RELEVE_*.csv")))


def balance(settings: Settings, account: str, euros: str | float, day: str | None = None) -> int:
    """Record the balance of an account the bank feeds do not cover (savings); returns it in cents."""
    cents = round(float(str(euros).replace(" ", "").replace(",", ".")) * 100)
    with db.session(settings.db_path) as con:
        db.init(con)
        if not con.execute("SELECT 1 FROM accounts WHERE id = ?", (account,)).fetchone():
            raise ValueError(f"Compte inconnu : {account}")
        db.set_balance(con, account, day or date.today().isoformat(), cents)
    return cents


def backup(settings: Settings, dest: Path) -> Path:
    """A consistent copy of the database, even while a sync writes to it (SQLite backup API)."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    src = db.connect(settings.db_path)
    out = sqlite3.connect(dest)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    return dest


def _readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{urllib.parse.quote(Path(path).as_posix())}?mode=ro", uri=True)


def check_database(path: Path) -> dict:
    """Refuse anything but a Patrimoine database; returns what it holds."""
    try:
        con = _readonly(path)
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("base endommagée")
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if not {"accounts", "transactions", "meta"} <= tables:
                raise ValueError("ce n'est pas une base Patrimoine")
            n = con.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
            last = con.execute("SELECT MAX(date) FROM transactions").fetchone()[0]
        finally:
            con.close()
    except sqlite3.DatabaseError as e:
        raise ValueError(f"fichier illisible : {e}") from None
    return {"operations": n, "derniere_operation": last}


def database(settings: Settings, path: Path) -> dict:
    """Replace the database with another copy (the PC's, typically). The current one is kept next to it as
    ``patrimoine-avant-import-<date>.db`` (one per import, never overwritten)."""
    info = check_database(path)
    current = settings.db_path
    current.parent.mkdir(parents=True, exist_ok=True)
    if current.exists():
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        backup(settings, current.with_name(f"patrimoine-avant-import-{stamp}.db"))
    tmp = current.with_name("patrimoine-import.tmp")
    src = _readonly(path)
    out = sqlite3.connect(tmp)
    try:
        src.backup(out)
    finally:
        out.close()
        src.close()
    for leftover in (current.with_name(current.name + "-wal"), current.with_name(current.name + "-shm")):
        leftover.unlink(missing_ok=True)
    tmp.replace(current)
    with db.session(current) as con:  # bring an older copy up to the current schema
        db.init(con)
    return info
