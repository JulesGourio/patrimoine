"""Trade Republic read access through pytr (private web API, reverse-engineered).

Only read subscriptions are used here; nothing in this module can place or cancel an order.
Login uses pytr's v2 web login: Jules confirms it in the Trade Republic app, no SMS code and no
browser for the WAF token. The session cookies are kept in the data folder so later syncs
resume without a new confirmation until Trade Republic expires them.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path
from typing import Any

from pytr.api import TradeRepublicApi, TradeRepublicError

from .. import vault
from ..config import Settings


class LoginRequired(RuntimeError):
    """The saved session is gone; Jules must run `patrimoine tr login` and confirm in the app."""


def api(settings: Settings) -> TradeRepublicApi:
    phone, pin = vault.get("tr_phone"), vault.get("tr_pin")
    if not (phone and pin):
        raise LoginRequired("Numéro ou PIN absent : `patrimoine secret set tr_phone` puis `tr_pin`.")
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return TradeRepublicApi(
        phone_no=phone,
        pin=pin,
        locale="fr",
        save_cookies=True,
        cookies_file=settings.data_dir / "tr_cookies.txt",
        use_v2_login=True,
    )


def connect(settings: Settings, interactive: bool = False) -> TradeRepublicApi:
    tr = api(settings)
    if tr.resume_websession():
        return tr
    if not interactive:
        raise LoginRequired("Session Trade Republic expirée : lance `uv run patrimoine tr login`.")
    tr.initiate_weblogin()
    code = None
    if tr.weblogin_needs_authenticator:
        code = input("Code de l'application d'authentification : ")
    else:
        print("Confirme la connexion dans l'appli Trade Republic (2 min max)…")
    tr.complete_weblogin(code)
    return tr


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


async def fetch_all(tr: TradeRepublicApi) -> dict[str, Any]:
    """Everything needed to rebuild accounts, flows and positions, as raw JSON."""
    account = tr.settings()
    out: dict[str, Any] = {"account": account}
    out["transactions"] = await paginate(tr, "timelineTransactions")
    out["activity"] = await paginate(tr, "timelineActivityLog")
    details = {}
    for item in out["transactions"] + out["activity"]:
        try:
            details[item["id"]] = await request(tr, {"type": "timelineDetailV2", "id": item["id"]})
        except (TradeRepublicError, asyncio.TimeoutError):
            details[item["id"]] = None
    out["details"] = details
    # One securities account per product (compte-titres, PEA): ask for each one we can see.
    sec_accounts = {account.get("securitiesAccountNumber")}
    for acc in account.get("securitiesAccounts") or []:
        if isinstance(acc, dict):
            sec_accounts.add(acc.get("securitiesAccountNumber") or acc.get("number"))
    out["portfolios"] = {}
    for no in filter(None, sec_accounts):
        try:
            out["portfolios"][no] = await request(tr, {"type": "compactPortfolioByType", "secAccNo": no})
        except (TradeRepublicError, asyncio.TimeoutError) as e:
            out["portfolios"][no] = {"error": str(e)}
    for key, payload in {
        "cash": {"type": "cash"},
        "savings_plans": {"type": "savingsPlans"},
        "history_max": {"type": "portfolioAggregateHistory", "range": "max"},
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
    data = asyncio.run(fetch_all(tr))
    path = settings.data_dir / "raw" / "tr" / f"{date.today().isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return path
