"""Live market data for the IREN dossier — free, key-less public feeds only.

Primary source is Nasdaq's own quote API (IREN is a NASDAQ-GS listing, so this is the
listing venue's own feed: quote, key statistics and a year of daily closes). Yahoo's
chart endpoint is the fallback. Neither needs an API key or an account.

Everything here is a cache in front of somebody else's feed. It is deliberately kept
apart from the petition record: nothing renders as fact without the timestamp it was
taken at, a page never blocks on the network, and every failure degrades to showing the
last figure we did get. Set MARKET_DATA=off to disable the fetch entirely.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone

import requests
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

SYMBOL = "IREN"
QUOTE_TTL = 300           # serve a cached quote this long before refetching
HISTORY_TTL = 6 * 3600    # daily closes: a few refreshes a day is plenty
STALE_LIMIT = 14 * 86400  # past this we stop showing a price at all
ERROR_BACKOFF = 120       # after a failed fetch, wait this long before trying again
TIMEOUT = (4, 6)          # (connect, read)
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
SPARK_W, SPARK_H = 640, 96


def enabled() -> bool:
    return os.environ.get("MARKET_DATA", "on").strip().lower() not in ("0", "off", "false", "no")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- parsing helpers
def num(v) -> float | None:
    """'$41.2907' / '44,902,322.09' / '-0.86%' / '+2.05' -> float; anything else -> None."""
    if isinstance(v, (int, float)):
        return float(v)
    if not isinstance(v, str):
        return None
    s = v.strip().replace(",", "").replace("$", "").replace("%", "").replace("+", "")
    if s in ("", "-", "--", "N/A", "NA", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _pair(v, order: str = "lohi") -> tuple[float | None, float | None]:
    """'25.31 - 76.87' or '$41.82/$39.03' -> (low, high). `order` is the source's order."""
    if not isinstance(v, str):
        return None, None
    parts = [num(p) for p in re.split(r"\s*[-/]\s*", v.strip()) if p.strip()]
    parts = [p for p in parts if p is not None]
    if len(parts) != 2:
        return None, None
    a, b = parts
    return (a, b) if order == "lohi" else (b, a)


def _direction(change: float | None) -> str:
    if change is None:
        return "flat"
    return "up" if change > 0 else ("down" if change < 0 else "flat")


# ---------------------------------------------------------------- the quote itself
@dataclass
class Quote:
    symbol: str = SYMBOL
    name: str | None = None
    exchange: str | None = None
    currency: str = "USD"

    # latest print, whichever session it came from
    price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    as_of: str | None = None
    market_status: str | None = None

    # the regular session's close, when the latest print is pre/after-hours
    close_price: float | None = None
    close_change: float | None = None
    close_change_pct: float | None = None
    close_as_of: str | None = None

    previous_close: float | None = None
    day_low: float | None = None
    day_high: float | None = None
    week52_low: float | None = None
    week52_high: float | None = None
    volume: float | None = None
    avg_volume: float | None = None
    market_cap: float | None = None
    one_year_target: float | None = None
    bid: float | None = None
    ask: float | None = None

    history: list[list[float]] = field(default_factory=list)   # [[epoch_ms, close], …]
    history_at: str | None = None

    source: str | None = None
    source_url: str | None = None
    fetched_at: str | None = None

    # ---- serialization (the cached JSON may predate a field, so unknown keys are dropped)
    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"))

    @classmethod
    def from_json(cls, raw: str) -> "Quote | None":
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        if not isinstance(data, dict):
            return None
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    # ---- derived, for the template
    @property
    def fetched(self) -> datetime | None:
        return _parse_iso(self.fetched_at)

    @property
    def age_seconds(self) -> float:
        f = self.fetched
        return (utcnow() - f).total_seconds() if f else 1e9

    @property
    def history_age_seconds(self) -> float:
        h = _parse_iso(self.history_at)
        return (utcnow() - h).total_seconds() if h else 1e9

    @property
    def is_stale(self) -> bool:
        return self.age_seconds > STALE_LIMIT

    @property
    def extended_hours(self) -> bool:
        """True when the latest print is outside the regular session, so two prices show."""
        return self.close_price is not None

    @property
    def direction(self) -> str:
        return _direction(self.change)

    @property
    def close_direction(self) -> str:
        return _direction(self.close_change)

    @property
    def status_key(self) -> str:
        return (self.market_status or "").strip().lower()

    @property
    def session_label(self) -> str:
        return {"open": "Market open", "closed": "Market closed", "after-hours": "After hours",
                "pre-market": "Pre-market", "extended hours": "Extended hours"}.get(
                    self.status_key, self.market_status or "")

    @property
    def headline_label(self) -> str:
        """What the big number is. Saying "after hours" over a 4pm close reads as a contradiction."""
        if self.extended_hours:
            return "At the close"
        return "Live" if self.status_key == "open" else "Last close"

    @property
    def ext_label(self) -> str:
        return "Pre-market" if self.status_key == "pre-market" else "After hours"

    def _pos(self, lo, hi) -> float | None:
        """Where the last price sits in a low–high band, 0–100."""
        p = self.close_price if self.close_price is not None else self.price
        if None in (p, lo, hi) or hi <= lo:
            return None
        return round(max(0.0, min(1.0, (p - lo) / (hi - lo))) * 100, 1)

    @property
    def day_pos(self) -> float | None:
        return self._pos(self.day_low, self.day_high)

    @property
    def week52_pos(self) -> float | None:
        return self._pos(self.week52_low, self.week52_high)

    @property
    def off_52w_high_pct(self) -> float | None:
        p = self.close_price if self.close_price is not None else self.price
        if not p or not self.week52_high:
            return None
        return round((p / self.week52_high - 1) * 100, 1)

    @property
    def series(self) -> list[tuple[float, float]]:
        """Daily closes, with today's session appended — the chart feed runs a day behind the
        quote, so without this the line would stop at yesterday while the price says today."""
        pts = [(float(x), float(y)) for x, y in self.history if y is not None]
        latest = self.close_price if self.close_price is not None else self.price
        if pts and latest is not None and round(pts[-1][1], 2) != round(latest, 2):
            f = self.fetched or utcnow()
            pts.append((f.timestamp() * 1000, float(latest)))
        return pts

    @property
    def spark(self) -> dict | None:
        """A 1-year sparkline as SVG geometry: viewBox units, drawn with a non-scaling stroke."""
        pts = self.series
        if len(pts) < 8:
            return None
        ys = [y for _, y in pts]
        lo, hi = min(ys), max(ys)
        span = (hi - lo) or 1.0
        pad = 6
        n = len(pts)
        coords = [(round(i * SPARK_W / (n - 1), 2),
                   round(pad + (hi - y) / span * (SPARK_H - 2 * pad), 2)) for i, (_, y) in enumerate(pts)]
        line = " ".join(f"{x},{y}" for x, y in coords)
        area = f"M0,{SPARK_H} L" + " L".join(f"{x},{y}" for x, y in coords) + f" L{SPARK_W},{SPARK_H} Z"
        change_pct = round((ys[-1] / ys[0] - 1) * 100, 1) if ys[0] else None
        return {"w": SPARK_W, "h": SPARK_H, "points": line, "area": area,
                "direction": _direction(change_pct), "change_pct": change_pct,
                "low": lo, "high": hi, "first": ys[0], "last": ys[-1],
                "from": _ms_label(pts[0][0]), "to": _ms_label(pts[-1][0]),
                "last_x": coords[-1][0], "last_y": coords[-1][1], "n": n}


def _parse_iso(v: str | None) -> datetime | None:
    if not v:
        return None
    try:
        d = datetime.fromisoformat(v)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _ms_label(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%b %Y")


# ---------------------------------------------------------------- sources
def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json, text/plain, */*",
                      "Accept-Language": "en-US,en;q=0.9"})
    return s


def _get_json(sess: requests.Session, url: str, **params) -> dict | None:
    r = sess.get(url, params=params or None, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


NASDAQ_API = "https://api.nasdaq.com/api/quote/{sym}/{part}"
NASDAQ_PAGE = "https://www.nasdaq.com/market-activity/stocks/{sym}"


def fetch_nasdaq(symbol: str = SYMBOL, *, history: bool = True) -> Quote | None:
    """Nasdaq's public quote API — the listing venue's own feed. No key, no account."""
    sess = _session()
    sym = symbol.lower()
    info = _get_json(sess, NASDAQ_API.format(sym=sym, part="info"), assetclass="stocks")
    d = (info or {}).get("data") or {}
    primary = d.get("primaryData") or {}
    if num(primary.get("lastSalePrice")) is None:
        return None

    secondary = d.get("secondaryData") or {}
    q = Quote(symbol=d.get("symbol") or symbol.upper(),
              name=d.get("companyName"), exchange=d.get("exchange"),
              market_status=d.get("marketStatus"),
              price=num(primary.get("lastSalePrice")),
              change=num(primary.get("netChange")),
              change_pct=num(primary.get("percentageChange")),
              as_of=_clean_stamp(primary.get("lastTradeTimestamp")),
              bid=num(primary.get("bidPrice")), ask=num(primary.get("askPrice")),
              volume=num(primary.get("volume")),
              source="Nasdaq", source_url=NASDAQ_PAGE.format(sym=sym))

    # in extended hours Nasdaq puts the regular-session close in secondaryData
    if num(secondary.get("lastSalePrice")) is not None:
        q.close_price = num(secondary.get("lastSalePrice"))
        q.close_change = num(secondary.get("netChange"))
        q.close_change_pct = num(secondary.get("percentageChange"))
        q.close_as_of = _clean_stamp(secondary.get("lastTradeTimestamp"))

    ks = d.get("keyStats") or {}
    q.day_low, q.day_high = _pair((ks.get("dayrange") or {}).get("value"))
    q.week52_low, q.week52_high = _pair((ks.get("fiftyTwoWeekHighLow") or {}).get("value"))

    try:
        summary = _get_json(sess, NASDAQ_API.format(sym=sym, part="summary"), assetclass="stocks")
        sd = ((summary or {}).get("data") or {}).get("summaryData") or {}

        def val(key):
            return (sd.get(key) or {}).get("value")

        q.previous_close = num(val("PreviousClose"))
        q.avg_volume = num(val("AverageVolume"))
        q.market_cap = num(val("MarketCap"))
        q.one_year_target = num(val("OneYrTarget"))
        q.volume = q.volume if q.volume is not None else num(val("ShareVolume"))
        if q.day_low is None:                                  # summary states these high-first
            q.day_low, q.day_high = _pair(val("TodayHighLow"), order="hilo")
        if q.week52_low is None:
            q.week52_low, q.week52_high = _pair(val("FiftTwoWeekHighLow"), order="hilo")
    except Exception as exc:                                   # summary is a bonus, not the quote
        log.info("nasdaq summary unavailable for %s: %s", symbol, exc)

    if history:
        q.history, q.history_at = _nasdaq_history(sess, sym), utcnow().isoformat()
    return q


def _clean_stamp(v) -> str | None:
    s = (v or "").strip()
    return re.sub(r"^Closed at\s+", "", s) or None


def _nasdaq_history(sess: requests.Session, sym: str) -> list[list[float]]:
    today = utcnow().date()
    frm = today.replace(year=today.year - 1)
    data = _get_json(sess, NASDAQ_API.format(sym=sym, part="chart"),
                     assetclass="stocks", fromdate=frm.isoformat(), todate=today.isoformat())
    rows = ((data or {}).get("data") or {}).get("chart") or []
    out = []
    for r in rows:
        x, y = r.get("x"), r.get("y")
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            out.append([float(x), round(float(y), 4)])
    return out


YAHOO_STATES = {"REGULAR": "Open", "PRE": "Pre-Market", "PREPRE": "Pre-Market",
                "POST": "After-Hours", "POSTPOST": "After-Hours", "CLOSED": "Closed"}
YAHOO_HOSTS = ("https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com")


def fetch_yahoo(symbol: str = SYMBOL, *, history: bool = True) -> Quote | None:
    """Fallback feed. Fewer fields than Nasdaq — no market cap, no average volume."""
    sess = _session()
    last_exc = None
    for host in YAHOO_HOSTS:
        try:
            data = _get_json(sess, f"{host}/v8/finance/chart/{symbol}", range="1y", interval="1d")
            break
        except Exception as exc:
            last_exc = exc
    else:
        raise last_exc                                          # pragma: no cover - network only
    result = ((data or {}).get("chart") or {}).get("result") or []
    if not result:
        return None
    meta = result[0].get("meta") or {}
    price = meta.get("regularMarketPrice")
    prev = meta.get("chartPreviousClose") or meta.get("previousClose")
    if price is None:
        return None
    change = price - prev if prev else None
    q = Quote(symbol=meta.get("symbol") or symbol.upper(),
              name=meta.get("longName") or meta.get("shortName"),
              exchange=meta.get("fullExchangeName") or meta.get("exchangeName"),
              currency=meta.get("currency") or "USD",
              price=float(price), change=change,
              change_pct=(change / prev * 100) if change is not None and prev else None,
              market_status=YAHOO_STATES.get((meta.get("marketState") or "").upper()),
              previous_close=prev,
              day_low=meta.get("regularMarketDayLow"), day_high=meta.get("regularMarketDayHigh"),
              week52_low=meta.get("fiftyTwoWeekLow"), week52_high=meta.get("fiftyTwoWeekHigh"),
              volume=meta.get("regularMarketVolume"),
              source="Yahoo Finance", source_url=f"https://finance.yahoo.com/quote/{symbol}")
    t = meta.get("regularMarketTime")
    if isinstance(t, (int, float)):
        q.as_of = datetime.fromtimestamp(t, timezone.utc).strftime("%b %-d, %Y %H:%M UTC")

    if history:
        stamps = result[0].get("timestamp") or []
        closes = (((result[0].get("indicators") or {}).get("quote") or [{}])[0]).get("close") or []
        q.history = [[float(s) * 1000, round(float(c), 4)]
                     for s, c in zip(stamps, closes) if c is not None]
        q.history_at = utcnow().isoformat()
    return q


SOURCES = (fetch_nasdaq, fetch_yahoo)


# ---------------------------------------------------------------- cache + refresh
_lock = threading.Lock()
_mem: dict[str, Quote] = {}
_inflight: set[str] = set()
_retry_after: dict[str, float] = {}


def _load(db: Session, symbol: str) -> Quote | None:
    from .models import MarketQuote
    row = db.get(MarketQuote, symbol)
    return Quote.from_json(row.payload) if row else None


def _store(db: Session, q: Quote) -> None:
    from .models import MarketQuote
    row = db.get(MarketQuote, q.symbol)
    if row is None:
        row = MarketQuote(symbol=q.symbol)
        db.add(row)
    row.payload, row.source, row.fetched_at = q.to_json(), q.source, utcnow()
    db.commit()


def cached(db: Session, symbol: str = SYMBOL) -> Quote | None:
    """Whatever we already have, without touching the network."""
    q = _mem.get(symbol)
    if q is None:
        q = _load(db, symbol)
        if q is not None:
            _mem[symbol] = q
    return q


def refresh(db: Session, symbol: str = SYMBOL, previous: Quote | None = None) -> Quote | None:
    """Fetch from the first source that answers; keep the previous history if it is fresh."""
    if not enabled():
        return None
    previous = previous if previous is not None else cached(db, symbol)
    want_history = previous is None or not previous.history or previous.history_age_seconds > HISTORY_TTL
    errors = []
    for source in SOURCES:
        try:
            q = source(symbol, history=want_history)
        except Exception as exc:
            errors.append(f"{source.__name__}: {exc}")
            continue
        if q is None:
            errors.append(f"{source.__name__}: no quote in response")
            continue
        if not q.history and previous is not None:
            q.history, q.history_at = previous.history, previous.history_at
        q.fetched_at = utcnow().isoformat()
        _mem[symbol] = q
        try:
            _store(db, q)
        except Exception as exc:                                # a cache write must never 500 a page
            db.rollback()
            log.warning("could not cache %s quote: %s", symbol, exc)
        _retry_after.pop(symbol, None)
        return q
    _retry_after[symbol] = utcnow().timestamp() + ERROR_BACKOFF
    log.warning("no market source answered for %s (%s)", symbol, "; ".join(errors))
    return None


def _refresh_in_background(symbol: str) -> None:
    from .db import SessionLocal
    try:
        with SessionLocal() as db:
            refresh(db, symbol)
    except Exception as exc:                                    # pragma: no cover - background only
        log.warning("background quote refresh failed for %s: %s", symbol, exc)
    finally:
        with _lock:
            _inflight.discard(symbol)


def get_quote(db: Session, symbol: str = SYMBOL, *, block: bool = False) -> Quote | None:
    """The one entry point. `block=False` (pages) never waits on the network; it serves the
    cache and refreshes behind the request. `block=True` (the JSON endpoint) will wait."""
    q = cached(db, symbol)
    if q is not None and q.age_seconds < QUOTE_TTL:
        return q
    if not enabled() or utcnow().timestamp() < _retry_after.get(symbol, 0):
        return q
    if block:
        return refresh(db, symbol, previous=q) or q
    with _lock:
        if symbol in _inflight:
            return q
        _inflight.add(symbol)
    threading.Thread(target=_refresh_in_background, args=(symbol,), daemon=True).start()
    return q


def reset_cache() -> None:
    """Tests and `make app-dev` reloads."""
    _mem.clear()
    _retry_after.clear()
    _inflight.clear()


# ---------------------------------------------------------------- display formatting
# One place formats these numbers, so the server-rendered panel and the JSON the page
# polls can never drift apart.
MINUS = "−"


def money(v, dp: int = 2, dash: str = "—") -> str:
    return f"${v:,.{dp}f}" if v is not None else dash


def signed(v, dp: int = 2, dash: str = "—") -> str:
    if v is None:
        return dash
    return f"{'+' if v > 0 else (MINUS if v < 0 else '')}{abs(v):,.{dp}f}"


def pct(v, dp: int = 2, dash: str = "—") -> str:
    if v is None:
        return dash
    return f"{'+' if v > 0 else (MINUS if v < 0 else '')}{abs(v):,.{dp}f}%"


def compact(v, prefix: str = "", dash: str = "—") -> str:
    """16412542689 -> '$16.41bn'; 44413404 -> '44.41m'; 8213 -> '8,213'."""
    if v is None:
        return dash
    for cut, suffix in ((1e12, "tn"), (1e9, "bn"), (1e6, "m")):
        if abs(v) >= cut:
            return f"{prefix}{v / cut:,.2f}{suffix}"
    return f"{prefix}{v:,.0f}"


def band(lo, hi, dp: int = 2, dash: str = "—") -> str:
    return f"${lo:,.{dp}f} – ${hi:,.{dp}f}" if lo is not None and hi is not None else dash


def display(q: Quote | None) -> dict[str, str | None]:
    """Every figure on the ticker as the string it renders as."""
    if q is None:
        return {}
    return {
        "symbol": q.symbol, "name": q.name, "exchange": q.exchange,
        "price": money(q.price), "change": signed(q.change), "change_pct": pct(q.change_pct),
        "direction": q.direction, "as_of": q.as_of, "session": q.session_label,
        "headline_label": q.headline_label, "ext_label": q.ext_label,
        "close_price": money(q.close_price), "close_change": signed(q.close_change),
        "close_change_pct": pct(q.close_change_pct), "close_direction": q.close_direction,
        "close_as_of": q.close_as_of, "extended_hours": q.extended_hours,
        "previous_close": money(q.previous_close),
        "day_range": band(q.day_low, q.day_high),
        "week52_range": band(q.week52_low, q.week52_high),
        "volume": compact(q.volume), "avg_volume": compact(q.avg_volume),
        "market_cap": compact(q.market_cap, "$"),
        "one_year_target": money(q.one_year_target),
        "bid": money(q.bid), "ask": money(q.ask),
        "off_52w_high": pct(q.off_52w_high_pct, dp=1),
        "day_pos": q.day_pos, "week52_pos": q.week52_pos,
        "source": q.source, "source_url": q.source_url,
        "fetched_at": q.fetched_at, "stale": q.is_stale,
    }
