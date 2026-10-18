"use client";

import type { MouseEvent } from "react";
import Link from "next/link";
import { ChevronRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { PageList, PageRow } from "@/lib/api/types";
import { formatBytes, number, percent } from "@/lib/format";
import {
  ApiGate,
  Empty,
  LoadingState,
  NoData,
  NumberLink,
  Panel,
  SearchField,
  Segmented,
  TableFooter,
  TextLink,
} from "../../shared";
import type { Props } from "../common";
import { PAGE_PRESETS, UNKNOWN_TITLE } from "./config";
import { blockTone, errorTone, pageHealth, plural, type Tone } from "./health";

type TabProps = Pick<
  Props,
  "href" | "open" | "filters" | "setFilter" | "reset"
>;

const Unknown = () => (
  <span className="unknown-dash" title={UNKNOWN_TITLE}>
    —
  </span>
);

function Rate({
  pct,
  tone,
  href,
}: {
  pct: number | null;
  tone: (n: number) => Tone;
  href: string;
}) {
  if (pct === null) return <Unknown />;

  return (
    <span className={`qualifier ${tone(pct)}`}>
      <i />
      <NumberLink value={percent(pct)} href={href} />
    </span>
  );
}

export function PagesTab({ href, open, filters, setFilter, reset }: TabProps) {
  const search = filters.get("q") || "";
  const presetParam = filters.get("preset") || "";
  const preset = PAGE_PRESETS.some((p) => p.value === presetParam)
    ? presetParam
    : "";
  const state = useScopedApi<PageList>(
    "pages",
    scopeFromQuery(filters),
    preset ? { view: preset } : {},
  );
  const rows = (state.data?.items ?? [])
    .filter(
      (p) => !search || p.path.toLowerCase().includes(search.toLowerCase()),
    )
    .sort(
      (a, b) =>
        b.agent_requests - a.agent_requests || a.path.localeCompare(b.path),
    );

  return (
    <>
      <div className="filter-toolbar">
        <SearchField
          placeholder="Search page paths…"
          value={search}
          onChange={(v) => setFilter("q", v)}
        />
        <Segmented
          label="Show pages"
          value={preset}
          onChange={(v) => setFilter("preset", v)}
          options={PAGE_PRESETS}
        />
        <span className="toolbar-end">
          {filters.get("class") && "Page totals include all classes · "}
          {state.data
            ? `${rows.length} ${plural(rows.length, "page", "pages")}`
            : ""}
        </span>
      </div>
      <Panel title="Pages" label="Observed">
        <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
          {() =>
            rows.length ? (
              <PageTable rows={rows} href={href} open={open} />
            ) : search ? (
              <Empty reset={reset} active={[`“${search}”`]} />
            ) : (
              <NoData title="No pages match this view">
                {preset === "never_reached"
                  ? "Every key or sitemap page had agent requests in this window, or no key pages are configured."
                  : "No page matched in this time range. Try a longer range."}
              </NoData>
            )
          }
        </ApiGate>
        {state.data && <TableFooter count={rows.length} noun="pages" />}
      </Panel>
      <p className="pages-hint">
        See how far agents reach in your key paths on the{" "}
        <Link className="text-link" href={href("/journeys")}>
          Journeys tab
        </Link>
        .
      </p>
    </>
  );
}

function PageTable({
  rows,
  href,
  open,
}: {
  rows: PageRow[];
  href: Props["href"];
  open: Props["open"];
}) {
  // Whole row opens the detail sheet. Links and buttons inside keep their own action.
  const onRow = (e: MouseEvent, path: string) => {
    if ((e.target as HTMLElement).closest("a,button")) return;
    open("page", path);
  };

  return (
    <div className="table-scroll">
      <table className="pages-table" aria-label="Pages">
        <thead>
          <tr>
            <th>Page</th>
            <th data-col="status">Status</th>
            <th
              aria-sort="descending"
              title="Requests from agent traffic, highest first"
            >
              Agent requests
            </th>
            <th data-col="errors" title="Share of requests answered 4xx or 5xx">
              Error rate
            </th>
            <th data-col="blocks" title="Share of requests answered 403 or 429">
              Block rate
            </th>
            <th data-col="sessions">Sessions</th>
            <th data-col="agents">Agents</th>
            <th data-col="retries">Retries</th>
            <th data-col="bytes">Median bytes</th>
            <th data-col="open" aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => {
            const health = pageHealth(p);

            return (
              <tr key={p.path} onClick={(e) => onRow(e, p.path)}>
                <td>
                  <TextLink
                    className="path-link"
                    onClick={() => open("page", p.path)}
                  >
                    {p.path}
                  </TextLink>
                  {p.tags.length > 0 && (
                    <span className="table-subline">
                      {p.tags.map((t) => (
                        <span key={t} className="page-tag">
                          {t}
                        </span>
                      ))}
                    </span>
                  )}
                </td>
                <td data-col="status">
                  <span className={`status ${health.pill}`}>
                    <span className="status-dot" />
                    {health.label}
                  </span>
                </td>
                <td className="figure">
                  <NumberLink
                    value={p.agent_requests}
                    href={href("/events", { path: p.path })}
                  />
                </td>
                <td data-col="errors">
                  <Rate
                    pct={p.error_rate_pct}
                    tone={errorTone}
                    href={href("/events", { path: p.path, status: "4xx,5xx" })}
                  />
                </td>
                <td data-col="blocks">
                  <Rate
                    pct={p.block_rate_pct}
                    tone={blockTone}
                    href={href("/events", { path: p.path, status: "403,429" })}
                  />
                </td>
                <td data-col="sessions">{number(p.sessions)}</td>
                <td data-col="agents">{number(p.distinct_agents)}</td>
                <td data-col="retries">{number(p.retries)}</td>
                <td data-col="bytes" className="mono">
                  {formatBytes(p.median_bytes) ?? <Unknown />}
                </td>
                <td data-col="open">
                  <ChevronRight size={14} className="row-chevron" />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
