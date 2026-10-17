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
} from "lucide-react";
import {
  agents,
  classes,
  number,
  pages,
  rangeOf,
  recommendations,
  scaled,
} from "@/lib/mock-data";
import {
  ClassName,
  Confidence,
  Href,
  Label,
  NumberLink,
  OpenDetail,
  Panel,
  Status,
  TextLink,
  Tip,
  TrafficChart,
} from "./shared";

export function RecommendationRows({ open }: { open: OpenDetail }) {
  return (
    <div className="recommendation-rows">
      {recommendations.slice(0, 3).map((r, i) => (
        <button
          key={r.id}
          className="recommendation-row"
          onClick={() => open("recommendation", r.id)}
        >
          <span className={`rank rank-${i}`}>{i + 1}</span>
          <span className="rec-main">
            <span className="rec-title">
              {r.title}
              {r.status === "New" && <Status value="New" />}
            </span>
            <span className="rec-meta">
              {r.pattern}
              <span>·</span>
              {r.sessions} sessions<span>·</span>
              {r.events} events
            </span>
          </span>
          <span className="rec-confidence">
            <Confidence value={r.confidence} />
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

export function Overview({
  href,
  open,
  selected,
  range,
}: {
  href: Href;
  open: OpenDetail;
  selected: string;
  range: string;
}) {
  // Every count follows the class and time range filters.
  const shown = classes.filter(
    (c) => !selected || selected.split(",").includes(String(c.id)),
  );
  const sum = shown.reduce((t, c) => t + c.count, 0);
  const automated = shown
    .filter((c) => c.id <= 4)
    .reduce((t, c) => t + c.count, 0);
  const groups = agents.filter((a) => shown.some((c) => c.id === a.classId));
  // The sample stores period changes for the unfiltered 24-hour view only.
  const comparable = !selected && (range === "24h" || range === "7d");
  const metrics = [
    {
      title: "Total requests",
      value: number(scaled(sum, range)),
      change: "12.8%",
      up: true,
      filter: {},
    },
    {
      title: "AI & automated share",
      value: `${((automated / sum) * 100).toFixed(1)}%`,
      change: "8.2%",
      up: true,
      filter: selected ? {} : { class: "1,2,3,4" },
    },
    {
      title: selected ? "Agent groups" : "Distinct agents",
      value: selected ? String(groups.length) : "24",
      change: selected ? "" : "+3",
      up: true,
      filter: {},
    },
    {
      title: "Error rate",
      value: "2.8%",
      change: "0.6%",
      up: false,
      filter: { status: "errors" },
    },
    {
      title: "Denial rate",
      value: "4.2%",
      change: "1.1%",
      up: true,
      filter: { status: "denied" },
    },
  ];
  return (
    <>
      <Panel
        title="Recommended next tests"
        className="recommendations-panel"
        action={
          <Link className="subtle-link" href={href("/recommendations")}>
            View all 5<ArrowRight size={13} />
          </Link>
        }
      >
        <div className="recommendation-context">
          <Sparkles size={14} />
          <span>
            Start at the top. Each test links to the sessions and requests
            behind it.
          </span>
          <span className="run-marker">Run #14 · 14:02</span>
        </div>
        <RecommendationRows open={open} />
      </Panel>
      <div className="metrics-strip">
        {metrics.map((m, i) => (
          <Link
            key={m.title}
            href={href(
              i === 2 ? "/agents" : "/events",
              m.filter as Record<string, string>,
            )}
            className="metric-cell"
          >
            <div className="metric-label">
              {m.title}
              <ArrowUpRight size={12} />
            </div>
            <strong>{m.value}</strong>
            <div className="metric-bottom">
              {m.change && comparable ? (
                <>
                  <span
                    className={i === 4 ? "change-negative" : "change-neutral"}
                  >
                    {m.up ? (
                      <ArrowUpRight size={12} />
                    ) : (
                      <ArrowDownRight size={12} />
                    )}{" "}
                    {m.change}
                  </span>
                  <span>vs. {rangeOf(range).compare}</span>
                </>
              ) : (
                <span>
                  {selected ? "Selected classes" : rangeOf(range).caption}
                  {i >= 3 && " · all classes"}
                </span>
              )}
            </div>
          </Link>
        ))}
      </div>
      <div className="two-column chart-columns">
        <Panel
          title="Request volume"
          label="Observed"
          action={
            <span className="muted panel-note">
              Requests / 15 min{" "}
              <Tip text="Fixed sample traffic for Oct 15–16, 2026. The bars show the relative traffic mix." />
            </span>
          }
        >
          <TrafficChart href={href} selected={selected} range={range} />
        </Panel>
        <Panel
          title="Traffic by class"
          label="Inferred"
          action={
            <Tip text="Classes use verified identity, the user agent, and edge signals. Select a class to inspect its sample requests." />
          }
        >
          <div
            className="class-distribution"
            aria-label="Traffic share by class"
          >
            {shown.map((c) => (
              <Link
                href={href("/events", { class: String(c.id) })}
                key={c.id}
                style={{
                  width: `${(c.count / sum) * 100}%`,
                  background: c.color,
                }}
                aria-label={`${c.name} ${((c.count / sum) * 100).toFixed(1)}%`}
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
              {shown.map((c) => (
                <tr key={c.id}>
                  <td>
                    <Link href={href("/events", { class: String(c.id) })}>
                      <ClassName id={c.id} />
                    </Link>
                  </td>
                  <td>
                    <NumberLink
                      value={scaled(c.count, range)}
                      href={href("/events", { class: String(c.id) })}
                    />
                  </td>
                  <td>{`${((c.count / sum) * 100).toFixed(1)}%`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="panel-footnote">
            <Info size={12} />
            <span>
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
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Page path</th>
                  <th aria-sort="descending">
                    Requests <span className="sort-arrow">↓</span>
                  </th>
                  <th>Errors</th>
                  <th>Denied</th>
                </tr>
              </thead>
              <tbody>
                {pages.slice(0, 5).map((p) => {
                  const agentOnly: Record<string, string> = selected
                    ? {}
                    : { class: "1,2,3,4" };
                  return (
                  <tr key={p.id}>
                    <td>
                      <TextLink
                        className="path-link"
                        onClick={() => open("page", p.id)}
                      >
                        {p.path}
                      </TextLink>
                      {p.tag && <span className="page-tag">{p.tag}</span>}
                    </td>
                    <td>
                      <NumberLink
                        value={scaled(p.requests, range)}
                        href={href("/events", { path: p.path, ...agentOnly })}
                      />
                    </td>
                    <td>
                      <NumberLink
                        value={`${p.errors.toFixed(1)}%`}
                        href={href("/events", {
                          path: p.path,
                          status: "errors",
                          ...agentOnly,
                        })}
                      />
                    </td>
                    <td className={p.blocks > 10 ? "negative" : ""}>
                      <NumberLink
                        value={`${p.blocks.toFixed(1)}%`}
                        href={href("/events", {
                          path: p.path,
                          status: "denied",
                          ...agentOnly,
                        })}
                      />
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="panel-footnote">
            {selected
              ? "Counts include all pages for the selected classes."
              : "Agent traffic includes classes 1–4."}{" "}
            HTTP status does not prove task completion.
          </div>
        </Panel>
        <Panel title="What the data can show">
          <div className="coverage-content">
            <div className="coverage-source">
              <span>
                <Check size={13} /> CDN logs
              </span>
              <span>
                <Check size={13} /> Origin logs
              </span>
              <span className="source-paired">
                98% paired <Label />
              </span>
            </div>
            <div className="coverage-line">
              <span>Requests with unknown class</span>
              <Link href={href("/events", { class: "6" })}>
                31.0%
                <ArrowUpRight size={12} />
              </Link>
            </div>
            <div className="coverage-gap">
              <Label type="Unknown" />
              <p>
                Task completion, page content, clicks, and form steps are not
                visible in request logs.
              </p>
            </div>
            <div className="coverage-limit">
              <Info size={13} />
              <span>
                Browser requests without an edge signal remain{" "}
                <strong>Unknown</strong>.
              </span>
            </div>
          </div>
        </Panel>
      </div>
      <Panel
        title="Classification confidence"
        label="Inferred"
        className="confidence-panel"
        action={
          <Tip text="Each cell opens requests for one class and confidence level. Zero means no matching sample evidence." />
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
              {shown.map((c) => (
                <tr key={c.id}>
                  <td>
                    <ClassName id={c.id} full />
                  </td>
                  {(["high", "medium", "low"] as const).map((conf) => (
                    <td key={conf}>
                      <NumberLink
                        value={scaled(c[conf], range)}
                        href={href("/events", {
                          class: String(c.id),
                          confidence: conf[0].toUpperCase() + conf.slice(1),
                        })}
                      />
                    </td>
                  ))}
                  <td>
                    <NumberLink
                      value={scaled(c.count, range)}
                      href={href("/events", { class: String(c.id) })}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </>
  );
}
