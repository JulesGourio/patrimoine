from __future__ import annotations

import argparse
import getpass
import json
import sys

from . import db, vault
from .config import Settings


def cmd_init(args: argparse.Namespace, settings: Settings) -> None:
    with db.session(settings.db_path) as con:
        db.init(con)
        n = con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    print(f"Base prête : {settings.db_path} ({n} comptes)")


def cmd_accounts(args: argparse.Namespace, settings: Settings) -> None:
    with db.session(settings.db_path) as con:
        for a in con.execute("SELECT id, institution, name, kind, source FROM accounts ORDER BY institution, id"):
            print(f"{a['id']:<18} {a['institution']:<7} {a['name']:<18} {a['kind']:<8} {a['source']}")


def cmd_secret(args: argparse.Namespace, settings: Settings) -> None:
    if args.action == "list":
        for name, what in vault.KNOWN.items():
            state = "défini" if vault.get(name) else "absent"
            print(f"{name:<14} {state:<7} {what}")
        return
    if not args.name:
        raise SystemExit("Nom du secret manquant (voir `patrimoine secret list`).")
    if args.action == "set":
        vault.set(args.name, getpass.getpass(f"{vault.KNOWN.get(args.name, args.name)} : "))
        print("Enregistré dans le gestionnaire d'identifiants Windows.")
    elif args.action == "delete":
        vault.delete(args.name)
        print("Supprimé.")


def cmd_tr(args: argparse.Namespace, settings: Settings) -> None:
    from . import sync
    from .sources import tr_parse, trade_republic

    try:
        if args.action == "login":
            trade_republic.connect(settings, interactive=True)
            print("Connecté ; la session est gardée pour les prochaines synchronisations.")
            return
        if args.action == "sync":
            path = trade_republic.dump(settings, interactive=True)
        else:  # import: the latest raw dump, without calling Trade Republic
            dumps = sorted((settings.data_dir / "raw" / "tr").glob("*.json"))
            if not dumps:
                raise SystemExit("Aucune donnée brute : lance `patrimoine tr sync`.")
            path = dumps[-1]
    except trade_republic.LoginRequired as e:
        raise SystemExit(str(e)) from None
    parsed = tr_parse.parse(json.loads(path.read_text(encoding="utf-8")))
    with db.session(settings.db_path) as con:
        db.init(con)
        report = sync.import_trade_republic(con, parsed, as_of=path.stem)
    print(f"Trade Republic ({path.name}) : " + "\n".join(report.lines()))


def cmd_history(args: argparse.Namespace, settings: Settings) -> None:
    from . import portfolio, prices

    with db.session(settings.db_path) as con:
        db.init(con)
        if not args.sans_prix:
            for isin, got in prices.update(con).items():
                print(f"  {isin} : {got}")
        df, book = portfolio.valuations(con)
        portfolio.store(con, df)
        last = df[df.date == df.date.max()].set_index("account_id")
        print(f"Historique reconstruit du {df.date.min()} au {df.date.max()} :")
        for acc, r in last.iterrows():
            print(f"  {acc:<11} espèces {r.cash:>10.2f}  titres {r.securities:>10.2f}  coût {r.cost:>10.2f}"
                  f"  +/- réalisées {r.realised:>9.2f}")
        for year, t in portfolio.tax_summary(con, book).items():
            print(f"  {year} (compte-titres) : " + ", ".join(f"{k} {v:.2f}" for k, v in t.items()))


def main(argv: list[str] | None = None) -> None:
    # Windows opens stdout/stderr in the legacy console codepage, which mangles accents.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except ValueError:
                pass
    parser = argparse.ArgumentParser(prog="patrimoine")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="Créer la base et les comptes").set_defaults(func=cmd_init)
    sub.add_parser("comptes", help="Lister les comptes").set_defaults(func=cmd_accounts)
    p = sub.add_parser("secret", help="Gérer les secrets (PIN, jetons)")
    p.add_argument("action", choices=["list", "set", "delete"])
    p.add_argument("name", nargs="?")
    p.set_defaults(func=cmd_secret)
    p = sub.add_parser("tr", help="Trade Republic")
    p.add_argument("action", choices=["login", "sync", "import"])
    p.set_defaults(func=cmd_tr)
    p = sub.add_parser("historique", help="Cours, valorisation quotidienne et plus-values")
    p.add_argument("--sans-prix", action="store_true", help="Ne pas retélécharger les cours")
    p.set_defaults(func=cmd_history)
    args = parser.parse_args(argv)
    args.func(args, Settings())


if __name__ == "__main__":
    main()
