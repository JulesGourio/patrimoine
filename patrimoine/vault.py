"""Secrets, never in files: the OS credential store on the PC (Windows Credential Manager through keyring),
the Android Keystore in the mobile app (backend installed by `mobile.init`).

A backend is any object with ``get(name)``, ``set(name, value)`` and ``delete(name)``.
"""
from __future__ import annotations

from typing import Protocol

SERVICE = "patrimoine"

# Known secret names, with what they are for (shown by the CLI and the app settings).
KNOWN = {
    "tr_phone": "Numéro de téléphone Trade Republic (+33…)",
    "tr_pin": "Code PIN Trade Republic",
    "cmb_session": "Session Enable Banking (accès aux comptes CMB)",
    "ntfy_topic": "Sujet ntfy pour les notifications téléphone",
    "smtp_password": "Mot de passe d'application du mail d'alertes",
    "github_token": "Jeton GitHub (dépôt patrimoine) pour les analyses cloud sans git",
}


class Backend(Protocol):
    def get(self, name: str) -> str | None: ...
    def set(self, name: str, value: str) -> None: ...  # noqa: A003
    def delete(self, name: str) -> None: ...


class KeyringBackend:
    """The OS credential store; keyring is imported only when a secret is first needed."""

    def get(self, name: str) -> str | None:
        import keyring

        return keyring.get_password(SERVICE, name)

    def set(self, name: str, value: str) -> None:  # noqa: A003
        import keyring

        keyring.set_password(SERVICE, name, value)

    def delete(self, name: str) -> None:
        import keyring

        keyring.delete_password(SERVICE, name)


class MemoryBackend:
    """For tests: nothing leaves the process."""

    def __init__(self, values: dict[str, str] | None = None) -> None:
        self.values = dict(values or {})

    def get(self, name: str) -> str | None:
        return self.values.get(name)

    def set(self, name: str, value: str) -> None:  # noqa: A003
        self.values[name] = value

    def delete(self, name: str) -> None:
        self.values.pop(name, None)


_backend: Backend = KeyringBackend()


def use(backend: Backend) -> None:
    """Replace the secret store (the mobile app installs its Android Keystore backend at start)."""
    global _backend
    _backend = backend


def get(name: str) -> str | None:
    return _backend.get(name)


def set(name: str, value: str) -> None:  # noqa: A001 - mirrors keyring's API
    _backend.set(name, value)


def delete(name: str) -> None:
    _backend.delete(name)
