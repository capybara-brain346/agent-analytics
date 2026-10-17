"use client";

import Link from "next/link";
import { ArrowRight, GitBranch, Info } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { JourneyOut, PageList, PageRow, PageView } from "@/lib/api/types";
import { capitalize, formatBytes, number, percent } from "@/lib/format";
import {
  ApiGate,
  Empty,
  Label,
  LoadingState,
  NoData,
  NumberLink,
  Panel,
  SearchField,
  Segmented,
  TableFooter,
  TextLink,
} from "../shared";
import { Props } from "./common";

const presets: { value: "" | PageView; label: string }[] = [
  { value: "", label: "All pages" },
  { value: "agent_heavy", label: "Agent-heavy" },
  { value: "errors", label: "Errors" },
  { value: "blocks", label: "Blocks" },
  { value: "retries", label: "Retries" },
  { value: "never_reached", label: "Key pages never reached" },
];

const Unknown = () => (
  <span className="muted" title="Unknown: no requests in this window">
    Unknown
  </span>
);

export function PagesJourneys({
  href,
  open,
  filters,
  setFilter,
  reset,
  isJourneys,
}: Props & { isJourneys: boolean }) {
  return (
    <>
      <div className="page-tabs">
        <Link
          className={!isJourneys ? "active" : ""}
          aria-current={!isJourneys ? "page" : undefined}
          href={href("/pages")}
        >
          Pages
        </Link>
        <Link
          className={isJourneys ? "active" : ""}
          aria-current={isJourneys ? "page" : undefined}
          href={href("/journeys")}
        >
          Journeys
        </Link>
      </div>
      {isJourneys ? (
        <JourneysTab href={href} open={open} filters={filters} />
      ) : (
        <PagesTab
          href={href}
          open={open}
          filters={filters}
          setFilter={setFilter}
          reset={reset}
        />
      )}
    </>
  );
}

function PagesTab({
  href,
  open,
  filters,
  setFilter,
  reset,
}: Pick<Props, "href" | "open" | "filters" | "setFilter" | "reset">) {
  const search = filters.get("q") || "";
  const presetParam = filters.get("preset") || "";
  const preset = presets.some((p) => p.value === presetParam)
    ? presetParam
    : "";
  const scope = scopeFromQuery(filters);
  const state = useScopedApi<PageList>(
    "pages",
    scope,
    preset ? { view: preset } : {},
  );
  const classFiltered = Boolean(filters.get("class"));
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
          options={presets}
        />
        <span className="toolbar-end">
          {classFiltered && "Page totals include all classes · "}
          {state.data ? `${rows.length} pages · ` : ""}sorted by agent requests
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
      <div className="notice">
        <GitBranch size={16} />
        <div>
          <strong>Look beyond a single page.</strong>
          <p>
            See how far agents reach in your key journeys, and where they retry.
          </p>
        </div>
        <Link className="text-link" href={href("/journeys")}>
          Explore journeys
          <ArrowRight size={13} />
        </Link>
      </div>
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
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Page path</th>
            <th aria-sort="descending">Agent requests ↓</th>
            <th>Sessions</th>
            <th>Agents</th>
            <th>Error rate</th>
            <th>Block rate (403/429)</th>
            <th>Retries</th>
            <th>Median bytes</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.path}>
              <td>
                <TextLink
                  className="mono path-link"
                  onClick={() => open("page", p.path)}
                >
                  {p.path}
                </TextLink>
                {p.tags.map((t) => (
                  <span key={t} className="page-tag">
                    {t}
                  </span>
                ))}
              </td>
              <td>
                <NumberLink
                  value={p.agent_requests}
                  href={href("/events", { path: p.path })}
                />
              </td>
              <td>{number(p.sessions)}</td>
              <td>{number(p.distinct_agents)}</td>
              <td>
                {p.error_rate_pct === null ? (
                  <Unknown />
                ) : (
                  <NumberLink
                    value={percent(p.error_rate_pct)}
                    href={href("/events", { path: p.path, status: "4xx,5xx" })}
                  />
                )}
              </td>
              <td className={(p.block_rate_pct ?? 0) > 10 ? "negative" : ""}>
                {p.block_rate_pct === null ? (
                  <Unknown />
                ) : (
                  <NumberLink
                    value={percent(p.block_rate_pct)}
                    href={href("/events", { path: p.path, status: "403,429" })}
                  />
                )}
              </td>
              <td>{number(p.retries)}</td>
              <td className="mono muted">
                {formatBytes(p.median_bytes) ?? <Unknown />}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JourneysTab({
  href,
  open,
  filters,
}: Pick<Props, "href" | "open" | "filters">) {
  const state = useScopedApi<JourneyOut[]>("journeys", scopeFromQuery(filters));
  return (
    <>
      <div className="notice compact-notice">
        <Info size={15} />
        <span>
          Step counts show pages reached. They do not show task completion.
        </span>
        <Label type="Unknown" />
      </div>
      <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
        {(list) =>
          list.length ? (
            <div className="journey-list">
              {list.map((j) => (
                <JourneyBlock
                  key={j.journey_id}
                  j={j}
                  href={href}
                  open={open}
                />
              ))}
            </div>
          ) : (
            <NoData title="No journeys configured">
              Define journeys in the site config to see how far agents reach.
            </NoData>
          )
        }
      </ApiGate>
    </>
  );
}

function JourneyBlock({
  j,
  href,
  open,
}: {
  j: JourneyOut;
  href: Props["href"];
  open: Props["open"];
}) {
  const retryTotals = j.steps.map((_, i) =>
    j.by_class.reduce((sum, c) => sum + (c.retry_or_loop[i] ?? 0), 0),
  );
  return (
    <Panel
      title={j.journey_id}
      action={
        <span className={`journey-critical ${j.critical ? "critical" : ""}`}>
          {j.critical ? "Critical journey" : "Standard journey"}
        </span>
      }
    >
      <div className="journey-description mono">{j.steps.join(" → ")}</div>
      {j.by_class.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Class</th>
                <th>Sessions</th>
                {j.steps.slice(1).map((s, i) => (
                  <th key={s}>Reached step {i + 2}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {j.by_class.map((c) => (
                <tr key={c.traffic_class}>
                  <td>{c.class_name}</td>
                  <td>
                    <NumberLink
                      value={c.sessions}
                      href={href("/sessions", {
                        journey: j.journey_id,
                        reached: "1",
                        class: String(c.traffic_class),
                      })}
                    />
                  </td>
                  {c.reached.slice(1).map((n, i) => (
                    <td key={i}>
                      <NumberLink
                        value={n}
                        href={href("/sessions", {
                          journey: j.journey_id,
                          reached: String(i + 2),
                          class: String(c.traffic_class),
                        })}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">
          No sessions reached the first step in this window.
        </p>
      )}
      <div className="journey-foot">
        <span className="amber-text">
          Retry or loop by step:{" "}
          {retryTotals.some((n) => n > 0)
            ? retryTotals
                .map((n, i) => (n ? `step ${i + 1}: ${number(n)}` : null))
                .filter(Boolean)
                .join(" · ")
            : "none"}
        </span>
        <span>
          Task outcome <strong>Unknown</strong>
        </span>
        <button
          className="text-link"
          onClick={() => open("journey", j.journey_id)}
        >
          View evidence
          <ArrowRight size={13} />
        </button>
      </div>
      <Label type={capitalize(j.by_class[0]?.label ?? "observed")} />
    </Panel>
  );
}
