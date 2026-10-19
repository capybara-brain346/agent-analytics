"""Shared fixtures.

Database fixtures are lazy: a test that does not use `db_url`, `conn`, `pool`, `client` or a
fixture built on them never touches Postgres.

- `db_url`: one fresh database `aa_test_<random>` for the whole pytest session, migrated with
  `alembic upgrade head`, dropped at the end. The server comes from TEST_DATABASE_SERVER_URL
  (default: the dev server on localhost:55432).
- `clean_db`: TRUNCATE of every table (except alembic_version) before each test.
- `conn`: one AsyncConnection per test, AUTOCOMMIT ON. Every statement commits at once, so data
  is visible to other connections. A test that needs a transaction writes
  `async with conn.transaction(): ...`.
- `pool`: opens the `src.store.db` pool on the test database (API tests).
- `client`: httpx.AsyncClient on the FastAPI app, with the pool open.
- `config_dir`: a temporary copy of apps/api/config, wired into settings (CONFIG_DIR).
- Settings ignore apps/api/.env. Only process environment variables apply.
"""

import os
import secrets
import shutil
from collections.abc import AsyncIterator, Iterator
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import psycopg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from psycopg import AsyncConnection, sql

from src.config import Settings, get_settings
from src.store import db
from tests.factories import NOW

API_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SERVER_URL = "postgresql://agent_analytics:agent_analytics@localhost:55432/agent_analytics"

# Tests use the code defaults, not the developer's apps/api/.env (OFFLINE, API_TOKEN, LLM keys).
Settings.model_config["env_file"] = None


def _server_url() -> str:
    return os.environ.get("TEST_DATABASE_SERVER_URL", DEFAULT_SERVER_URL)


def _with_database(url: str, name: str) -> str:
    return urlsplit(url)._replace(path=f"/{name}").geturl()


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    name = f"aa_test_{secrets.token_hex(4)}"
    server = _server_url()
    with psycopg.connect(server, autocommit=True) as admin:
        admin.execute(sql.SQL("create database {}").format(sql.Identifier(name)))
    url = _with_database(server, name)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    try:
        command.upgrade(Config(str(API_ROOT / "alembic.ini")), "head")
        yield url
    finally:
        get_settings.cache_clear()
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with psycopg.connect(server, autocommit=True) as admin:
            admin.execute(
                sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name))
            )


@pytest.fixture
def settings(request: pytest.FixtureRequest) -> Iterator[Settings]:
    # Load db_url first when the test uses the database, so DATABASE_URL is set before Settings.
    if "db_url" in request.fixturenames:
        request.getfixturevalue("db_url")
    get_settings.cache_clear()
    yield get_settings()
    get_settings.cache_clear()


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    target = tmp_path / "config"
    shutil.copytree(API_ROOT / "config", target)
    monkeypatch.setenv("CONFIG_DIR", str(target))
    get_settings.cache_clear()
    yield target
    get_settings.cache_clear()


@pytest.fixture
def now() -> datetime:
    return NOW


@pytest_asyncio.fixture
async def clean_db(db_url: str) -> None:
    async with await AsyncConnection.connect(db_url, autocommit=True) as c:
        cur = await c.execute(
            """
            select quote_ident(relname) from pg_class
            where relnamespace = 'public'::regnamespace and relkind in ('r', 'p')
              and not relispartition and relname <> 'alembic_version'
            """
        )
        tables = [row[0] for row in await cur.fetchall()]
        await c.execute("truncate " + ", ".join(tables) + " restart identity cascade")


@pytest_asyncio.fixture
async def conn(db_url: str, clean_db: None, settings: Settings) -> AsyncIterator[AsyncConnection]:
    async with await AsyncConnection.connect(db_url, autocommit=True) as c:
        yield c


@pytest_asyncio.fixture
async def pool(db_url: str, clean_db: None, settings: Settings) -> AsyncIterator[object]:
    await db.open_pool(settings)
    await db.pool().wait()
    yield db.pool()
    await db.close_pool()


@pytest_asyncio.fixture
async def client(pool: object) -> AsyncIterator[httpx.AsyncClient]:
    from src.main import create_app

    transport = httpx.ASGITransport(app=create_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
