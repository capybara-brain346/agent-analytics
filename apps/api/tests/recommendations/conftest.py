import textwrap
from pathlib import Path

import pytest

from src.config import get_settings

SITE = """
site_id: example
sources: [origin]
key_pages: [/pricing, /products, /docs/api, /private/plans]
conversion_pages: [/signup, /checkout]
journeys:
  - id: signup
    critical: true
    steps: [/pricing, /signup, /signup/confirm]
  - id: docs
    steps: [/docs, /docs/api]
access_policy:
  allow: [/docs]
  block: [/admin]
  robots_disallow: [/private]
"""


@pytest.fixture(autouse=True)
def site_and_llm(config_dir: Path, monkeypatch: pytest.MonkeyPatch):
    (config_dir / "sites" / "example.yaml").write_text(textwrap.dedent(SITE))
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
