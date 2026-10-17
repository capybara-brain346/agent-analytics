from pathlib import Path

import pytest

from src.routes.ingest import inbox_dependency
from src.services import ingest
from tests.fakes import MemoryInbox

TOKEN = "dev-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
TOKEN_SHA = "c91cbbedf8c712e8e2b7517ddeca8fe4fde839ebd8339e0b2001363002b37712"


@pytest.fixture(autouse=True)
def fresh_limits():
    ingest.reset_limits()
    yield
    ingest.reset_limits()


@pytest.fixture
def inbox() -> MemoryInbox:
    return MemoryInbox()


@pytest.fixture
def api(config_dir: Path, client, inbox: MemoryInbox):
    # One-source site "solo" (origin only) next to "example" (cdn + origin).
    (config_dir / "sites" / "solo.yaml").write_text(
        f"site_id: solo\nsources: [origin]\ningest_token_sha256: {TOKEN_SHA}\n"
    )
    app = client._transport.app
    app.dependency_overrides[inbox_dependency] = lambda: inbox
    yield client
    app.dependency_overrides.clear()
