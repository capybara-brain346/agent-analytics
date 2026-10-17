"use client";

import Link from "next/link";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  Info,
  Sparkles,
  TriangleAlert,
} from "lucide-react";
import { classOf } from "@/lib/classes";
import { rangeOf } from "@/lib/api/filters";
import type { ApiState } from "@/lib/api/use-api";
import type {
  KeyNumberName,
  Overview as OverviewData,
  RecommendationBrief,
} from "@/lib/api/types";
import { capitalize, dateTimeUTC, number, percent } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Confidence,
  Gap,
  Href,
  Label,
  LoadingState,
  NoData,
  NumberLink,
  OpenDetail,
  Panel,
  Status,
  TextLink,
  Tip,
} from "./shared";
import { TrendChart } from "./trend-chart";

export function RecommendationRows({
  items,
  open,
}: {
  items: RecommendationBrief[];
  open: OpenDetail;
}) {
  return (
    <div className="recommendation-rows">
      {items.map((r, i) => (
        <button
          key={r.id}
          className="recommendation-row"
          onClick={() => open("recommendation", String(r.id))}
        >
          <span className={`rank rank-${i}`}>{r.rank ?? i + 1}</span>
          <span className="rec-main">
            <span className="rec-title">
              {r.target}
              {r.change === "new" && <Status value="New" />}
            </span>
            <span className="rec-meta">
              {r.pattern_name}
              {r.change === "open" && (
                <>
                  <span>·</span>Still open
                </>
              )}
            </span>
          </span>
          <span className="rec-confidence">
            <Confidence value={capitalize(r.confidence)} />
          </span>
          <span className="priority-score">
            <strong>{r.score}</strong>
            <span>priority</span>
          </span>
          <ChevronRight className="row-chevron" size={15} />
        </button>
      ))}
    </div>
  );
}

// Agent traffic is classes 1-4. A class filter in the URL replaces it.
const agentClasses = (selected: string): Record<string, string> =>
  selected ? {} : { class: "1,2,3,4" };

// Label, link and wording for each key number. `bad`: a rise is bad news.
const keyNumbers: {
  key: KeyNumberName;
  title: string;
  path: string;
  filter: (selected: string) => Record<string, string>;
  bad?: boolean;
}[] = [
  {
    key: "total_requests",
    title: "Total requests",
    path: "/events",
    filter: () => ({}),
  },
  {
    key: "ai_or_automated_share",
    title: "AI & automated share",
    path: "/events",
    filter: agentClasses,
  },
  {
    key: "distinct_agents",
    title: "Distinct agents",
    path: "/agents",
    filter: () => ({}),
  },
  {
    key: "error_rate",
    title: "Error rate",
    path: "/events",
    filter: () => ({ status: "4xx,5xx" }),
    bad: true,
  },
  {
    key: "denial_rate",
    title: "Denial rate",
    path: "/events",
    filter: () => ({ status: "403,429" }),
    bad: true,
  },
];

const sourceName: Record<string, string> = {
  cdn: "CDN logs",
  origin: "Origin logs",
};

function OverviewSkeleton() {
  return (
    <>
      <Panel title="Recommended next tests">
        <LoadingState label="Loading recommendations" rows={3} />
      </Panel>
      <Panel title="Key numbers">
        <LoadingState label="Loading key numbers" rows={2} />
      </Panel>
      <Panel title="Request volume">
        <LoadingState label="Loading traffic" rows={5} />
      </Panel>
    </>
  );
}

export function Overview({
  href,
  open,
  selected,
  range,
  state,
}: {
  href: Href;
  open: OpenDetail;
  selected: string;
  range: string;
  state: ApiState<OverviewData>;
}) {
  return (
    <ApiGate state={state} skeleton={<OverviewSkeleton />}>
      {(data) => (
        <OverviewBody
          data={data}
          href={href}
          open={open}
          selected={selected}
          range={range}
        />
      )}
    </ApiGate>
  );
}

function OverviewBody({
  data,
  href,
  open,
  selected,
  range,
}: {
  data: OverviewData;
  href: Href;
  open: OpenDetail;
  selected: string;
  range: string;
}) {
  if (data.empty)
    return (
      <NoData
        title="No data for this site in this time range"
        action={
          <Link className="text-link" href={href("/data")}>
            {data.freshness.last_import_at
              ? `Last import ${dateTimeUTC(data.freshness.last_import_at)} UTC · View data sources`
              : "No import yet · View data sources"}
          </Link>
        }
      >
        Try a longer time range, or check that logs arrive.
      </NoData>
    );
  const { coverage, freshness } = data;
  const compare = rangeOf(range).compare;
  const bucket = rangeOf(range).bucket;
  const classRows = data.traffic_by_class;
  const total = data.key_numbers.total_requests.value ?? 0;
  const agentTrafficSelected =
    !selected || selected.split(",").some((c) => Number(c) <= 4);
  const agentOnly = agentClasses(selected);
  return (
    <>
      <Panel
        title="Recommended next tests"
        className="recommendations-panel"
        action={
          <Link className="subtle-link" href={href("/recommendations")}>
            View all
            <ArrowRight size={13} />
          </Link>
        }
      >
        <div className="recommendation-context">
          <Sparkles size={14} />
          <span>
            Start at the top. Each test links to the sessions and requests
            behind it.
          </span>
        </div>
        {data.top_recommendations.length ? (
          <RecommendationRows items={data.top_recommendations} open={open} />
        ) : (
          <NoData title="No open recommendations">
            No pipeline run has produced a list yet, or no pattern met its
            threshold in the latest run. The Recommendations page shows which.
          </NoData>
        )}
      </Panel>
      <div className="metrics-strip">
        {keyNumbers.map((m) => {
          const k = data.key_numbers[m.key];
          const text =
            k.value === null
              ? null
              : k.unit === "percent"
                ? percent(k.value)
                : number(k.value);
          const up = (k.change_pct ?? 0) >= 0;
          return (
            <Link
              key={m.key}
              href={href(m.path, m.filter(selected))}
              className="metric-cell"
            >
              <div className="metric-label">
                {m.title}
                <ArrowUpRight size={12} />
              </div>
              <strong>{text ?? <Gap>Unknown</Gap>}</strong>
              <div className="metric-bottom">
                {k.change_pct !== null ? (
                  <>
                    <span
                      className={
                        m.bad && up ? "change-negative" : "change-neutral"
                      }
                    >
                      {up ? (
                        <ArrowUpRight size={12} />
                      ) : (
                        <ArrowDownRight size={12} />
                      )}{" "}
                      {percent(Math.abs(k.change_pct))}
                    </span>
                    <span>vs. {compare}</span>
                  </>
                ) : (
                  <span>No traffic in the {compare} to compare</span>
                )}
              </div>
            </Link>
          );
        })}
      </div>
      <div className="two-column chart-columns">
        <Panel
          title="Request volume"
          label="Observed"
          action={
            <span className="muted panel-note">
              Requests / {bucket}{" "}
              <Tip text="Each bar is one UTC hour or day. The colours split the bar by traffic class." />
            </span>
          }
        >
          <TrendChart
            href={href}
            trend={data.trend}
            start={data.window.start}
            end={data.window.end}
            bucket={bucket}
          />
        </Panel>
        <Panel
          title="Traffic by class"
          label="Inferred"
          action={
            <Tip text="Classes use verified identity, the user agent, and edge signals. Select a class to inspect its requests." />
          }
        >
          <div
            className="class-distribution"
            aria-label="Traffic share by class"
          >
            {classRows
              .filter((c) => c.requests > 0)
              .map((c) => (
                <Link
                  href={href("/events", { class: String(c.traffic_class) })}
                  key={c.traffic_class}
                  style={{
                    width: `${c.share_pct}%`,
                    background: classOf(c.traffic_class).color,
                  }}
                  aria-label={`${c.name} ${percent(c.share_pct)}`}
                />
              ))}
          </div>
          <table className="class-table">
            <thead>
              <tr>
                <th>Class</th>
                <th>Requests</th>
                <th>Share</th>
              </tr>
            </thead>
            <tbody>
              {classRows.map((c) => (
                <tr key={c.traffic_class}>
                  <td>
                    <Link
                      href={href("/events", { class: String(c.traffic_class) })}
                    >
                      <ClassName id={c.traffic_class} />
                    </Link>
                  </td>
                  <td>
                    <NumberLink
                      value={c.requests}
                      href={href("/events", { class: String(c.traffic_class) })}
                    />
                  </td>
                  <td>{percent(c.share_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="panel-footnote">
            <Info size={12} />
            <span>
              {data.unclassified_requests > 0 && (
                <>
                  {number(data.unclassified_requests)} requests have no class
                  yet.{" "}
                </>
              )}
              Class does not confirm identity.{" "}
              <TextLink onClick={() => open("legend", "labels")}>
                How classification works
              </TextLink>
            </span>
          </div>
        </Panel>
      </div>
      <div className="two-column bottom-columns">
        <Panel
          title="Top pages by agent traffic"
          label="Observed"
          action={
            <Link className="subtle-link" href={href("/pages")}>
              All pages
              <ArrowRight size={13} />
            </Link>
          }
        >
          {data.top_pages.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Page path</th>
                    <th aria-sort="descending">
                      Agent requests <span className="sort-arrow">↓</span>
                    </th>
                    <th>Errors</th>
                    <th>Denied</th>
                  </tr>
                </thead>
                <tbody>
                  {data.top_pages.map((p) => (
                    <tr key={p.path}>
                      <td>
                        <TextLink
                          className="path-link"
                          onClick={() => open("page", p.path)}
                        >
                          {p.path}
                        </TextLink>
                      </td>
                      <td>
                        <NumberLink
                          value={p.agent_requests}
                          href={href("/events", { path: p.path, ...agentOnly })}
                        />
                      </td>
                      <td>
                        <NumberLink
                          value={p.errors}
                          href={href("/events", {
                            path: p.path,
                            status: "4xx,5xx",
                            ...agentOnly,
                          })}
                        />
                      </td>
                      <td className={p.blocks > 0 ? "negative" : ""}>
                        <NumberLink
                          value={p.blocks}
                          href={href("/events", {
                            path: p.path,
                            status: "403,429",
                            ...agentOnly,
                          })}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <NoData title="No agent requests to pages">
              {agentTrafficSelected
                ? "No class 1–4 request arrived in this window."
                : "This list counts classes 1–4 only. The selected classes are outside it."}
            </NoData>
          )}
          <div className="panel-footnote">
            Agent traffic is classes 1–4. Errors are status 400 and above.
            Denied is 403 and 429. HTTP status does not prove task completion.
          </div>
        </Panel>
        <Panel title="What the data can show">
          <div className="coverage-content">
            <div className="coverage-source">
              {coverage.sources_configured.map((source) => {
                const present =
                  coverage.sources_present.includes(source) ||
                  coverage.sources_present.includes("paired");
                return present ? (
                  <span key={source}>
                    <Check size={13} /> {sourceName[source] ?? source}
                  </span>
                ) : (
                  <span key={source} className="amber-text">
                    <TriangleAlert size={13} /> {sourceName[source] ?? source}:
                    no data in this window
                  </span>
                );
              })}
              <span className="source-paired">
                {coverage.paired_share_pct === null ? (
                  <Gap>Paired share unknown</Gap>
                ) : (
                  <>
                    {percent(coverage.paired_share_pct, 0)} paired <Label />
                  </>
                )}
              </span>
            </div>
            <div className="coverage-line">
              <span>Requests with unknown class</span>
              {coverage.unknown_share_pct === null ? (
                <Gap>No requests to measure</Gap>
              ) : (
                <Link href={href("/events", { class: "6" })}>
                  {percent(coverage.unknown_share_pct)}
                  <ArrowUpRight size={12} />
                </Link>
              )}
            </div>
            <div className="coverage-gap">
              <Label type="Unknown" />
              <p>
                {coverage.cannot_see.length
                  ? `${capitalize(coverage.cannot_see.join(", "))} are not visible in request logs.`
                  : "No known blind spots."}
              </p>
            </div>
            {coverage.partial.map((text) => (
              <div className="coverage-limit" key={text}>
                <Info size={13} />
                <span>{capitalize(text)}.</span>
              </div>
            ))}
            {freshness.state !== "ok" && (
              <div className="coverage-limit">
                <TriangleAlert size={13} />
                <span>{freshness.text}</span>
              </div>
            )}
          </div>
        </Panel>
      </div>
      <Panel
        title="Classification confidence"
        label="Inferred"
        className="confidence-panel"
        action={
          <Tip text="Each cell opens requests for one class and confidence level. Zero means no matching requests." />
        }
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Traffic class</th>
                <th>High confidence</th>
                <th>Medium confidence</th>
                <th>Low confidence</th>
                <th>Total requests</th>
              </tr>
            </thead>
            <tbody>
              {classRows.map((c) => (
                <tr key={c.traffic_class}>
                  <td>
                    <ClassName id={c.traffic_class} full />
                  </td>
                  {(["high", "medium", "low"] as const).map((conf) => (
                    <td key={conf}>
                      <NumberLink
                        value={c[conf]}
                        href={href("/events", {
                          class: String(c.traffic_class),
                          confidence: conf,
                        })}
                      />
                    </td>
                  ))}
                  <td>
                    <NumberLink
                      value={c.requests}
                      href={href("/events", { class: String(c.traffic_class) })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel-footnote">
          {number(total)} requests in this window
          {data.unclassified_requests > 0 &&
            `, of which ${number(data.unclassified_requests)} have no class yet`}
          .
        </div>
      </Panel>
    </>
  );
}
