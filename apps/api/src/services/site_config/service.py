import hashlib
import hmac
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import yaml

from src.config import get_settings
from src.models.domain import SourceType

SITE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


class SiteNotFound(LookupError):
    pass


@dataclass(frozen=True)
class Journey:
    id: str
    steps: list[str]
    critical: bool = False


@dataclass(frozen=True)
class AccessPolicy:
    allow: list[str] = field(default_factory=list)
    block: list[str] = field(default_factory=list)
    robots_disallow: list[str] = field(default_factory=list)

    def blocked_by_intent(self, path: str) -> bool:
        path = urlsplit(path).path or "/"
        allowed = _longest_prefix(path, self.allow)
        blocked = _longest_prefix(path, [*self.block, *self.robots_disallow])
        return blocked > allowed


def _longest_prefix(path: str, prefixes: list[str]) -> int:
    lengths = [len(p) for p in prefixes if path.startswith(p)]
    return max(lengths, default=-1)


@dataclass(frozen=True)
class CdnBucket:
    bucket: str
    prefix: str = ""
    source: str = "cdn"


@dataclass(frozen=True)
class SiteConfig:
    site_id: str
    sources: list[SourceType]
    cdn_field_map: str | None = None
    request_id_header: str | None = None
    ingest_token_sha256: str | None = None
    no_data_alert_minutes: int = 60
    key_pages: list[str] = field(default_factory=list)
    conversion_pages: list[str] = field(default_factory=list)
    journeys: list[Journey] = field(default_factory=list)
    access_policy: AccessPolicy = field(default_factory=AccessPolicy)
    site_pages: list[str] = field(default_factory=list)
    cdn_bucket: CdnBucket | None = None

    @property
    def pairs_sources(self) -> bool:
        return SourceType.CDN in self.sources and SourceType.ORIGIN in self.sources


def _sites_dir() -> Path:
    return get_settings().config_dir / "sites"


def list_sites() -> list[str]:
    return sorted(p.stem for p in _sites_dir().glob("*.yaml") if SITE_ID.match(p.stem))


def load_site_config(site_id: str) -> SiteConfig:
    if not SITE_ID.match(site_id):
        raise SiteNotFound(site_id)
    path = _sites_dir() / f"{site_id}.yaml"
    if not path.is_file():
        raise SiteNotFound(site_id)
    raw = yaml.safe_load(path.read_text()) or {}
    policy = raw.get("access_policy") or {}
    return SiteConfig(
        site_id=raw.get("site_id") or site_id,
        sources=[SourceType(s) for s in raw.get("sources") or []],
        cdn_field_map=raw.get("cdn_field_map"),
        request_id_header=raw.get("request_id_header"),
        ingest_token_sha256=raw.get("ingest_token_sha256"),
        no_data_alert_minutes=int(
            raw.get("no_data_alert_minutes") or get_settings().no_data_alert_minutes
        ),
        key_pages=list(raw.get("key_pages") or []),
        conversion_pages=list(raw.get("conversion_pages") or []),
        journeys=[
            Journey(id=j["id"], steps=list(j["steps"]), critical=bool(j.get("critical", False)))
            for j in raw.get("journeys") or []
        ],
        access_policy=AccessPolicy(
            allow=list(policy.get("allow") or []),
            block=list(policy.get("block") or []),
            robots_disallow=list(policy.get("robots_disallow") or []),
        ),
        site_pages=_site_pages(raw.get("site_pages"), path.parent),
        cdn_bucket=_cdn_bucket(raw.get("cdn_bucket")),
    )


def _cdn_bucket(block: dict | None) -> CdnBucket | None:
    if not block or not block.get("bucket"):
        return None
    return CdnBucket(
        bucket=str(block["bucket"]),
        prefix=str(block.get("prefix") or get_settings().bucket_reader_prefix),
        source=str(block.get("source") or "cdn"),
    )


def _site_pages(value: list[str] | dict | str | None, base: Path) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    file_name = value["file"] if isinstance(value, dict) else value
    pages = []
    for line in (base / file_name).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "://" in line:
            parts = urlsplit(line)
            line = parts.path + (f"?{parts.query}" if parts.query else "")
        pages.append(line)
    return pages


def token_matches(config: SiteConfig, token: str) -> bool:
    if not config.ingest_token_sha256 or not token:
        return False
    digest = hashlib.sha256(token.encode()).hexdigest()
    return hmac.compare_digest(digest, config.ingest_token_sha256)


def load_cdn_field_map(name: str) -> dict:
    if not SITE_ID.match(name):
        raise SiteNotFound(name)
    path = get_settings().config_dir / "cdn" / f"{name}.yaml"
    if not path.is_file():
        raise SiteNotFound(name)
    return yaml.safe_load(path.read_text()) or {}
