from typing import Annotated

from fastapi import APIRouter, Query

from src.models.api import PageDetail, PageList, PageRow
from src.routes.params import Conn, ScopeDep, not_found, utcnow
from src.routes.sessions import session_row
from src.services import site_config
from src.store import queries

router = APIRouter(prefix="/pages", tags=["pages"])

VIEWS = "^(agent_heavy|errors|blocks|retries|never_reached)$"


def page_row(r: dict, tags: list[str]) -> PageRow:
    requests = r.get("requests") or 0
    return PageRow(
        path=r["path"],
        tags=tags,
        agent_requests=r.get("agent_requests") or 0,
        requests=requests,
        sessions=r.get("sessions", 0),
        distinct_agents=r.get("agents", 0),
        error_rate_pct=round(100.0 * (r.get("errors") or 0) / requests, 2) if requests else None,
        block_rate_pct=round(100.0 * (r.get("blocks") or 0) / requests, 2) if requests else None,
        retries=r.get("retries") or 0,
        median_bytes=r.get("median_bytes"),
    )


def config_tags(cfg: site_config.SiteConfig, path: str, stored: list[str] | None) -> list[str]:
    tags = set(stored or [])
    if path in cfg.key_pages:
        tags.add("key")
    if path in cfg.conversion_pages:
        tags.add("conversion")
    return sorted(tags)


@router.get("", response_model=PageList | PageDetail)
async def list_pages(
    conn: Conn,
    scope: ScopeDep,
    path: Annotated[str | None, Query(description="Exact path: returns page detail")] = None,
    view: Annotated[str | None, Query(pattern=VIEWS)] = None,
) -> PageList | PageDetail:
    cfg = site_config.load_site_config(scope.site_id)
    f = scope.filters()
    rows = await queries.list_pages(conn, f)
    by_path = {r["path"]: r for r in rows}

    if path is not None:
        known = path in by_path or path in cfg.key_pages or path in cfg.site_pages
        detail = await queries.get_page(conn, f, path)
        if not known and not detail["by_class"] and not detail["sessions"]:
            raise not_found("page", path)
        now = utcnow()
        row = page_row(by_path.get(path, {"path": path}), config_tags(cfg, path, detail["tags"]))
        return PageDetail(
            page=row,
            in_sitemap=path in cfg.site_pages,
            access_policy="blocked_by_intent"
            if cfg.access_policy.blocked_by_intent(path)
            else "allowed",
            by_class=detail["by_class"],
            over_time=detail["over_time"],
            agents=detail["agents"],
            sessions=[session_row(s, now) for s in detail["sessions"]],
            recommendations=detail["recommendations"],
        )

    items = [page_row(r, config_tags(cfg, r["path"], r["tags"])) for r in rows]
    # Key pages that no client reached: shown with 0 requests (Unknown if never fetched, R4).
    for p in dict.fromkeys([*cfg.key_pages, *cfg.conversion_pages, *cfg.site_pages]):
        if p not in by_path:
            items.append(page_row({"path": p}, config_tags(cfg, p, None)))
    match view:
        case "agent_heavy":
            items.sort(key=lambda i: (-i.agent_requests, i.path))
            items = [i for i in items if i.agent_requests > 0]
        case "errors":
            items = [i for i in items if (i.error_rate_pct or 0) > 0]
        case "blocks":
            items = [i for i in items if (i.block_rate_pct or 0) > 0]
        case "retries":
            items = [i for i in items if i.retries > 0]
        case "never_reached":
            items = [
                i
                for i in items
                if i.agent_requests == 0 and ("key" in i.tags or i.path in cfg.site_pages)
            ]
    return PageList(view=view, items=items)
