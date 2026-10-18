import pytest

from src.config import get_settings
from src.routes.ingest import inbox_dependency
from src.services import ingest
from tests.fakes import MemoryInbox


@pytest.fixture
def inbox(config_dir, client, monkeypatch) -> MemoryInbox:
    monkeypatch.setenv("OFFLINE", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")
    get_settings.cache_clear()
    ingest.reset_limits()
    memory = MemoryInbox()
    app = client._transport.app
    app.dependency_overrides[inbox_dependency] = lambda: memory
    yield memory
    app.dependency_overrides.clear()
    ingest.reset_limits()
