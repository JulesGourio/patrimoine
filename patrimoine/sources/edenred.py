"""Connecteur MyEdenred (carte titres-restaurant) : SQUELETTE, rien n'est encore écrit.

Edenred n'a pas d'API publique pour un particulier ; le site MyEdenred n'a pas encore été observé avec l'utilisateur
(pages, requêtes, déroulé de la double authentification). Tant que ce n'est pas fait, les trois fonctions lèvent
``NotImplementedError`` et la carte se tient à la main : ``carte_operation``, ``carte_solde`` et ``carte_import``
(copier-coller de l'historique de l'appli), voir ``patrimoine/cartes.py``.

Risques à garder en tête avant d'écrire la suite :

- Non officiel : le site peut interdire l'automatisation dans ses conditions d'utilisation ; tout repose sur des
  pages et des requêtes que rien ne garantit.
- Fragile : un changement de page, d'URL ou de protection anti-robot casse le connecteur sans prévenir. Il doit
  échouer proprement (message clair, aucune écriture partielle) et ne jamais bloquer la synchro des autres sources.
- Double authentification : une confirmation (SMS, appli) peut être demandée à chaque connexion. L'utilisateur la
  fait en personne ; le connecteur ne la contourne pas. Garder la session pour limiter les demandes, comme
  Trade Republic.
- Secrets : ``edenred_login`` et ``edenred_password`` uniquement dans ``patrimoine.vault`` (jamais dans le code, un
  fichier ``.env`` ou la base). Rien ne doit être journalisé.

Comment il alimentera les mêmes outils que la saisie manuelle (aucun code supplémentaire côté base) :

    carte = cartes.resolve(con, "Edenred")
    for op in fetch_operations(since):          # [{"date", "libelle", "montant", "type"}]
        cartes.add_operation(con, carte, op["date"], op["montant"], op["libelle"], op["type"])
    cartes.set_balance(con, carte, fetch_balance())

``add_operation`` ne recrée pas une opération identique déjà présente, donc relancer sur une fenêtre qui
chevauche l'historique est sans danger ; ``set_balance`` ne crée une ligne d'ajustement que si le solde du site
diffère du solde calculé (ce qui signale une opération manquée).
"""
from __future__ import annotations

from datetime import date

from .. import vault

A_ECRIRE = "à écrire après observation du site MyEdenred avec l'utilisateur"


def credentials() -> tuple[str, str]:
    """Identifiant et mot de passe MyEdenred depuis le coffre (``edenred_login``, ``edenred_password``)."""
    login, password = vault.get("edenred_login"), vault.get("edenred_password")
    if not login or not password:
        raise RuntimeError("identifiants MyEdenred absents du coffre (edenred_login, edenred_password)")
    return login, password


class Edenred:
    """Session MyEdenred. Interface cible ; à implémenter après observation du site."""

    def login(self) -> None:
        """Ouvre la session (identifiants du coffre ; double authentification confirmée par l'utilisateur)."""
        raise NotImplementedError(A_ECRIRE)

    def fetch_balance(self) -> float:
        """Solde actuel de la carte, en euros."""
        raise NotImplementedError(A_ECRIRE)

    def fetch_operations(self, since: date) -> list[dict]:
        """Opérations depuis ``since`` : [{"date": AAAA-MM-JJ, "libelle": str, "montant": euros positif,
        "type": "paiement" | "credit"}]."""
        raise NotImplementedError(A_ECRIRE)


def login() -> Edenred:
    session = Edenred()
    session.login()
    return session


def fetch_balance(session: Edenred) -> float:
    return session.fetch_balance()


def fetch_operations(session: Edenred, since: date) -> list[dict]:
    return session.fetch_operations(since)
