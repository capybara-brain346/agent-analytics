"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { rangeOf, scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { Overview as OverviewData } from "@/lib/api/types";
import { dateTimeUTC, windowCaption } from "@/lib/format";
import { Overview } from "./overview";
import {
  Activity as ActivityView,
  Agents,
  DataPipeline,
  PagesJourneys,
  Recommendations,
} from "./sections";
import { DetailSheet } from "./shell/detail-sheet";
import { FilterBar } from "./shell/filter-bar";
import { navItems } from "./shell/nav-config";
import { Rail } from "./shell/rail";
import { TopBar } from "./shell/topbar";
import type { Href } from "./shared";

const globalKeys = ["site", "range", "class"];

export function Dashboard() {
  const pathname = usePathname(),
    query = useSearchParams(),
    router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const route = pathname.split("/").filter(Boolean),
    view = route[0] || "overview";
  const active =
    view === "sessions"
      ? "events"
      : view === "journeys"
        ? "pages"
        : view;
  const nav = navItems.find((n) => n.key === active);
  // The global filters in the URL. One request for the overview feeds the
  // freshness banner on every screen, and the Overview screen.
  const scope = scopeFromQuery(query),
    range = scope.range,
    selected = scope.classes;
  const overview = useScopedApi<OverviewData>("overview", scope, {
    bucket: rangeOf(range).bucket,
  });
  // The URL has no site until the user picks one. The API then uses the only
  // site it has, and names it in the response.
  const site = scope.site || overview.data?.window.site || "";
  const freshness = overview.data?.freshness;
  const href: Href = (path, filters = {}) => {
    const params = new URLSearchParams();
    globalKeys.forEach((k) => {
      const v = query.get(k);
      if (v) params.set(k, v);
    });
    Object.entries(filters).forEach(([k, v]) => {
      if (v) params.set(k, v);
    });
    return `${path}${params.size ? `?${params}` : ""}`;
  };
  function setFilter(key: string, value: string) {
    const params = new URLSearchParams(query.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    params.delete("detail");
    router.replace(`${pathname}${params.size ? `?${params}` : ""}`, {
      scroll: false,
    });
  }
  function reset() {
    router.replace(href(pathname), { scroll: false });
  }
  function open(type: string, id: string) {
    const next = `${type}:${id}`;
    if (next === detail) return;
    const params = new URLSearchParams(query.toString());
    params.set("detail", next);
    setTrail((t) => [
      ...(t.length || !detail ? t : [{ detail, pushed: false }]),
      { detail: next, pushed: true },
    ]);
    router.push(`${pathname}?${params}`, { scroll: false });
  }
  const directType: Record<string, string> = {
    recommendations: "recommendation",
    agents: "agent",
    events: "event",
    sessions: "session",
    journeys: "journey",
  };
  const detail =
    query.get("detail") ||
    (route[1] && directType[view] ? `${directType[view]}:${route[1]}` : "");
  // Sheets opened in this view, oldest first. A deep-linked sheet is the
  // unpushed base. Browser Back and Forward move along the same list.
  const [trail, setTrail] = useState<{ detail: string; pushed: boolean }[]>([]);
  const [seenDetail, setSeenDetail] = useState(detail);
  if (seenDetail !== detail) {
    setSeenDetail(detail);
    setTrail((t) => {
      if (!detail) return [];
      const at = t.findLastIndex((e) => e.detail === detail);
      if (at >= 0) return t.slice(0, at + 1);
      return t.length ? [...t, { detail, pushed: true }] : t;
    });
  }
  // Keep the last sheet on screen while the sheet animates closed.
  const [shownDetail, setShownDetail] = useState(detail);
  if (detail && shownDetail !== detail) setShownDetail(detail);
  const [shownType, shownId] = splitDetail(shownDetail);
  const closing = useRef("");
  useEffect(() => {
    // A deep-linked base sheet is still open after history.go: remove it.
    if (closing.current && detail === closing.current) {
      closing.current = "";
      const params = new URLSearchParams(window.location.search);
      params.delete("detail");
      router.replace(
        `${route[1] ? `/${view}` : pathname}${params.size ? `?${params}` : ""}`,
        { scroll: false },
      );
    }
  }, [detail, pathname, route, router, view]);
  const previous =
    trail.length > 1 && trail.at(-1)?.detail === detail
      ? trail.at(-2)!.detail
      : "";
  const sheetTitle = useRef<HTMLHeadingElement>(null);
  function closeDetail() {
    const pushed = trail.filter((e) => e.pushed).length;
    if (pushed) {
      // Leave the sheet the way it was entered, so Back does not reopen it.
      if (pushed < trail.length) closing.current = trail[0].detail;
      window.history.go(-pushed);
      return;
    }
    const params = new URLSearchParams(query.toString());
    params.delete("detail");
    router.replace(
      `${route[1] ? `/${view}` : pathname}${params.size ? `?${params}` : ""}`,
      { scroll: false },
    );
  }
  const props = { href, open, filters: query, setFilter, reset };
  const caption = overview.data
    ? windowCaption(overview.data.window.start, overview.data.window.end)
    : rangeOf(range).label;
  const rail = (onNavigate?: () => void) => (
    <Rail
      href={href}
      active={active}
      site={site}
      freshness={freshness}
      onNavigate={onNavigate}
    />
  );
  return (
    <div className="shell" data-shell>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="rail" data-rail>
        {rail()}
      </aside>
      <div className="stage">
        <TopBar
          title={nav?.label || "Not found"}
          href={href}
          freshness={freshness}
          failed={Boolean(overview.error)}
          onMenu={() => setMobileOpen(true)}
          onLabelGuide={() => open("legend", "labels")}
        />
        <main id="main-content" className="workspace" data-work data-scroll>
          {nav && (
            <FilterBar
              site={site}
              range={range}
              classes={selected}
              caption={`${caption} UTC`}
              setFilter={setFilter}
            />
          )}
          <div className="page-content">
            {view === "overview" ? (
              <Overview
                href={href}
                open={open}
                selected={selected}
                range={range}
                state={overview}
              />
            ) : view === "recommendations" ? (
              <Recommendations {...props} />
            ) : view === "agents" ? (
              <Agents {...props} />
            ) : view === "events" || view === "sessions" ? (
              <ActivityView {...props} isSessions={view === "sessions"} />
            ) : view === "pages" || view === "journeys" ? (
              <PagesJourneys {...props} isJourneys={view === "journeys"} />
            ) : view === "data" ? (
              <DataPipeline {...props} />
            ) : (
              <div className="empty-state">
                <p>This page does not exist.</p>
                <Link className="text-link" href={href("/overview")}>
                  Return to overview
                </Link>
              </div>
            )}
          </div>
          <footer className="status-row">
            <span>{site}</span>
            <span>
              {freshness?.data_up_to
                ? `data up to ${dateTimeUTC(freshness.data_up_to)}`
                : "data freshness unknown"}
            </span>
            <span>all times UTC</span>
          </footer>
        </main>
      </div>
      <DetailSheet
        open={Boolean(detail)}
        onClose={closeDetail}
        titleRef={sheetTitle}
        backTo={previous ? splitDetail(previous) : null}
        onBack={() => router.back()}
        type={shownType}
        id={shownId}
        site={site}
        href={href}
        openDetail={open}
      />
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent
          side="left"
          className="rail-sheet"
          showCloseButton={false}
        >
          <SheetHeader className="sr-only">
            <SheetTitle>Agent Analytics</SheetTitle>
            <SheetDescription>{site || "Agent traffic"}</SheetDescription>
          </SheetHeader>
          {rail(() => setMobileOpen(false))}
        </SheetContent>
      </Sheet>
    </div>
  );
}
// A detail id may hold ":" (a page path, for example). Split at the first one.
function splitDetail(detail: string): [string, string] {
  const at = detail.indexOf(":");
  return at < 0 ? [detail, ""] : [detail.slice(0, at), detail.slice(at + 1)];
}
