import pytest

from src.config import get_settings
from src.services import ingest


@pytest.fixture
def tight(monkeypatch):
    monkeypatch.setenv("INGEST_RATE_PER_MINUTE", "2")
    monkeypatch.setenv("INGEST_BYTES_PER_DAY", "100")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_request_window_slides(tight):
    assert await ingest.check_rate_limit("a", now=0.0)
    assert await ingest.check_rate_limit("a", now=10.0)
    assert not await ingest.check_rate_limit("a", now=59.0)
    assert await ingest.check_rate_limit("a", now=60.5)


async def test_sites_are_independent(tight):
    for t in (0.0, 1.0):
        assert await ingest.check_rate_limit("a", now=t)
    assert not await ingest.check_rate_limit("a", now=2.0)
    assert await ingest.check_rate_limit("b", now=2.0)


async def test_byte_quota_slides_over_a_day(tight):
    ingest.record_bytes("a", 90, now=0.0)
    assert not await ingest.check_rate_limit("a", size_hint=20, now=1.0)
    assert await ingest.check_rate_limit("a", size_hint=10, now=2.0)
    assert await ingest.check_rate_limit("a", size_hint=100, now=86_401.0)
