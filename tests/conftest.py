import pytest
from app import market


@pytest.fixture(autouse=True)
def no_market_fetch(monkeypatch):
    """Tests never reach the market feed: MARKET_DATA=off, and the process cache starts empty.
    Tests that want a quote stub one in (see tests/test_market.py)."""
    monkeypatch.setenv("MARKET_DATA", "off")
    market.reset_cache()
    yield
    market.reset_cache()
