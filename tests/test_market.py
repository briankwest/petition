"""The IREN ticker: parsing the public feeds, the cache, and the panel on /iren."""
import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.main import create_app
from app import market
from app.models import MarketQuote


# ---- the shapes the two upstream feeds actually return (trimmed) -------------------
NASDAQ_INFO = {
    "data": {
        "symbol": "IREN", "companyName": "IREN Limited Ordinary Shares", "exchange": "NASDAQ-GS",
        "marketStatus": "After-Hours",
        "primaryData": {"lastSalePrice": "$41.2907", "netChange": "-0.3593", "percentageChange": "-0.86%",
                        "deltaIndicator": "down", "lastTradeTimestamp": "Sep 3, 2026 6:14 PM ET",
                        "bidPrice": "$41.24", "askPrice": "$41.31", "volume": "44,902,322.096396"},
        "secondaryData": {"lastSalePrice": "$41.65", "netChange": "+2.05", "percentageChange": "+5.18%",
                          "lastTradeTimestamp": "Closed at Sep 3, 2026 4:00 PM ET"},
        "keyStats": {"fiftyTwoWeekHighLow": {"value": "25.31 - 76.87"}, "dayrange": {"value": "39.03 - 41.82"}},
    },
    "status": {"rCode": 200},
}
NASDAQ_SUMMARY = {
    "data": {"summaryData": {
        "OneYrTarget": {"value": "$80.00"}, "TodayHighLow": {"value": "$41.82/$39.03"},
        "ShareVolume": {"value": "44,902,065.096396"}, "AverageVolume": {"value": "44,413,404"},
        "PreviousClose": {"value": "$39.60"}, "FiftTwoWeekHighLow": {"value": "$76.87/$25.31"},
        "MarketCap": {"value": "16,412,542,689"}, "AnnualizedDividend": {"value": "N/A"},
    }},
    "status": {"rCode": 200},
}
NASDAQ_CHART = {"data": {"chart": [
    {"z": {"close": str(28 + i % 7), "dateTime": "9/3/2025"}, "x": 1756857600000 + i * 86400000, "y": 28 + i % 7}
    for i in range(40)]}, "status": {"rCode": 200}}


def nasdaq_stub(monkeypatch):
    def fake(sess, url, **params):
        if url.endswith("/info"):
            return NASDAQ_INFO
        if url.endswith("/summary"):
            return NASDAQ_SUMMARY
        if url.endswith("/chart"):
            return NASDAQ_CHART
        raise AssertionError(url)
    monkeypatch.setattr(market, "_get_json", fake)


# ---- helpers ----------------------------------------------------------------------
def test_num_parses_the_shapes_the_feeds_use():
    assert market.num("$41.2907") == 41.2907
    assert market.num("44,902,322.096396") == 44902322.096396
    assert market.num("-0.86%") == -0.86
    assert market.num("+2.05") == 2.05
    assert market.num(41) == 41.0
    for junk in ("N/A", "", "--", None, "abc", {}):
        assert market.num(junk) is None


def test_pair_reads_both_range_orders():
    assert market._pair("25.31 - 76.87") == (25.31, 76.87)
    assert market._pair("$41.82/$39.03", order="hilo") == (39.03, 41.82)
    assert market._pair("nonsense") == (None, None)


def test_formatting_is_signed_and_compact():
    assert market.money(39.6) == "$39.60"
    assert market.signed(2.05) == "+2.05" and market.signed(-0.36) == "−0.36"
    assert market.pct(-0.86) == "−0.86%"
    assert market.compact(16412542689, "$") == "$16.41bn"
    assert market.compact(44413404) == "44.41m"
    assert market.compact(8213) == "8,213"
    assert market.band(25.31, 76.87) == "$25.31 – $76.87"
    assert market.money(None) == "—" and market.compact(None) == "—"


# ---- normalizing the Nasdaq payload ------------------------------------------------
def test_nasdaq_quote_is_normalized(monkeypatch):
    nasdaq_stub(monkeypatch)
    q = market.fetch_nasdaq("IREN")
    assert (q.symbol, q.exchange, q.source) == ("IREN", "NASDAQ-GS", "Nasdaq")
    assert q.price == 41.2907 and q.change == -0.3593 and q.change_pct == -0.86
    # in extended hours the regular-session close is the headline, and "Closed at " is dropped
    assert q.extended_hours and q.close_price == 41.65
    assert q.close_as_of == "Sep 3, 2026 4:00 PM ET"
    assert q.headline_label == "At the close" and q.ext_label == "After hours"
    assert (q.day_low, q.day_high) == (39.03, 41.82)
    assert (q.week52_low, q.week52_high) == (25.31, 76.87)
    assert q.market_cap == 16412542689 and q.avg_volume == 44413404
    assert q.previous_close == 39.6 and q.one_year_target == 80.0
    assert len(q.history) == 40


def test_market_open_has_no_second_price_line(monkeypatch):
    info = json.loads(json.dumps(NASDAQ_INFO))
    info["data"]["marketStatus"] = "Open"
    info["data"]["secondaryData"] = {"lastSalePrice": "", "netChange": ""}
    monkeypatch.setattr(market, "_get_json", lambda s, url, **kw: {
        "/info": info, "/summary": NASDAQ_SUMMARY, "/chart": NASDAQ_CHART}[
            "/" + url.rsplit("/", 1)[1]])
    q = market.fetch_nasdaq("IREN")
    assert not q.extended_hours and q.close_price is None
    assert q.headline_label == "Live"


def test_a_quoteless_payload_is_not_a_quote(monkeypatch):
    monkeypatch.setattr(market, "_get_json", lambda s, url, **kw: {"data": None})
    assert market.fetch_nasdaq("IREN") is None


def test_summary_failure_still_yields_a_quote(monkeypatch):
    def fake(sess, url, **params):
        if url.endswith("/summary"):
            raise RuntimeError("500")
        return {"/info": NASDAQ_INFO, "/chart": NASDAQ_CHART}["/" + url.rsplit("/", 1)[1]]
    monkeypatch.setattr(market, "_get_json", fake)
    q = market.fetch_nasdaq("IREN")
    assert q.price == 41.2907 and q.market_cap is None       # the bonus fields are simply absent
    assert (q.day_low, q.day_high) == (39.03, 41.82)         # these come from info, not summary


def test_yahoo_fallback_is_normalized(monkeypatch):
    payload = {"chart": {"result": [{
        "meta": {"symbol": "IREN", "longName": "IREN Limited", "fullExchangeName": "NasdaqGS",
                 "currency": "USD", "marketState": "REGULAR", "regularMarketPrice": 41.65,
                 "chartPreviousClose": 39.6, "regularMarketDayLow": 39.03, "regularMarketDayHigh": 41.82,
                 "fiftyTwoWeekLow": 25.31, "fiftyTwoWeekHigh": 76.87, "regularMarketVolume": 44902065,
                 "regularMarketTime": 1788552000},
        "timestamp": [1756857600, 1756944000, 1757030400],
        "indicators": {"quote": [{"close": [28.21, None, 26.13]}]}}]}}
    monkeypatch.setattr(market, "_get_json", lambda s, url, **kw: payload)
    q = market.fetch_yahoo("IREN")
    assert q.source == "Yahoo Finance" and q.price == 41.65
    assert round(q.change, 2) == 2.05 and round(q.change_pct, 2) == 5.18
    assert q.market_status == "Open" and not q.extended_hours
    assert q.history == [[1756857600000.0, 28.21], [1757030400000.0, 26.13]]   # gaps dropped


# ---- the sparkline ------------------------------------------------------------------
def test_spark_geometry_spans_the_box_and_ends_at_the_last_close():
    q = market.Quote(close_price=40.0, fetched_at="2026-09-03T22:00:00+00:00",
                     history=[[1756857600000 + i * 86400000, 10.0 + i] for i in range(20)])
    sp = q.spark
    xs = [float(p.split(",")[0]) for p in sp["points"].split()]
    assert xs[0] == 0 and xs[-1] == market.SPARK_W and xs == sorted(xs)
    assert sp["last"] == 40.0 and sp["n"] == 21          # today's session appended to the daily closes
    assert sp["direction"] == "up" and sp["change_pct"] == 300.0
    assert sp["area"].startswith(f"M0,{market.SPARK_H}") and sp["area"].endswith("Z")


def test_spark_needs_a_series_to_draw():
    assert market.Quote(history=[[1, 2.0]]).spark is None
    assert market.Quote().spark is None


def test_todays_close_is_not_appended_twice():
    hist = [[1756857600000 + i * 86400000, 10.0] for i in range(20)]
    q = market.Quote(close_price=10.0, history=hist)
    assert len(q.series) == 20


# ---- position in a band -------------------------------------------------------------
def test_band_position_is_clamped_and_uses_the_regular_close():
    q = market.Quote(price=99.0, close_price=50.0, week52_low=25.0, week52_high=75.0)
    assert q.week52_pos == 50.0 and q.off_52w_high_pct == -33.3
    assert market.Quote(price=10.0, day_low=5.0, day_high=5.0).day_pos is None
    assert market.Quote(price=10.0).day_pos is None


# ---- caching ------------------------------------------------------------------------
@pytest.fixture
def db():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    with sessionmaker(bind=eng, expire_on_commit=False)() as s:
        yield s


def test_refresh_stores_the_quote_and_serves_it_from_cache(db, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)
    calls = []
    real = market.fetch_nasdaq
    monkeypatch.setattr(market, "SOURCES", (lambda *a, **kw: (calls.append(1), real(*a, **kw))[1],))

    q = market.get_quote(db, block=True)
    assert q and q.price == 41.2907 and q.fetched_at and not q.is_stale
    assert db.get(MarketQuote, "IREN").source == "Nasdaq"
    assert len(calls) == 1

    market.get_quote(db, block=True)                      # inside the TTL: no second fetch
    assert len(calls) == 1


def test_cache_survives_a_restart(db, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)
    stored = market.get_quote(db, block=True)
    market.reset_cache()                                  # as if the process had been replaced
    assert market.cached(db).price == stored.price


def test_a_dead_feed_serves_the_last_good_quote(db, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)
    good = market.get_quote(db, block=True)
    good.fetched_at = "2026-09-01T00:00:00+00:00"         # age it past the TTL
    market._store(db, good)
    market.reset_cache()

    def dead(*a, **kw):
        raise RuntimeError("connection refused")
    monkeypatch.setattr(market, "SOURCES", (dead, dead))
    served = market.get_quote(db, block=True)
    assert served is not None and served.price == good.price
    assert served.fetched_at == "2026-09-01T00:00:00+00:00"


def test_failure_backs_off_before_trying_again(db, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    tries = []
    monkeypatch.setattr(market, "SOURCES", (lambda *a, **kw: tries.append(1) or None,))
    assert market.get_quote(db, block=True) is None
    assert market.get_quote(db, block=True) is None
    assert len(tries) == 1                                # the second call is inside the backoff


def _age(db, q, fetched, history_at):
    q.fetched_at, q.history_at = fetched, history_at
    market._store(db, q)
    market.reset_cache()


def test_a_stale_quote_with_fresh_history_does_not_refetch_the_year(db, monkeypatch):
    """A quote goes stale every five minutes; a year of daily closes does not."""
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)
    first = market.get_quote(db, block=True)
    assert len(first.history) == 40
    asked = []

    def source(symbol, history=True):
        asked.append(history)
        return market.Quote(symbol=symbol, price=1.0, source="stub")
    monkeypatch.setattr(market, "SOURCES", (source,))

    _age(db, first, "2026-09-01T00:00:00+00:00", market.utcnow().isoformat())
    again = market.get_quote(db, block=True)
    assert asked == [False]
    assert again.price == 1.0 and len(again.history) == 40      # carried over from the old quote


def test_history_is_refetched_once_it_ages_out(db, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)
    first = market.get_quote(db, block=True)
    asked = []

    def source(symbol, history=True):
        asked.append(history)
        return market.Quote(symbol=symbol, price=1.0, source="stub")
    monkeypatch.setattr(market, "SOURCES", (source,))

    _age(db, first, "2026-09-01T00:00:00+00:00", "2026-08-01T00:00:00+00:00")
    market.get_quote(db, block=True)
    assert asked == [True]


def test_off_switch_never_touches_the_network(db, monkeypatch):
    monkeypatch.setattr(market, "SOURCES", (lambda *a, **kw: pytest.fail("fetched with MARKET_DATA=off"),))
    assert market.get_quote(db, block=True) is None
    assert market.refresh(db) is None


def test_a_stale_payload_shape_is_tolerated():
    assert market.Quote.from_json('{"symbol":"IREN","price":41.0,"gone_field":1}').price == 41.0
    assert market.Quote.from_json("not json") is None
    assert market.Quote.from_json("[1,2]") is None


# ---- the page and the endpoint -------------------------------------------------------
@pytest.fixture
def client():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(eng)
    app = create_app(engine=eng)
    with TestClient(app, base_url="http://testserver") as c:
        yield c


def test_iren_renders_without_a_quote(client):
    html = client.get("/iren").text
    assert 'class="ticker ticker--empty"' in html
    assert "its public quote feed has not answered" in html
    assert "<div data-tk-body hidden>" in html             # the figures are there for the script to fill
    assert html.count("<h1>") == 1                         # the dossier itself is unharmed


def test_quote_endpoint_says_so_when_the_feed_is_off(client):
    r = client.get("/api/quote.json")
    assert r.status_code == 503 and r.json() == {"ok": False, "symbol": "IREN"}
    assert r.headers["cache-control"] == "no-store"


def test_quote_endpoint_and_panel_render_the_figures(client, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)

    r = client.get("/api/quote.json")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["display"]["close_price"] == "$41.65"
    assert body["display"]["market_cap"] == "$16.41bn"
    assert body["display"]["headline_label"] == "At the close"
    assert body["spark"]["points"] and body["spark"]["direction"] in ("up", "down", "flat")

    html = client.get("/iren").text                       # now server-rendered from the cache
    assert 'class="ticker"' in html and 'class="ticker ticker--empty"' not in html
    assert "<div data-tk-body >" in html or "<div data-tk-body>" in html
    assert "$41.65" in html and "$16.41bn" in html and "$25.31 – $76.87" in html
    assert "At the close" in html and "44.41m" in html
    assert "Nothing here is investment advice" in html


def test_the_captain_can_switch_the_panel_off(client, db, monkeypatch):
    monkeypatch.setenv("MARKET_DATA", "on")
    nasdaq_stub(monkeypatch)
    assert 'id="ticker"' in client.get("/iren").text

    from app.settings import Settings
    from app.db import get_db
    s = Settings(next(client.app.dependency_overrides[get_db]()))
    s.set("public_show_market", False)
    s.db.commit()

    html = client.get("/iren").text
    assert 'id="ticker"' not in html and 'id="market"' not in html
    assert "What the company actually does" in html          # the dossier is otherwise untouched
    r = client.get("/api/quote.json")
    assert r.status_code == 503 and r.json()["ok"] is False
