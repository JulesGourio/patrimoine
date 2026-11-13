"""Daily closing prices in EUR from Yahoo Finance, one listing per ISIN.

Trade Republic no longer serves price history (aggregateHistory answers BAD_SUBSCRIPTION_TYPE),
so Yahoo is the source. Euro listings are preferred; other currencies are converted with the
day's rate. Turbos and warrants have no listing: the portfolio values them at trade prices.
"""
from __future__ import annotations

import logging
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone

import pandas as pd

log = logging.getLogger(__name__)

# Euro venues first; London last because it mixes GBp, GBP and USD lines.
VENUE_RANK = {"PA": 0, "AS": 1, "DE": 2, "F": 3, "SG": 4, "MI": 5, "MC": 6, "BR": 7, "": 8, "HK": 9, "L": 10}
FX = {"USD": "EURUSD=X", "GBP": "EURGBP=X", "HKD": "EURHKD=X", "CHF": "EURCHF=X", "JPY": "EURJPY=X"}


def venue(symbol: str) -> str:
    return symbol.rsplit(".", 1)[1] if "." in symbol else ""


def candidates(isin: str) -> list[str]:
    import yfinance as yf

    try:
        quotes = yf.Search(isin, max_results=10).quotes
    except Exception:  # noqa: BLE001 - network or Yahoo format change: no candidate
        return []
    symbols = [q["symbol"] for q in quotes if q.get("symbol")]
    return sorted(symbols, key=lambda s: VENUE_RANK.get(venue(s), 8))


def history(symbol: str, start: date) -> tuple[pd.Series, str]:
    """Split-adjusted daily closes (Yahoo 'Close') and the listing currency."""
    import yfinance as yf

    t = yf.Ticker(symbol)
    df = t.history(start=start.isoformat(), auto_adjust=False, actions=False)
    if df.empty:
        return pd.Series(dtype=float), ""
    currency = (t.history_metadata or {}).get("currency") or ""
    s = df["Close"].dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None).normalize()
    return s, currency


def to_eur(s: pd.Series, currency: str, start: date) -> pd.Series | None:
    if currency == "EUR":
        return s
    if currency == "GBp":
        s, currency = s / 100, "GBP"
    pair = FX.get(currency)
    if not pair:
        return None
    rate, _ = history(pair, start)
    if rate.empty:
        return None
    rate = rate.reindex(s.index.union(rate.index)).ffill().reindex(s.index)
    return (s / rate).dropna()


def closes(tickers: list[str], start: date | str, batch_size: int = 200) -> pd.DataFrame:
    """Adjusted daily closes of many US tickers at once (one column each), in their own currency.

    Yahoo rate-limits bursts: batches are paced, and a batch that comes back mostly empty is retried once.
    Dotted class shares ("BRK.B") are asked as Yahoo writes them ("BRK-B") and returned under the original name.
    """
    import time

    import yfinance as yf

    names = {t.replace(".", "-"): t for t in dict.fromkeys(tickers) if t}
    frames = []
    todo = sorted(names)
    for i in range(0, len(todo), batch_size):
        batch = todo[i:i + batch_size]
        df = None
        for _ in range(2):
            try:
                got = yf.download(batch, start=str(start), auto_adjust=True, progress=False, threads=True)["Close"]
                df = got if isinstance(got, pd.DataFrame) else got.to_frame(batch[0])
            except Exception as e:  # noqa: BLE001 - network or Yahoo format change
                log.warning("Yahoo: %s", e)
                df = None
            if df is not None and df.notna().any().mean() > 0.5:
                break
            time.sleep(30)
        if df is not None:
            frames.append(df)
        if i + batch_size < len(todo):
            time.sleep(5)
    if not frames:
        return pd.DataFrame()
    px = pd.concat(frames, axis=1).sort_index().ffill()
    px.index = pd.to_datetime(px.index).tz_localize(None)
    return px.rename(columns=names)


def change(px: pd.DataFrame, ticker: str, start, end=None) -> float | None:
    """Price change of ``ticker`` from the first close on or after ``start`` to the last close on or before
    ``end`` (the latest close when None)."""
    if ticker not in px:
        return None
    s = px[ticker].dropna()
    after = s[s.index >= pd.Timestamp(start)]
    until = s[s.index <= pd.Timestamp(end)] if end is not None else s
    if after.empty or until.empty or not after.iloc[0] or until.index[-1] < after.index[0]:
        return None
    return float(until.iloc[-1] / after.iloc[0] - 1)


# Trade Republic crypto "ISINs" (XF000BTC0017) carry the coin's code; Yahoo quotes it against the euro.
CRYPTO_NAMES = {"BITCOIN": "BTC", "ETHEREUM": "ETH", "SOLANA": "SOL", "RIPPLE": "XRP", "CARDANO": "ADA",
                "POLKADOT": "DOT", "DOGECOIN": "DOGE", "LITECOIN": "LTC", "CHAINLINK": "LINK", "AVALANCHE": "AVAX"}


def crypto_symbols(isin: str, name: str | None) -> list[str]:
    import re

    out = []
    m = re.match(r"XF000([A-Z0-9]{2,5}?)\d{3,4}$", isin or "")
    if m:
        out.append(f"{m.group(1)}-EUR")
    code = CRYPTO_NAMES.get((name or "").strip().upper())
    if code:
        out.append(f"{code}-EUR")
    return out


# Listings Yahoo's ISIN search misses; tried along with its own results.
EXTRA_SYMBOLS = {
    "FR0010342592": ["LQQ.PA"],
    "US69608A1088": ["PLTR", "PTX.DE"],
    "JE00BYQY3Z98": ["3CFL.L"],
    "IE00BQT3WG13": ["CNYA.AS"],
}


def score(eur: pd.Series, trades: list[tuple[pd.Timestamp, float]], splits: list[pd.Timestamp],
          first_day: pd.Timestamp) -> tuple[int, float]:
    """(covers the whole holding period, closeness of Yahoo's close to our trade prices). Higher is better."""
    covers = int(eur.index[0] <= first_day + pd.Timedelta(days=10) and len(eur) >= 20)
    last_split = max(splits) if splits else pd.Timestamp.min
    ratios = [u / eur.asof(d) for d, u in trades if d >= last_split and d >= eur.index[0]]
    ratios = [r for r in ratios if r == r and r > 0]
    if not ratios:
        return covers, -1.0
    ratios.sort()
    return covers, -abs(math.log(ratios[len(ratios) // 2]))


def update(con: sqlite3.Connection, isins: list[str] | None = None) -> dict[str, str]:
    """Fetch prices for every instrument (or the given ones). Returns {isin: symbol or reason}."""
    from .portfolio import rows, trade_prices

    txs = rows(con)
    trades = trade_prices(txs)
    first_seen: dict[str, pd.Timestamp] = {}
    splits: dict[str, list[pd.Timestamp]] = {}
    for r in txs:
        if r["isin"]:
            first_seen.setdefault(r["isin"], pd.Timestamp(r["date"]))
            if r["flow"] == "operation_titres":
                splits.setdefault(r["isin"], []).append(pd.Timestamp(r["date"]))
    default_first = min(first_seen.values(), default=pd.Timestamp(date.today() - timedelta(days=365)))
    done: dict[str, str] = {}
    for isin, symbol, kind, name in con.execute("SELECT isin, symbol, kind, name FROM instruments").fetchall():
        if isins and isin not in isins:
            continue
        if kind == "derive":
            done[isin] = "turbo : prix des ordres"
            continue
        first_day = first_seen.get(isin, default_first)
        start = (first_day - pd.Timedelta(days=10)).date()
        best: tuple[tuple[int, float], str, str, pd.Series] | None = None
        tried = dict.fromkeys(([symbol] if symbol else []) + EXTRA_SYMBOLS.get(isin, [])
                              + (crypto_symbols(isin, name) if kind == "crypto" else candidates(isin)))
        for sym in tried:
            try:
                s, currency = history(sym, start)
            except Exception as e:  # noqa: BLE001
                log.info("%s %s: %s", isin, sym, e)
                continue
            eur = to_eur(s, currency, start) if not s.empty else None
            if eur is None or eur.empty:
                continue
            sc = score(eur, trades.get(isin, []), splits.get(isin, []), first_day)
            if best is None or sc > best[0]:
                best = (sc, sym, currency, eur)
            if sc[0] == 1 and sc[1] > -0.03:
                break  # whole period, within 3 % of our trade prices: good enough
        if best is None:
            done[isin] = "aucune cotation trouvée"
            continue
        sc, sym, currency, eur = best
        con.execute("DELETE FROM prices WHERE isin = ?", (isin,))
        con.executemany(
            "INSERT INTO prices (isin, date, close, source) VALUES (?, ?, ?, ?)",
            [(isin, d.date().isoformat(), float(v), sym) for d, v in eur.items()],
        )
        con.execute("UPDATE instruments SET symbol = ?, currency = ? WHERE isin = ?", (sym, currency, isin))
        gap = f", écart aux ordres {100 * (math.exp(-sc[1]) - 1):.1f} %" if sc[1] > -1 else ""
        done[isin] = f"{sym} ({currency}{'' if sc[0] else ', période incomplète'}{gap})"
    con.commit()
    return done


# ---------- intraday quotes (period 1J of the Bourse screen, stock sheet) ----------

PARIS = "Europe/Paris"
INTRADAY_INTERVAL = "5m"
INTRADAY_KEEP_DAYS = 7       # rows older than this are deleted at each refresh
INTRADAY_FETCH_DAYS = 5      # Yahoo serves 5-minute bars for the last 60 days; 5 days cover a long weekend
INTRADAY_MAX_AGE_MIN = 15    # during the session, quotes older than this are fetched again
_ECHEC: dict[str, float] = {}  # isin -> monotonic time before which the source is not asked again
_ECHEC_ERREUR = 300.0          # offline, Yahoo down
_ECHEC_VIDE = 1800.0           # no bars (holiday, unknown symbol)


def _paris(now: datetime | None = None) -> datetime:
    from zoneinfo import ZoneInfo

    return (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(PARIS))


def session_ouverte(now: datetime | None = None) -> bool:
    """Weekdays 8:00–22:00 in Paris: the only time prices move for the lines held (Europe, then the US close)."""
    p = _paris(now)
    return p.weekday() < 5 and 8 <= p.hour < 22


def _derniere_seance(now: datetime | None = None) -> date:
    """Paris date of the session the quotes should cover: today once 8:00 has passed on a weekday, else the
    previous weekday."""
    p = _paris(now)
    d = p.date()
    if p.weekday() >= 5 or p.hour < 8:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def intraday(symbol: str, interval: str = INTRADAY_INTERVAL, jours: int = INTRADAY_FETCH_DAYS) -> tuple[pd.Series, str]:
    """Bars of the last days (Yahoo 'Close', UTC naive index) and the listing currency. Raises when offline."""
    import yfinance as yf

    t = yf.Ticker(symbol)
    df = t.history(period=f"{jours}d", interval=interval, auto_adjust=False, actions=False, timeout=10)
    if df.empty:
        return pd.Series(dtype=float), ""
    currency = (t.history_metadata or {}).get("currency") or ""
    s = df["Close"].dropna()
    idx = pd.to_datetime(s.index)
    s.index = (idx.tz_convert("UTC") if idx.tz is not None else idx).tz_localize(None)
    return s, currency


def intraday_eur(s: pd.Series, currency: str, fx: dict[str, pd.Series | None]) -> pd.Series | None:
    """Intraday bars in euros, with the currency pair at the same pace (kept in `fx` for the other lines)."""
    if currency == "EUR":
        return s
    if currency == "GBp":
        s, currency = s / 100, "GBP"
    pair = FX.get(currency)
    if not pair:
        return None
    if pair not in fx:
        try:
            rate, _ = intraday(pair)
        except Exception as e:  # noqa: BLE001
            log.info("%s: %s", pair, e)
            rate = pd.Series(dtype=float)
        fx[pair] = rate if not rate.empty else None
    rate = fx[pair]
    if rate is None:
        return None
    rate = rate.reindex(s.index.union(rate.index)).ffill().bfill().reindex(s.index)
    return (s / rate).dropna()


def purge_intraday(con: sqlite3.Connection, now: datetime | None = None, jours: int = INTRADAY_KEEP_DAYS) -> int:
    """Delete the quotes older than `jours` days. Returns how many rows went."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=jours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = con.execute("DELETE FROM prices_intraday WHERE ts < ?", (cutoff,)).rowcount
    return n


def _a_rafraichir(last: str | None, now: datetime) -> bool:
    if last is None:
        return True
    t = datetime.strptime(last, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    if session_ouverte(now):
        return now - t > timedelta(minutes=INTRADAY_MAX_AGE_MIN)
    return _paris(t).date() < _derniere_seance(now)


def update_intraday(con: sqlite3.Connection, isins: list[str] | None = None, now: datetime | None = None,
                    force: bool = False) -> dict[str, int]:
    """Fetch the 5-minute quotes of the lines (all instruments with a symbol, or the given ISINs) and store them in
    `prices_intraday`. Without `force`, only the lines whose quotes are missing or, during the session, older than
    15 minutes. Never raises: offline or source down, the quotes already stored stay. Returns {isin: rows written}."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    now = now or datetime.now(timezone.utc)
    done: dict[str, int] = {}
    try:
        purge_intraday(con, now)
        todo = []
        for isin, symbol, currency in con.execute(
                "SELECT isin, symbol, currency FROM instruments WHERE symbol IS NOT NULL AND symbol != ''"
                " AND COALESCE(kind, '') != 'derive'").fetchall():
            if isins is not None and isin not in isins:
                continue
            if time.monotonic() < _ECHEC.get(isin, 0.0):
                continue
            last = con.execute("SELECT MAX(ts) FROM prices_intraday WHERE isin = ?", (isin,)).fetchone()[0]
            if force or _a_rafraichir(last, now):
                todo.append((isin, symbol, currency or "EUR"))
        if not todo:
            return done

        def fetch(item: tuple[str, str, str]) -> tuple[str, str, pd.Series | None, str]:
            isin, symbol, _ = item
            try:
                s, cur = intraday(symbol)
                return isin, symbol, s, cur
            except Exception as e:  # noqa: BLE001 - offline, Yahoo format change
                log.info("%s %s: %s", isin, symbol, e)
                return isin, symbol, None, ""

        with ThreadPoolExecutor(max_workers=4) as pool:
            fetched = list(pool.map(fetch, todo))
        fx: dict[str, pd.Series | None] = {}
        for (isin, symbol, stored_cur), (_, _, s, cur) in zip(todo, fetched):
            if s is None:
                _ECHEC[isin] = time.monotonic() + _ECHEC_ERREUR
                continue
            eur = intraday_eur(s, cur or stored_cur, fx) if not s.empty else None
            if eur is None or eur.empty:
                _ECHEC[isin] = time.monotonic() + _ECHEC_VIDE
                continue
            _ECHEC.pop(isin, None)
            con.executemany(
                "INSERT OR REPLACE INTO prices_intraday (isin, ts, close, source) VALUES (?, ?, ?, ?)",
                [(isin, d.strftime("%Y-%m-%dT%H:%M:%SZ"), float(v), symbol) for d, v in eur.items()])
            done[isin] = len(eur)
        con.commit()
    except Exception as e:  # noqa: BLE001 - the screen and the watch must never fail for the quotes
        log.warning("intraday: %s", e)
    return done
