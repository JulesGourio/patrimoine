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
        owner = (json.loads(path.read_text(encoding="utf-8")).get("account") or {}).get("name")
        report = sync.import_trade_republic(con, parsed, as_of=path.stem, owner=owner)
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


def cmd_cmb(args: argparse.Namespace, settings: Settings) -> None:
    from pathlib import Path

    from .sources import enable_banking as eb

    try:
        if args.action == "cle":
            if not args.chemin:
                raise SystemExit("Donne le chemin du fichier .pem téléchargé.")
            app_id = eb.install_key(settings, Path(args.chemin).expanduser())
            print(f"Clé de l'application {app_id[:8]}… rangée dans {eb.key_dir(settings)}")
        elif args.action == "connect":
            print("Ouvre ce lien, connecte-toi à la CMB et valide l'accès à tes comptes :\n")
            print(eb.start_consent(settings))
            print("\nLe navigateur finira sur une page introuvable (https://localhost/patrimoine?…) : c'est normal.")
            accounts = eb.finish_consent(settings, input("Colle ici l'adresse complète de cette page : "))
            print(f"Connecté : {len(accounts)} compte(s).")
        else:
            from . import sync

            if args.action == "sync":
                path = eb.dump(settings)
            else:  # import: every raw dump, oldest first (the bank only serves ~13 months)
                path = None
            dumps = sorted((settings.data_dir / "raw" / "cmb").glob("*.json"))
            with db.session(settings.db_path) as con:
                db.init(con)
                for p in dumps if path is None else [path]:
                    report = sync.import_cmb(con, json.loads(p.read_text(encoding="utf-8")))
                    print(f"CMB ({p.name}) : " + "\n".join(report.lines()))
    except eb.ConsentRequired as e:
        raise SystemExit(str(e)) from None


def cmd_balance(args: argparse.Namespace, settings: Settings) -> None:
    from . import imports

    try:
        imports.balance(settings, args.compte, args.montant, args.date)
    except ValueError as e:
        raise SystemExit(f"{e} (voir `patrimoine comptes`)") from None
    print(f"Solde de {args.compte} enregistré : {args.montant} €")


def cmd_sync(args: argparse.Namespace, settings: Settings) -> None:
    from . import pipeline

    for line in pipeline.run(settings, send_alerts=not args.sans_alertes):
        print(line)


def cmd_alerts(args: argparse.Namespace, settings: Settings) -> None:
    from . import alerts

    with db.session(settings.db_path) as con:
        db.init(con)
        if args.action == "ajouter":
            con.execute("INSERT INTO alert_rules (kind, isin, target, threshold, window_days, note)"
                        " VALUES (?, ?, ?, ?, ?, ?)", (args.type, args.isin, args.categorie, args.seuil,
                                                       args.jours, args.note))
            print("Règle ajoutée.")
        elif args.action == "tester":
            from . import notify

            ok = notify.send("Test Patrimoine", "Les notifications fonctionnent.", email=args.mail)
            print("Envoyée." if ok else "Échec de l'envoi.")
        else:
            alerts.seed(con)
            for r in con.execute("SELECT id, kind, isin, target, threshold, window_days, active, note FROM alert_rules"):
                print(dict(r))


def cmd_report(args: argparse.Namespace, settings: Settings) -> None:
    from . import tasks

    raise SystemExit(tasks.analysis("semaine", settings, sync_first=not args.sans_sync))


def cmd_analysis(args: argparse.Namespace, settings: Settings) -> None:
    from . import tasks

    raise SystemExit(tasks.analysis("jour", settings, sync_first=not args.sans_sync))


def cmd_cloud(args: argparse.Namespace, settings: Settings) -> None:
    from . import cloud

    for line in ([cloud.export(settings)] if args.action == "export" else cloud.pull(settings)):
        print(line)


def cmd_app(args: argparse.Namespace, settings: Settings) -> None:
    """Open the dashboard; start it first unless it is already running."""
    import socket
    import subprocess
    import sys
    import webbrowser

    from .config import ROOT

    url = "http://localhost:8501"
    with socket.socket() as s:
        running = s.connect_ex(("127.0.0.1", 8501)) == 0
    if running:
        webbrowser.open(url)
        print(f"Tableau de bord déjà lancé : {url}")
        return
    print(f"Tableau de bord sur {url} (Ctrl+C pour l'arrêter)")
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(ROOT / "streamlit_app.py"),
                    "--server.port", "8501", "--server.headless", "false"], cwd=ROOT)


def cmd_tasks(args: argparse.Namespace, settings: Settings) -> None:
    from . import tasks

    for line in tasks.install():
        print(line)


def cmd_peg(args: argparse.Namespace, settings: Settings) -> None:
    from pathlib import Path

    from . import imports

    files = sorted(Path(args.dossier).expanduser().glob("AVO*.pdf")) if args.dossier else []
    try:
        r = imports.peg(settings, files)
    except ValueError as e:
        raise SystemExit(str(e)) from None
    print(f"{r['releves']} relevés, {r['nouvelles']} nouvelles opérations, {r['mises_a_jour']} mises à jour : "
          f"{r['actions']:.4f} actions Airbus au {r['au']}")
    for e in r["esop"]:
        print(f"  ESOP {e['date']} : +{e['quantity']:.4f} ({e['type']})")


def cmd_cmb_csv(args: argparse.Namespace, settings: Settings) -> None:
    from pathlib import Path

    from . import imports

    files = sorted(Path(args.dossier).expanduser().glob("RELEVE_*.csv")) if args.dossier else []
    for acc, (new, updated, first, last) in imports.cmb_csv(settings, files).items():
        print(f"{acc} : {new} nouvelles, {updated} mises à jour ({first} → {last})")


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
    p = sub.add_parser("cmb", help="Comptes CMB via Enable Banking")
    p.add_argument("action", choices=["cle", "connect", "sync", "import"])
    p.add_argument("chemin", nargs="?", help="Pour `cle` : le fichier .pem de l'application")
    p.set_defaults(func=cmd_cmb)
    p = sub.add_parser("solde", help="Saisir le solde d'un compte absent des flux bancaires (livrets)")
    p.add_argument("compte")
    p.add_argument("montant")
    p.add_argument("--date", help="AAAA-MM-JJ, aujourd'hui par défaut")
    p.set_defaults(func=cmd_balance)
    p = sub.add_parser("sync", help="Tout synchroniser (Trade Republic, CMB, cours, historique, alertes)")
    p.add_argument("--sans-alertes", action="store_true")
    p.set_defaults(func=cmd_sync)
    p = sub.add_parser("alertes", help="Règles d'alerte")
    p.add_argument("action", choices=["liste", "ajouter", "tester"])
    p.add_argument("--type", choices=["baisse_ligne", "hausse_ligne", "baisse_portefeuille", "seuil_bas",
                                      "seuil_haut", "concentration", "budget"])
    p.add_argument("--isin")
    p.add_argument("--categorie")
    p.add_argument("--seuil", type=float)
    p.add_argument("--jours", type=int)
    p.add_argument("--note")
    p.add_argument("--mail", action="store_true")
    p.set_defaults(func=cmd_alerts)
    p = sub.add_parser("rapport", help="Bilan de la semaine rédigé par Claude Code")
    p.add_argument("--sans-sync", action="store_true")
    p.set_defaults(func=cmd_report)
    p = sub.add_parser("analyse", help="Analyse de la dernière séance rédigée par Claude Code")
    p.add_argument("--sans-sync", action="store_true")
    p.set_defaults(func=cmd_analysis)
    p = sub.add_parser("cloud", help="Routines Claude : publier leurs analyses (import) ou leur envoyer les données")
    p.add_argument("action", nargs="?", choices=["import", "export"], default="import")
    p.set_defaults(func=cmd_cloud)
    sub.add_parser("app", help="Ouvrir le tableau de bord (le lance s'il ne tourne pas)").set_defaults(func=cmd_app)
    sub.add_parser("taches", help="Installer les tâches planifiées Windows").set_defaults(func=cmd_tasks)
    p = sub.add_parser("cmb-csv", help="Importer les exports CSV de la CMB (RELEVE_*.csv)")
    p.add_argument("dossier", nargs="?", help="Dossier où prendre les RELEVE_*.csv (ex. Téléchargements)")
    p.set_defaults(func=cmd_cmb_csv)
    p = sub.add_parser("peg", help="Importer les relevés Amundi (AVO*.pdf) du PEG Airbus")
    p.add_argument("dossier", nargs="?", help="Dossier où prendre les nouveaux AVO*.pdf (ex. Téléchargements)")
    p.set_defaults(func=cmd_peg)
    p = sub.add_parser("historique", help="Cours, valorisation quotidienne et plus-values")
    p.add_argument("--sans-prix", action="store_true", help="Ne pas retélécharger les cours")
    p.set_defaults(func=cmd_history)
    args = parser.parse_args(argv)
    args.func(args, Settings())


if __name__ == "__main__":
    main()
