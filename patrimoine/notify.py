"""Push notifications through ntfy.sh (phone app) with an e-mail copy relayed by ntfy.

The topic name is the only thing that protects the channel: it is random and kept in the
credential store. Jules subscribes to it once in the ntfy app.
"""
from __future__ import annotations

import secrets as pysecrets

import requests

from . import vault

SERVER = "https://ntfy.sh"
EMAIL = "ju.gourio@gmail.com"


def topic() -> str:
    t = vault.get("ntfy_topic")
    if not t:
        t = "patrimoine-" + pysecrets.token_hex(12)
        vault.set("ntfy_topic", t)
    return t


def send(title: str, message: str, priority: int = 3, tags: list[str] | None = None, email: bool = True,
         click: str | None = None) -> bool:
    body = {"topic": topic(), "title": title, "message": message, "priority": priority, "tags": tags or []}
    if email:
        body["email"] = EMAIL
    if click:
        body["click"] = click
    try:
        r = requests.post(SERVER, json=body, timeout=20)
        return r.status_code < 300
    except requests.RequestException:
        return False
