import hashlib
from pathlib import Path

import pytest

from src.config import Settings
from src.models.domain import SourceType
from src.services import site_config


@pytest.fixture
def sites_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from src.config import get_settings

    (tmp_path / "sites").mkdir()
    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    get_settings.cache_clear()
    yield tmp_path / "sites"
    get_settings.cache_clear()


def write(sites_dir: Path, name: str, text: str) -> None:
    (sites_dir / f"{name}.yaml").write_text(text)


FULL = """
site_id: shop
sources: [cdn, origin]
cdn_field_map: example
request_id_header: X-Request-ID
ingest_token_sha256: abc123
no_data_alert_minutes: 30
key_pages: [/pricing]
conversion_pages: [/signup]
journeys:
  - id: signup
    critical: true
    steps: [/pricing, /signup]
  - id: docs
    steps: [/docs]
access_policy:
  allow: [/pricing]
  block: [/admin]
  robots_disallow: [/private]
site_pages: [/pricing, /docs/api]
"""


def test_loads_all_fields(sites_dir: Path) -> None:
    write(sites_dir, "shop", FULL)
    cfg = site_config.load_site_config("shop")
    assert cfg.site_id == "shop"
    assert cfg.sources == [SourceType.CDN, SourceType.ORIGIN]
    assert cfg.cdn_field_map == "example"
    assert cfg.request_id_header == "X-Request-ID"
    assert cfg.ingest_token_sha256 == "abc123"
    assert cfg.no_data_alert_minutes == 30
    assert cfg.key_pages == ["/pricing"]
    assert cfg.conversion_pages == ["/signup"]
    assert [j.id for j in cfg.journeys] == ["signup", "docs"]
    assert cfg.journeys[0].critical is True
    assert cfg.journeys[1].critical is False
    assert cfg.site_pages == ["/pricing", "/docs/api"]
    assert cfg.pairs_sources is True


def test_defaults(sites_dir: Path) -> None:
    write(sites_dir, "min", "site_id: min\nsources: [origin]\n")
    cfg = site_config.load_site_config("min")
    assert cfg.no_data_alert_minutes == Settings().no_data_alert_minutes
    assert cfg.key_pages == []
    assert cfg.journeys == []
    assert cfg.site_pages == []
    assert cfg.ingest_token_sha256 is None
    assert cfg.pairs_sources is False


def test_site_id_defaults_to_file_name(sites_dir: Path) -> None:
    write(sites_dir, "abc", "sources: [origin]\n")
    assert site_config.load_site_config("abc").site_id == "abc"


def test_list_sites(sites_dir: Path) -> None:
    write(sites_dir, "b", "sources: [origin]\n")
    write(sites_dir, "a", "sources: [cdn]\n")
    assert site_config.list_sites() == ["a", "b"]


def test_unknown_site(sites_dir: Path) -> None:
    with pytest.raises(site_config.SiteNotFound):
        site_config.load_site_config("nope")


@pytest.mark.parametrize("bad", ["../etc/passwd", "a/b", "", ".hidden", "A B"])
def test_unsafe_site_id_is_not_found(sites_dir: Path, bad: str) -> None:
    with pytest.raises(site_config.SiteNotFound):
        site_config.load_site_config(bad)


def test_site_pages_from_file(sites_dir: Path) -> None:
    (sites_dir / "pages.txt").write_text(
        "# key content\n/pricing\n\nhttps://shop.example/docs/api?x=1\n"
    )
    write(sites_dir, "shop", "sources: [origin]\nsite_pages: {file: pages.txt}\n")
    assert site_config.load_site_config("shop").site_pages == ["/pricing", "/docs/api?x=1"]


def test_token_check(sites_dir: Path) -> None:
    digest = hashlib.sha256(b"dev-token").hexdigest()
    write(sites_dir, "shop", f"sources: [origin]\ningest_token_sha256: {digest}\n")
    cfg = site_config.load_site_config("shop")
    assert site_config.token_matches(cfg, "dev-token")
    assert not site_config.token_matches(cfg, "other")
    assert not site_config.token_matches(cfg, "")


def test_token_check_without_token_configured(sites_dir: Path) -> None:
    write(sites_dir, "shop", "sources: [origin]\n")
    assert not site_config.token_matches(site_config.load_site_config("shop"), "x")


def test_access_policy_most_specific_wins() -> None:
    policy = site_config.AccessPolicy(
        allow=["/docs/public"], block=["/docs", "/admin"], robots_disallow=["/private"]
    )
    assert policy.blocked_by_intent("/admin/users")
    assert policy.blocked_by_intent("/docs/internal")
    assert not policy.blocked_by_intent("/docs/public/a")
    assert policy.blocked_by_intent("/private?x=1")
    assert not policy.blocked_by_intent("/pricing")


def test_example_site_file_loads() -> None:
    cfg = site_config.load_site_config("example")
    assert cfg.ingest_token_sha256 == hashlib.sha256(b"dev-token").hexdigest()
    assert cfg.pairs_sources
    assert cfg.journeys


def test_cdn_field_map(sites_dir: Path) -> None:
    (sites_dir.parent / "cdn").mkdir()
    (sites_dir.parent / "cdn" / "x.yaml").write_text("format: json\npath: p\n")
    assert site_config.load_cdn_field_map("x") == {"format": "json", "path": "p"}
    with pytest.raises(site_config.SiteNotFound):
        site_config.load_cdn_field_map("missing")


def test_cdn_bucket_block(config_dir, settings):
    (config_dir / "sites" / "withbucket.yaml").write_text(
        "site_id: withbucket\nsources: [cdn]\ncdn_bucket: {bucket: b1, prefix: p/}\n"
    )
    (config_dir / "sites" / "plain.yaml").write_text("site_id: plain\nsources: [origin]\n")
    got = site_config.load_site_config("withbucket").cdn_bucket
    assert (got.bucket, got.prefix, got.source) == ("b1", "p/", "cdn")
    assert site_config.load_site_config("plain").cdn_bucket is None
