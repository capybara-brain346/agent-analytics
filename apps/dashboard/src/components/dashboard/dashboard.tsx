"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  Bot,
  Boxes,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronRight,
  CircleHelp,
  Database,
  Globe2,
  LayoutDashboard,
  Menu,
  ScanLine,
  Settings2,
  Sparkles,
} from "lucide-react";
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
import { windowCaption } from "@/lib/format";
import { Overview } from "./overview";
import {
  Activity as ActivityView,
  Agents,
  DataPipeline,
  PagesJourneys,
  Recommendations,
} from "./sections";
import { DetailContent, detailTitle } from "./details";
import { ClassFilter, Href, Label, Select } from "./shared";

const navigation: {
  path: string;
  label: string;
  icon: typeof Sparkles;
  count?: number;
}[] = [
  { path: "/overview", label: "Overview", icon: LayoutDashboard },
  { path: "/recommendations", label: "Recommendations", icon: Sparkles },
  { path: "/agents", label: "Agents", icon: Bot },
  { path: "/events", label: "Activity explorer", icon: Activity },
  { path: "/pages", label: "Pages & journeys", icon: Boxes },
  { path: "/data", label: "Data & pipeline", icon: Database },
];
const globalKeys = ["site", "range", "class"];
export function Dashboard() {
  const pathname = usePathname(),
    query = useSearchParams(),
    router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);
  const route = pathname.split("/").filter(Boolean),
    view = route[0] || "overview";
  const settings = view === "data" && query.get("tab") === "settings";
  const active = settings
    ? "settings"
    : view === "sessions"
      ? "events"
      : view === "journeys"
        ? "pages"
        : view;
  const nav = settings
    ? { label: "Settings" }
    : navigation.find((n) => n.path === `/${active}`);
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
  const navItems = (
    <>
      <div className="nav-caption">Workspace</div>
      <nav aria-label="Main navigation">
        {navigation.map((item) => (
          <Link
            key={item.path}
            className={`nav-item ${active === item.path.slice(1) ? "active" : ""}`}
            href={href(item.path)}
            onClick={() => setMobileOpen(false)}
            aria-current={active === item.path.slice(1) ? "page" : undefined}
          >
            <item.icon size={16} />
            <span>{item.label}</span>
            {item.count && <span className="nav-count">{item.count}</span>}
          </Link>
        ))}
        <Link
          className={`nav-item mobile-only ${settings ? "active" : ""}`}
          href={href("/data", { tab: "settings" })}
          onClick={() => setMobileOpen(false)}
          aria-current={settings ? "page" : undefined}
        >
          <Settings2 size={16} />
          <span>Settings</span>
        </Link>
      </nav>
    </>
  );
  const descriptions: Record<string, string> = {
    overview: "Understand your agent traffic. Know what to test next.",
    recommendations:
      "The journeys worth testing, with the evidence behind each one.",
    agents: "Who is visiting, what they claim, and what the evidence confirms.",
    events: "Follow the evidence, one request at a time.",
    sessions: "Follow the evidence, one session at a time.",
    pages: "Where agents go, and where the gaps appear.",
    journeys: "Where agents go, and where the gaps appear.",
    data: "Data sources, coverage, and the state of your pipeline.",
  };
  const props = { href, open, filters: query, setFilter, reset };
  return (
    <div className="workspace-shell">
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <aside className="sidebar">
        <Link href={href("/overview")} className="brand">
          <span className="brand-mark">
            <ScanLine size={22} />
          </span>
          <span>Agent Analytics</span>
        </Link>
        <div className="workspace-switch">
          <span className="workspace-avatar">
            {(site || "?").charAt(0).toUpperCase()}
          </span>
          <span>
            {site || "Loading site"}
            <small>Agent traffic</small>
          </span>
        </div>
        {navItems}
        <div className="sidebar-bottom">
          <Link
            className={`nav-item ${settings ? "active" : ""}`}
            aria-current={settings ? "page" : undefined}
            href={href("/data", { tab: "settings" })}
          >
            <Settings2 size={15} />
            Settings
          </Link>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            <button
              className="mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={19} />
            </button>
            <span className="desktop-only">
              <ChartNoAxesCombined size={15} />
            </span>
            <span className="breadcrumb-root">Workspace</span>
            <span className="breadcrumb-separator">/</span>
            <span>{nav?.label || "Not found"}</span>
          </div>
          <div className="topbar-right" />
        </header>
        <main id="main-content">
          <div className="section-intro">
            <div>
              <h1>{nav?.label || "Page not found"}</h1>
              <p>{descriptions[view] || "This page does not exist."}</p>
            </div>
          </div>
          {nav && (
            <>
              <div className="global-filters">
                <div className="filter-group">
                  <Select
                    label="Site"
                    value={site}
                    onChange={(v) => setFilter("site", v)}
                    icon={<Globe2 size={13} />}
                    options={[{ value: site, label: site || "Loading…" }]}
                  />
                  <span className="filter-divider" />
                  <Select
                    label="Time range"
                    value={range}
                    onChange={(v) => setFilter("range", v)}
                    icon={<CalendarDays size={13} />}
                    options={[
                      { value: "1h", label: "Last 1 hour" },
                      { value: "6h", label: "Last 6 hours" },
                      { value: "24h", label: "Last 24 hours" },
                      { value: "7d", label: "Last 7 days" },
                    ]}
                  />
                  <ClassFilter
                    value={selected}
                    onChange={(v) => setFilter("class", v)}
                  />
                </div>
                <Link
                  href={href(
                    "/data",
                    freshness && freshness.state !== "ok"
                      ? { tab: "health" }
                      : {},
                  )}
                  className={`freshness ${freshness?.state === "ok" ? "" : "stale"}`}
                >
                  <span className="live-dot" />
                  <span>
                    {freshness
                      ? freshness.text
                      : overview.error
                        ? "Data freshness unknown"
                        : "Checking data freshness…"}
                  </span>
                  <ChevronRight size={12} />
                </Link>
              </div>
              <div className="window-caption">
                <span>
                  {overview.data
                    ? windowCaption(
                        overview.data.window.start,
                        overview.data.window.end,
                      )
                    : rangeOf(range).label}{" "}
                  <span className="muted">· UTC</span>
                </span>
                <span>
                  <button
                    className="label-guide-trigger"
                    aria-label="Label guide: Observed, Inferred, Unknown"
                    onClick={() => open("legend", "labels")}
                  >
                    <Label />
                    <Label type="Inferred" />
                    <Label type="Unknown" />
                    <CircleHelp size={12} />
                  </button>
                </span>
              </div>
            </>
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
              <div className="site-empty">
                <h2>Page not found</h2>
                <Link className="text-link" href={href("/overview")}>
                  Return to overview
                </Link>
              </div>
            )}
          </div>
          <footer className="workspace-footer">
            <span>
              <ScanLine size={12} />
              Agent Analytics
            </span>
            <span>{site}</span>
            <span>All times are UTC</span>
          </footer>
        </main>
      </div>
      <Sheet
        open={Boolean(detail)}
        onOpenChange={(value) => {
          if (!value) closeDetail();
        }}
      >
        <SheetContent className="evidence-sheet" initialFocus={sheetTitle}>
          <SheetHeader className="evidence-sheet-header">
            {previous && detail && (
              <button className="sheet-back" onClick={() => router.back()}>
                <ArrowLeft size={13} />
                Back to {detailTitle(...splitDetail(previous))}
              </button>
            )}
            <SheetTitle ref={sheetTitle} tabIndex={-1}>
              {detailTitle(shownType, shownId)}
            </SheetTitle>
            <SheetDescription>
              {shownType === "legend"
                ? "How to read the evidence in this workspace"
                : `Evidence · ${site}`}
            </SheetDescription>
          </SheetHeader>
          <div className="sheet-body">
            <DetailContent
              type={shownType}
              id={shownId}
              href={href}
              open={open}
            />
          </div>
        </SheetContent>
      </Sheet>
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="mobile-nav">
          <SheetHeader>
            <SheetTitle>Agent Analytics</SheetTitle>
            <SheetDescription>{site || "Agent traffic"}</SheetDescription>
          </SheetHeader>
          {navItems}
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
