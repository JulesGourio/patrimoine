"""Secrets stored in the OS credential store (Windows Credential Manager), never in files."""
from __future__ import annotations

import keyring

SERVICE = "patrimoine"

# Known secret names, with what they are for (shown by the CLI).
KNOWN = {
    "tr_phone": "Numéro de téléphone Trade Republic (+33…)",
    "tr_pin": "Code PIN Trade Republic",
    "ntfy_topic": "Sujet ntfy pour les notifications téléphone",
    "smtp_password": "Mot de passe d'application du mail d'alertes",
}


def get(name: str) -> str | None:
    return keyring.get_password(SERVICE, name)


def set(name: str, value: str) -> None:  # noqa: A001 - mirrors keyring's API
    keyring.set_password(SERVICE, name, value)


def delete(name: str) -> None:
    keyring.delete_password(SERVICE, name)
