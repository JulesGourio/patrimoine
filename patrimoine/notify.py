"""Notifications: push through ntfy.sh (phone app) and e-mail through Gmail SMTP.

ntfy.sh no longer relays e-mail for anonymous users (error 40053), so mail goes out directly from
Jules's Gmail account with an app password kept in the credential store (`smtp_password`).
The ntfy topic name is the only thing protecting the push channel: it is random and kept secret.
In the mobile app, pushes become the phone's own notifications (`set_local`, installed by `mobile.init`).
"""
from __future__ import annotations

import logging
import os
import secrets as pysecrets
import smtplib
from email.message import EmailMessage
from typing import Callable

import requests

from . import vault

SERVER = "https://ntfy.sh"

log = logging.getLogger(__name__)

# (title, message, priority 1-5) -> shown or not. Set by the mobile app; None on the PC (ntfy).
_local: Callable[[str, str, int], bool] | None = None


def set_local(handler: Callable[[str, str, int], bool] | None) -> None:
    """Send pushes to this handler (the phone's notifications) instead of ntfy."""
    global _local
    _local = handler


def topic() -> str:
    t = vault.get("ntfy_topic")
    if not t:
        t = "patrimoine-" + pysecrets.token_hex(12)
        vault.set("ntfy_topic", t)
    return t


def push(title: str, message: str, priority: int = 3, tags: list[str] | None = None) -> bool:
    if _local is not None:
        try:
            return bool(_local(title, message[:3900], priority))
        except Exception:  # noqa: BLE001 - a notification must never break a sync
            log.exception("notification locale")
            return False
    body = {"topic": topic(), "title": title, "message": message[:3900], "priority": priority, "tags": tags or []}
    try:
        return requests.post(SERVER, json=body, timeout=20).status_code < 300
    except requests.RequestException:
        return False


def address() -> str:
    """The Gmail address used to send and receive the mails (secret ``smtp_email`` or ``PATRIMOINE_EMAIL``)."""
    return (vault.get("smtp_email") or os.environ.get("PATRIMOINE_EMAIL") or "").strip()


def mail_ready() -> bool:
    return bool(vault.get("smtp_password")) and bool(address())


def mail(subject: str, text: str, html: str | None = None, images: dict[str, bytes] | None = None) -> bool:
    """``images``: PNGs the HTML shows as ``<img src="cid:{name}">`` (inline, no remote loading)."""
    password, email = vault.get("smtp_password"), address()
    if not password or not email:
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"[Patrimoine] {subject}", email, email
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
        for name, png in (images or {}).items():
            msg.get_payload()[1].add_related(png, "image", "png", cid=f"<{name}>")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
            s.starttls()
            s.login(email, password.replace(" ", ""))
            s.send_message(msg)
        return True
    except (smtplib.SMTPException, OSError):
        return False


def markdown_html(md: str) -> str:
    try:
        import markdown

        body = markdown.markdown(md, extensions=["tables"])
    except ImportError:
        body = "<pre>" + md + "</pre>"
    return ("<div style=\"font-family:Inter,Arial,sans-serif;max-width:760px;line-height:1.5;color:#111827\">"
            + body + "</div>")


def send(title: str, message: str, priority: int = 3, tags: list[str] | None = None, email: bool = False,
         markdown_body: bool = False) -> str | None:
    """Push, plus a mail copy when asked and configured. Returns the channels that worked, or None."""
    done = []
    if push(title, message, priority, tags):
        done.append("ntfy" if _local is None else "téléphone")
    if email and mail(title, message, markdown_html(message) if markdown_body else None):
        done.append("mail")
    return "+".join(done) or None
