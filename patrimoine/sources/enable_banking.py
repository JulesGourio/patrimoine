"""CMB accounts through Enable Banking (PSD2 account information, read only).

Jules registered a production application in "restricted" mode: it only sees the accounts he linked
himself, which is all we need. The private key (.pem named after the application id) stays in the
data folder; the session id lives in the credential store. A session lasts until the consent
expires (at most 180 days), then `patrimoine cmb connect` must be run again.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import time
import urllib.parse
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import jwt
import requests

from .. import vault
from ..config import Settings

API = "https://api.enablebanking.com"
REDIRECT_URL = "https://localhost/patrimoine"
BANK_NAMES = ("Crédit Mutuel de Bretagne", "CMB")


class ConsentRequired(RuntimeError):
    """No valid CMB session: run `patrimoine cmb connect`."""


def key_dir(settings: Settings) -> Path:
    return settings.data_dir / "enablebanking"


def install_key(settings: Settings, pem: Path) -> str:
    """Copy the application's private key into the data folder; its file name is the application id."""
    app_id = pem.stem
    uuid.UUID(app_id)  # the control panel names the file after the application id
    key_dir(settings).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pem, key_dir(settings) / pem.name)
    return app_id


def app_key(settings: Settings) -> tuple[str, str]:
    pems = sorted(key_dir(settings).glob("*.pem"))
    if not pems:
        raise ConsentRequired("Clé Enable Banking absente : `patrimoine cmb cle <chemin du .pem>`.")
    return pems[-1].stem, pems[-1].read_text()


def headers(settings: Settings) -> dict[str, str]:
    app_id, key = app_key(settings)
    now = int(time.time())
    token = jwt.encode(
        {"iss": "enablebanking.com", "aud": "api.enablebanking.com", "iat": now, "exp": now + 3600},
        key, algorithm="RS256", headers={"kid": app_id},
    )
    return {"Authorization": f"Bearer {token}"}


def call(settings: Settings, method: str, path: str, **kw: Any) -> Any:
    r = requests.request(method, API + path, headers=headers(settings), timeout=60, **kw)
    if r.status_code in (401, 403) and "/accounts/" in path:
        raise ConsentRequired(f"Accès CMB refusé ({r.status_code}) : relance `patrimoine cmb connect`.")
    if r.status_code >= 400:
        raise RuntimeError(f"Enable Banking {method} {path} : {r.status_code} {r.text[:300]}")
    return r.json()


def find_bank(settings: Settings) -> dict[str, Any]:
    banks = call(settings, "GET", "/aspsps", params={"country": "FR"}).get("aspsps", [])
    for b in banks:
        if any(n.lower() in b["name"].lower() for n in BANK_NAMES):
            return b
    raise RuntimeError("CMB introuvable parmi les banques Enable Banking ("
                       + ", ".join(b["name"] for b in banks if "mutuel" in b["name"].lower()) + ")")


def start_consent(settings: Settings, days: int = 180) -> str:
    """URL where Jules signs in to CMB; the bank then redirects to REDIRECT_URL?code=…"""
    bank = find_bank(settings)
    # The bank rejects anything beyond its maximum, to the second: keep an hour of margin.
    seconds = min(days * 86400, int(bank.get("maximum_consent_validity") or days * 86400)) - 3600
    body = {
        "access": {"valid_until": (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()},
        "aspsp": {"name": bank["name"], "country": "FR"},
        "state": uuid.uuid4().hex,
        "redirect_url": REDIRECT_URL,
        "psu_type": "personal",
    }
    return call(settings, "POST", "/auth", json=body)["url"]


def finish_consent(settings: Settings, redirected_to: str) -> list[dict[str, Any]]:
    """Exchange the code from the redirect URL for a session; returns the accounts it covers."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(redirected_to.strip()).query)
    if "code" not in query:
        raise RuntimeError("Pas de code dans l'adresse collée : " + ", ".join(query.get("error", ["?"])))
    session = call(settings, "POST", "/sessions", json={"code": query["code"][0]})
    vault.set("cmb_session", session["session_id"])
    return session.get("accounts", [])


def session_accounts(settings: Settings) -> list[dict[str, Any]]:
    session_id = vault.get("cmb_session")
    if not session_id:
        raise ConsentRequired("Pas de connexion CMB : lance `patrimoine cmb connect`.")
    session = call(settings, "GET", f"/sessions/{session_id}")
    if session.get("status") not in (None, "AUTHORIZED"):
        raise ConsentRequired(f"Connexion CMB {session.get('status')} : relance `patrimoine cmb connect`.")
    accounts = session.get("accounts_data") or session.get("accounts") or []
    return [a if isinstance(a, dict) else {"uid": a} for a in accounts]


def transactions(settings: Settings, uid: str, date_from: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    params: dict[str, str] = {"date_from": date_from.isoformat()}
    while True:
        page = call(settings, "GET", f"/accounts/{uid}/transactions", params=params)
        out.extend(page.get("transactions", []))
        key = page.get("continuation_key")
        if not key:
            return out
        params["continuation_key"] = key


def dump(settings: Settings, date_from: date | None = None) -> Path:
    """Balances and transactions of every linked account, raw, to data/raw/cmb/<date>.json."""
    date_from = date_from or date.today() - timedelta(days=730)
    accounts = []
    for acc in session_accounts(settings):
        uid = acc["uid"]
        details = acc if "account_id" in acc else call(settings, "GET", f"/accounts/{uid}/details")
        accounts.append({
            "uid": uid,
            "details": details,
            "balances": call(settings, "GET", f"/accounts/{uid}/balances").get("balances", []),
            "transactions": transactions(settings, uid, date_from),
        })
    path = settings.data_dir / "raw" / "cmb" / f"{date.today().isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"accounts": accounts}, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def line_id(account_uid: str, tx: dict[str, Any], occurrence: int) -> str:
    """Bank ids when given; otherwise a hash of the line (two identical lines the same day get 0, 1…)."""
    ref = tx.get("entry_reference") or tx.get("transaction_id")
    if ref:
        return f"cmb:{ref}"
    basis = "|".join([account_uid, str(tx.get("booking_date")), json.dumps(tx.get("transaction_amount")),
                      " ".join(tx.get("remittance_information") or []), str(occurrence)])
    return "cmb:" + hashlib.sha1(basis.encode()).hexdigest()[:20]
