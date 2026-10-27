"""Trade Republic read access through pytr (private web API, reverse-engineered).

Only read subscriptions are used here; nothing in this module can place or cancel an order.
Login uses pytr's v2 web login: Jules confirms it in the Trade Republic app, no SMS code and no
browser for the WAF token. The session cookies are kept in the data folder so later syncs
resume without a new confirmation until Trade Republic expires them.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Callable

import requests
from pytr.api import TradeRepublicApi, TradeRepublicError

from .. import vault
from ..config import Settings


class LoginRequired(RuntimeError):
    """The saved session is gone; Jules must run `patrimoine tr login` and confirm in the app."""


def normalize_phone(raw: str) -> str:
    """Trade Republic wants the international format without spaces: 06 12 34 56 78 -> +33612345678."""
    phone = re.sub(r"[\s.\-()]", "", raw)
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    elif phone.startswith("0"):
        phone = "+33" + phone[1:]
    if not re.fullmatch(r"\+\d{8,15}", phone):
        raise LoginRequired("Numéro Trade Republic mal formé : ressaisis-le au format +33612345678 "
                            "(`patrimoine secret set tr_phone`).")
    return phone


def api(settings: Settings) -> TradeRepublicApi:
    phone, pin = vault.get("tr_phone"), vault.get("tr_pin")
    if not (phone and pin):
        raise LoginRequired("Numéro ou PIN absent : `patrimoine secret set tr_phone` puis `tr_pin`.")
    phone, pin = normalize_phone(phone), pin.strip()
    if not re.fullmatch(r"\d{4}", pin):
        raise LoginRequired("Le PIN Trade Republic fait 4 chiffres : `patrimoine secret set tr_pin`.")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return TradeRepublicApi(
        phone_no=phone,
        pin=pin,
        locale="fr",
        save_cookies=True,
        cookies_file=settings.data_dir / "tr_cookies.txt",
        use_v2_login=True,
    )


def connect(settings: Settings, interactive: bool = False,
            ask_code: Callable[[], str] | None = None) -> TradeRepublicApi:
    """Resume the saved session, or (interactive) log in: Jules confirms in the Trade Republic app. ``ask_code``
    gives the authenticator code when the account uses one (the terminal by default)."""
    tr = api(settings)
    if tr.resume_websession():
        return tr
    if not interactive:
        raise LoginRequired("Session Trade Republic expirée : lance `uv run patrimoine tr login`.")
    try:
        tr.initiate_weblogin()
    except requests.HTTPError as e:
        raise LoginRequired(f"Trade Republic refuse la connexion ({e.response.status_code}) : "
                            f"{_error_codes(e.response)}") from None
    code = None
    if tr.weblogin_needs_authenticator:
        code = (ask_code or (lambda: input("Code de l'application d'authentification : ")))()
    else:
        print("Confirme la connexion dans l'appli Trade Republic (2 min max)…")
    tr.complete_weblogin(code)
    return tr


def _error_codes(response: requests.Response) -> str:
    """The error codes Trade Republic sends back; never echoes the request (it holds the PIN)."""
    try:
        errors = response.json().get("errors") or []
        return ", ".join(f"{e.get('errorCode')} {e.get('errorField') or ''}".strip() for e in errors) or "sans détail"
    except ValueError:
        return "réponse vide"


async def request(tr: TradeRepublicApi, payload: dict[str, Any], timeout: float = 20) -> Any:
    """Subscribe, wait for the first answer to this subscription, unsubscribe."""
    sub_id = await tr.subscribe(payload)
    try:
        while True:
            got_id, _, response = await asyncio.wait_for(tr.recv(), timeout)
            if got_id == sub_id:
                return response
    finally:
        try:
            await tr.unsubscribe(sub_id)
        except Exception:  # noqa: BLE001 - the subscription may already be closed server side
            pass


async def paginate(tr: TradeRepublicApi, kind: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    after = None
    while True:
        page = await request(tr, {"type": kind, "after": after})
        items.extend(page.get("items", []))
        after = (page.get("cursors") or {}).get("after")
        if not after:
            return items


def _cached_details(settings: Settings) -> dict[str, Any]:
    """Details already fetched by the last dump: a past operation's detail does not change, so only new ones
    (and those that failed last time) are requested again."""
    files = sorted((settings.data_dir / "raw" / "tr").glob("*.json"))
    if not files:
        return {}
    try:
        old = json.loads(files[-1].read_text(encoding="utf-8")).get("details") or {}
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in old.items() if v is not None}


async def fetch_all(tr: TradeRepublicApi, cached: dict[str, Any] | None = None) -> dict[str, Any]:
    """Everything needed to rebuild accounts, flows and positions, as raw JSON."""
    account = tr.settings()
    out: dict[str, Any] = {"account": account}
    out["transactions"] = await paginate(tr, "timelineTransactions")
    out["activity"] = await paginate(tr, "timelineActivityLog")
    details = {}
    cached = cached or {}
    for item in out["transactions"] + out["activity"]:
        if item["id"] in cached:
            details[item["id"]] = cached[item["id"]]
            continue
        try:
            details[item["id"]] = await request(tr, {"type": "timelineDetailV2", "id": item["id"]})
        except (TradeRepublicError, asyncio.TimeoutError):
            details[item["id"]] = None
    out["details"] = details
    # The account settings only give the compte-titres number; the PEA is a sibling number
    # (compte-titres + 1 for Jules). Try the neighbours and keep those that answer.
    out["portfolios"] = {}
    cto = account.get("securitiesAccountNumber")
    if cto and cto.isdigit():
        width = len(cto)
        for delta in (0, 1, -1, 2):
            no = str(int(cto) + delta).zfill(width)
            try:
                out["portfolios"][no] = await request(
                    tr, {"type": "compactPortfolioByType", "secAccNo": no}, timeout=20 if delta == 0 else 8)
            except (TradeRepublicError, asyncio.TimeoutError):
                pass
    for key, payload in {
        "cash": {"type": "cash"},
        "savings_plans": {"type": "savingsPlans"},
    }.items():
        try:
            out[key] = await request(tr, payload)
        except (TradeRepublicError, asyncio.TimeoutError) as e:
            out[key] = {"error": str(e)}
    await tr.close()
    return out


def dump(settings: Settings, interactive: bool = False) -> Path:
    """Fetch everything and write it to data/raw/tr/<date>.json (kept locally, never committed)."""
    tr = connect(settings, interactive)
    data = asyncio.run(fetch_all(tr, _cached_details(settings)))
    path = settings.data_dir / "raw" / "tr" / f"{date.today().isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
