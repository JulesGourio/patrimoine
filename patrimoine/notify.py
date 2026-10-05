"""Notifications: push through ntfy.sh (phone app) and e-mail through Gmail SMTP.

ntfy.sh no longer relays e-mail for anonymous users (error 40053), so mail goes out directly from
Jules's Gmail account with an app password kept in the credential store (`smtp_password`).
The ntfy topic name is the only thing protecting the push channel: it is random and kept secret.
"""
from __future__ import annotations

import secrets as pysecrets
import smtplib
from email.message import EmailMessage

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


def push(title: str, message: str, priority: int = 3, tags: list[str] | None = None) -> bool:
    body = {"topic": topic(), "title": title, "message": message[:3900], "priority": priority, "tags": tags or []}
    try:
        return requests.post(SERVER, json=body, timeout=20).status_code < 300
    except requests.RequestException:
        return False


def mail_ready() -> bool:
    return bool(vault.get("smtp_password"))


def mail(subject: str, text: str, html: str | None = None, images: dict[str, bytes] | None = None) -> bool:
    """``images``: PNGs the HTML shows as ``<img src="cid:{name}">`` (inline, no remote loading)."""
    password = vault.get("smtp_password")
    if not password:
        return False
    msg = EmailMessage()
    msg["Subject"], msg["From"], msg["To"] = f"[Patrimoine] {subject}", EMAIL, EMAIL
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
        for name, png in (images or {}).items():
            msg.get_payload()[1].add_related(png, "image", "png", cid=f"<{name}>")
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
            s.starttls()
            s.login(EMAIL, password.replace(" ", ""))
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


def send(title: str, message: str, priority: int = 3, tags: list[str] | None = None, email: bool = True,
         markdown_body: bool = False) -> str | None:
    """Push, plus a mail copy when asked and configured. Returns the channels that worked, or None."""
    done = []
    if push(title, message, priority, tags):
        done.append("ntfy")
    if email and mail(title, message, markdown_html(message) if markdown_body else None):
        done.append("mail")
    return "+".join(done) or None
