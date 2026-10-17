from dataclasses import dataclass, field

from src.models.domain import SourceType


@dataclass(frozen=True)
class Journey:
    id: str
    steps: list[str]
    critical: bool = False


@dataclass(frozen=True)
class SiteConfig:
    site_id: str
    sources: list[SourceType]
    cdn_field_map: str | None = None
    request_id_header: str | None = None
    key_pages: list[str] = field(default_factory=list)
    conversion_pages: list[str] = field(default_factory=list)
    journeys: list[Journey] = field(default_factory=list)


def load_site_config(site_id: str) -> SiteConfig:
    raise NotImplementedError
