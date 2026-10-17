"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  CircleAlert,
  FileText,
  Filter,
  GitBranch,
  Info,
  LockKeyhole,
  Sparkles,
  X,
} from "lucide-react";
import {
  agents,
  classes,
  filterEvents,
  filterSessions,
  imports,
  journeys,
  number,
  pages,
  rangeOf,
  recommendations,
  runs,
  scaled,
} from "@/lib/mock-data";
import {
  ClassName,
  Confidence,
  Empty,
  Href,
  Label,
  NumberLink,
  OpenDetail,
  Panel,
  CountLink,
  SearchField,
  Segmented,
  Select,
  Status,
  TableFooter,
  TextLink,
  Tip,
  TrafficChart,
} from "./shared";

export type Filters = {
  get: (key: string) => string | null;
  toString: () => string;
};
type Props = {
  href: Href;
  open: OpenDetail;
  filters: Filters;
  setFilter: (key: string, value: string) => void;
  reset: () => void;
};
const option = (values: string[], all: string) => [
  { value: "", label: all },
  ...values.map((v) => ({ value: v, label: v })),
];

export function Recommendations({
  href,
  open,
  filters,
  setFilter,
  reset,
}: Props) {
  const pattern = filters.get("pattern") || "",
    status = filters.get("status") || "",
    confidence = filters.get("confidence") || "";
  const previous = filters.get("run") === "13";
  // Run #13 predates rec-01 and rec-04; rec-05 was new in that run.
  const statusIn = (r: (typeof recommendations)[number]) =>
    previous ? (r.id === "rec-05" ? "New" : "Still open") : r.status;
  const selectedClasses = filters.get("class") || "";
  const list = recommendations.filter(
    (r) =>
      (!selectedClasses ||
        selectedClasses
          .split(",")
          .includes(
            String(agents.find((a) => a.id === r.agentId)?.classId),
          )) &&
      (!previous || !["rec-01", "rec-04"].includes(r.id)) &&
      (!pattern || r.pattern === pattern) &&
      (!status || statusIn(r) === status) &&
      (!confidence || r.confidence === confidence),
  );
  const changes = previous
    ? { added: 1, open: 3, gone: 0 }
    : { added: 2, open: 3, gone: 1 };
  return (
    <>
      <div className="run-summary">
        <span className="run-icon">
          <Sparkles size={16} />
        </span>
        <div>
          <strong>Recommendation run #{previous ? "13" : "14"}</strong>
          <span>
            Oct 16, 2026 · {previous ? "02:00–08:00" : "08:00–14:00"} · 6-hour
            window
          </span>
        </div>
        <div className="run-changes">
          <Status value={`${changes.added} new`} />
          <span>{changes.open} still open</span>
          <span>{changes.gone} gone</span>
        </div>
        <Select
          label="Recommendation run"
          value={previous ? "13" : "14"}
          onChange={(v) => setFilter("run", v)}
          options={[
            { value: "14", label: "Latest run #14" },
            { value: "13", label: "Previous run #13" },
          ]}
        />
      </div>
      <div className="filter-toolbar">
        <Filter size={14} />
        <Select
          label="Pattern"
          value={pattern}
          onChange={(v) => setFilter("pattern", v)}
          options={option(
            [...new Set(recommendations.map((r) => r.pattern))],
            "All patterns",
          )}
        />
        <Select
          label="Recommendation status"
          value={status}
          onChange={(v) => setFilter("status", v)}
          options={option(["New", "Still open"], "All statuses")}
        />
        <Select
          label="Confidence"
          value={confidence}
          onChange={(v) => setFilter("confidence", v)}
          options={option(["High", "Medium", "Low"], "All confidence")}
        />
        <span className="toolbar-end">
          {list.length} recommendations · sorted by priority
        </span>
      </div>
      <Panel
        title="Journeys to test"
        label="Inferred"
        action={
          <Tip text="Priority = Impact × Frequency × Severity × Confidence. Open a recommendation to inspect each factor." />
        }
      >
        {list.length ? (
          <>
          <div className="recommendation-cards">
            {list.map((r, i) => (
              <button
                key={r.id}
                className="recommendation-row"
                onClick={() => open("recommendation", r.id)}
              >
                <span className={`rank rank-${i}`}>{i + 1}</span>
                <span className="rec-main">
                  <span className="rec-title">{r.title}</span>
                  <span className="rec-meta">
                    {r.pattern}
                    <span>·</span>
                    {statusIn(r)}
                    <span>·</span>
                    {r.confidence} confidence
                  </span>
                </span>
                <span className="priority-score">
                  <strong>{r.score}</strong>
                  <span>priority</span>
                </span>
                <ChevronRight className="row-chevron" size={15} />
              </button>
            ))}
          </div>
          <div className="table-scroll recommendations-table-wrap">
            <table className="recommendations-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Recommended test</th>
                  <th aria-sort="descending">Priority ↓</th>
                  <th>Confidence</th>
                  <th>
                    Evidence <Label />
                  </th>
                </tr>
              </thead>
              <tbody>
                {list.map((r, i) => (
                  <tr key={r.id}>
                    <td className="muted">{i + 1}</td>
                    <td>
                      <TextLink
                        className="rec-table-title"
                        onClick={() => open("recommendation", r.id)}
                      >
                        {r.title}
                      </TextLink>
                      <div className="table-subline">
                        {r.pattern}
                        <Status value={statusIn(r)} />
                      </div>
                    </td>
                    <td>
                      <span className="score-button">{r.score}</span>
                    </td>
                    <td>
                      <Confidence value={r.confidence} />
                    </td>
                    <td>
                      <Link
                        className="number-link"
                        href={href("/sessions", { rec: r.id })}
                      >
                        {r.sessions} sessions
                      </Link>
                      <div className="table-subline">
                        <Link href={href("/events", { rec: r.id })}>
                          {r.events} events
                        </Link>
                      </div>
                    </td>
                  </tr>
                ))}
                {previous && !pattern && !status && !confidence && (
                  <tr>
                    <td className="muted">{list.length + 1}</td>
                    <td>
                      Check access to /rates
                      <div className="table-subline">
                        Blocked access
                        <Status value="Still open" />
                      </div>
                    </td>
                    <td colSpan={3} className="muted">
                      Gone in run #14 · evidence not in the sample
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          </>
        ) : (
          <Empty
            reset={reset}
            active={[
              pattern,
              status,
              confidence && `${confidence} confidence`,
              selectedClasses && "the selected traffic classes",
            ].filter(Boolean) as string[]}
          />
        )}
        <div className="panel-footnote">
          <Info size={13} />
          Recommendations suggest tests. They do not confirm the cause of an
          issue.
        </div>
      </Panel>
      {!previous && (
      <details className="disclosure-panel">
        <summary>
          <ChevronRight size={14} />
          <span>Gone since the previous run</span>
          <span className="count-chip">1</span>
        </summary>
        <div className="disclosure-body">
          <div className="gone-item">
            <span>Check access to /rates</span>
            <Status value="Gone" />
            <span className="muted">
              The blocked-request threshold was not met in run #14.
            </span>
          </div>
          <p className="muted">
            Gone means the pattern was absent in this window. It does not prove
            that the issue is fixed.
          </p>
        </div>
      </details>
      )}
      <Panel
        title="Run history"
        action={<span className="muted">Saved snapshots</span>}
      >
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Window</th>
                <th>Created</th>
                <th>New</th>
                <th>Still open</th>
                <th>Gone</th>
                <th>Rule version</th>
              </tr>
            </thead>
            <tbody>
              {[14, 13, 12].map((n, i) => (
                <tr key={n}>
                  <td>
                    #{n}
                    {n === 14 && <span className="page-tag">Latest</span>}
                    {(previous ? 13 : 14) === n && (
                      <span className="page-tag">Shown</span>
                    )}
                  </td>
                  <td>{["08:00–14:00", "02:00–08:00", "20:00–02:00"][i]}</td>
                  <td>
                    {["Oct 16, 14:02", "Oct 16, 08:02", "Oct 16, 02:02"][i]}
                  </td>
                  <td>{[2, 1, 1][i]}</td>
                  <td>{[3, 3, 2][i]}</td>
                  <td>{[1, 0, 1][i]}</td>
                  <td>
                    <code>v3</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      <div className="meta-line">
        <span>Rule v3</span>
        <span>Prompt v2</span>
        <span>Template text · fixed demo snapshot</span>
        <span>Created Oct 16, 2026 at {previous ? "08:02" : "14:02"}</span>
      </div>
    </>
  );
}

export function Agents({ href, open, filters, setFilter, reset }: Props) {
  const range = filters.get("range") || "24h";
  const search = filters.get("q") || "",
    verdict = filters.get("verdict") || "",
    selected = filters.get("class") || "";
  const list = agents.filter(
    (a) =>
      (!search ||
        `${a.name} ${a.vendor}`.toLowerCase().includes(search.toLowerCase())) &&
      (!verdict || a.verdict === verdict) &&
      (!selected || selected.split(",").includes(String(a.classId))),
  );
  return (
    <>
      <div className="inline-stats">
        <span>
          <strong>{number(24)}</strong> distinct agents <Label />
        </span>
        <span>
          <strong>4</strong> verified identities
        </span>
        <span>
          <strong>6</strong> traffic classes
        </span>
        <span className="muted">
          <Info size={13} />A user agent is a claim, not proof of identity.
        </span>
      </div>
      <div className="filter-toolbar">
        <SearchField
          placeholder="Search agents or vendors…"
          value={search}
          onChange={(v) => setFilter("q", v)}
        />
        <Select
          label="Verification"
          value={verdict}
          onChange={(v) => setFilter("verdict", v)}
          options={option(
            ["VERIFIED", "CLAIMED", "UNVERIFIED", "SPOOFED", "UNKNOWN"],
            "All verification",
          )}
        />
        <span className="toolbar-end">{list.length} agent groups</span>
      </div>
      <Panel
        title="Agent directory"
        label="Observed"
        action={
          <Tip text="Verified means the source IP matched the identity check. Other names are claims. Aggregated rows group similar unnamed clients." />
        }
      >
        {list.length ? (
          <div className="table-scroll">
            <table className="agents-table">
              <thead>
                <tr>
                  <th>Agent / client</th>
                  <th>Traffic class</th>
                  <th>Verification</th>
                  <th aria-sort="descending">Requests ↓</th>
                  <th>Sessions</th>
                  <th>Pages</th>
                  <th>Last seen</th>
                </tr>
              </thead>
              <tbody>
                {list.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <button
                        className="agent-cell"
                        onClick={() => open("agent", a.id)}
                      >
                        <span
                          className="agent-symbol"
                          style={{ color: a.color }}
                        >
                          {a.symbol}
                        </span>
                        <span>
                          <strong>{a.name}</strong>
                          <small>
                            {a.id === "other-bots"
                              ? "Grouped clients · names are claims"
                              : a.verdict === "CLAIMED" ||
                                  a.verdict === "UNVERIFIED"
                                ? `Claims to be ${a.name}, unverified`
                                : a.vendor}
                          </small>
                        </span>
                      </button>
                    </td>
                    <td>
                      <ClassName id={a.classId} />
                    </td>
                    <td>
                      <Status value={a.verdict} />
                    </td>
                    <td>
                      <NumberLink
                        value={scaled(a.requests, range)}
                        href={href("/events", { agent: a.id })}
                      />
                    </td>
                    <td>
                      <NumberLink
                        value={scaled(a.sessions, range)}
                        href={href("/sessions", { agent: a.id })}
                      />
                    </td>
                    <td>
                      {a.pages}
                    </td>
                    <td className="mono muted">{a.last}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            reset={reset}
            active={[search && `“${search}”`, verdict].filter(Boolean)}
          />
        )}
        <TableFooter
          count={list.length}
          total="24 distinct agents"
          noun="agent groups"
        />
      </Panel>
      <div className="notice">
        <Info size={15} />
        <div>
          <strong>Some traffic cannot be identified.</strong>
          <p>
            Browser requests without an edge signal remain Unknown. A shared IP
            can include more than one agent.
          </p>
        </div>
        <button className="text-link" onClick={() => open("legend", "labels")}>
          Read the label guide
          <ArrowRight size={13} />
        </button>
      </div>
    </>
  );
}

export function Activity({
  href,
  open,
  filters,
  setFilter,
  reset,
  isSessions,
}: Props & { isSessions: boolean }) {
  const search = filters.get("q") || "",
    status = filters.get("status") || "",
    selected = filters.get("class") || "",
    agent = filters.get("agent") || "",
    range = filters.get("range") || "24h";
  const filtered = filterEvents({
    classId: selected,
    status,
    agent,
    path: filters.get("path") || "",
    session: filters.get("session") || "",
    source: filters.get("source") || "",
    confidence: filters.get("confidence") || "",
    verdict: filters.get("verdict") || "",
    rec: filters.get("rec") || "",
    since: rangeOf(range).since,
    search,
  }).sort((a, b) => b.time.localeCompare(a.time));
  const sessionList = filterSessions({
    classId: selected,
    agent,
    confidence: filters.get("confidence") || "",
    state: filters.get("state") || "",
    retry: filters.get("retry") || "",
    loop: filters.get("loop") || "",
    path: filters.get("path") || "",
    journey: filters.get("journey") || "",
    reached: filters.get("reached") || "",
    rec: filters.get("rec") || "",
    since: rangeOf(range).since,
    search,
  }).sort((a, b) => b.started.localeCompare(a.started));
  const list = filtered;
  const rec = recommendations.find((r) => r.id === filters.get("rec"));
  // Filters without their own control on this page. Each one gets a chip.
  const hidden = [
    ["path", "Path"],
    ["session", "Session"],
    ["confidence", "Confidence"],
    ["verdict", "Verification"],
    ["journey", "Journey"],
    ["reached", "Reached step"],
  ].filter(([k]) => filters.get(k));
  const chipValue = (k: string) =>
    k === "journey"
      ? journeys.find((j) => j.id === filters.get(k))?.name || filters.get(k)
      : filters.get(k);
  // Tabs keep the filters that apply to both events and sessions.
  const shared = Object.fromEntries(
    // Events-only and sessions-only keys ride along and wait for the way back.
    [
      "agent",
      "q",
      "path",
      "confidence",
      "rec",
      "status",
      "source",
      "state",
      "retry",
      "loop",
    ]
      .map((k) => [k, filters.get(k) || ""])
      .filter(([, v]) => v),
  );
  const agentName = agents.find((a) => a.id === agent)?.name;
  const active = [
    rec && `the evidence for “${rec.title}”`,
    selected &&
      `class ${selected
        .split(",")
        .map((id) => classes.find((c) => String(c.id) === id)?.short)
        .join(", ")}`,
    search && `“${search}”`,
    agentName,
    !isSessions && status && `status ${status}`,
    !isSessions && filters.get("source") && `source ${filters.get("source")}`,
    isSessions && filters.get("state") && `state ${filters.get("state")}`,
    isSessions && filters.get("retry") && "has retry",
    isSessions && filters.get("loop") && "has loop",
    ...hidden.map(([k, label]) => `${label.toLowerCase()} ${chipValue(k)}`),
  ].filter(Boolean) as string[];
  const narrowed = active.length > 0;
  const eventTotal = scaled(128432, range),
    sessionTotal = scaled(9955, range);
  return (
    <>
      <div className="page-tabs">
        <Link
          className={!isSessions ? "active" : ""}
          aria-current={!isSessions ? "page" : undefined}
          href={href("/events", shared)}
        >
          Events
          <span>{number(narrowed ? filtered.length : eventTotal)}</span>
        </Link>
        <Link
          className={isSessions ? "active" : ""}
          aria-current={isSessions ? "page" : undefined}
          href={href("/sessions", shared)}
        >
          Sessions
          <span>
            {number(narrowed ? sessionList.length : sessionTotal)}
          </span>
        </Link>
      </div>
      <div className="filter-toolbar">
        <SearchField
          placeholder={
            isSessions
              ? "Search sessions or agents…"
              : "Search paths or agents…"
          }
          value={search}
          onChange={(v) => setFilter("q", v)}
        />
        <Select
          label="Agent"
          value={agent}
          onChange={(v) => setFilter("agent", v)}
          options={[
            { value: "", label: "All agents" },
            ...agents.map((a) => ({ value: a.id, label: a.name })),
          ]}
        />
        {isSessions ? (
          <>
            <Select
              label="Session state"
              value={filters.get("state") || ""}
              onChange={(v) => setFilter("state", v)}
              options={option(["Closed", "In progress"], "All states")}
            />
            <button
              className={`filter-chip ${filters.get("retry") ? "selected" : ""}`}
              onClick={() =>
                setFilter("retry", filters.get("retry") ? "" : "yes")
              }
            >
              Has retry
            </button>
            <button
              className={`filter-chip ${filters.get("loop") ? "selected" : ""}`}
              onClick={() =>
                setFilter("loop", filters.get("loop") ? "" : "yes")
              }
            >
              Has loop
            </button>
          </>
        ) : (
          <>
            <Select
              label="HTTP status"
              value={status}
              onChange={(v) => setFilter("status", v)}
              options={[
                { value: "", label: "All status codes" },
                { value: "200", label: "200 · OK" },
                { value: "403", label: "403 · Forbidden" },
                { value: "429", label: "429 · Rate limited" },
                { value: "denied", label: "Denied · 403 / 429" },
                { value: "errors", label: "All errors" },
              ]}
            />
            <Select
              label="Source"
              value={filters.get("source") || ""}
              onChange={(v) => setFilter("source", v)}
              options={option(["Paired", "CDN", "Origin"], "All sources")}
            />
          </>
        )}
      </div>
      {rec && (
        <div className="evidence-context" role="note">
          <Sparkles size={14} />
          <span>
            <span>
              Evidence for <strong>{rec.title}</strong>
            </span>
            <small>
              {isSessions
                ? `${sessionList.length} of ${rec.sessions} matching sessions are in the sample`
                : `${filtered.length} of ${rec.events} matching requests are in the sample`}{" "}
              · {rec.agent}
            </small>
          </span>
          <Link
            className="text-link"
            href={href(`/recommendations/${rec.id}`)}
          >
            <ArrowLeft size={13} />
            Back to recommendation
          </Link>
          <button
            className="icon-button"
            aria-label="Remove recommendation filter"
            onClick={() => setFilter("rec", "")}
          >
            <X size={13} />
          </button>
        </div>
      )}
      {hidden.length > 0 && (
        <div className="active-filters">
          {hidden.map(([k, label]) => (
            <button
              key={k}
              aria-label={`Remove filter ${label} ${chipValue(k)}`}
              onClick={() => setFilter(k, "")}
            >
              {label}: {chipValue(k)}
              <X size={11} />
            </button>
          ))}
          <button onClick={reset}>Clear filters</button>
        </div>
      )}
      <Panel
        title={isSessions ? "Session activity" : "Event volume"}
        label="Observed"
        className="activity-chart"
        action={
          active.length ? (
            <span className="muted">
              All requests · only the class filter applies
            </span>
          ) : undefined
        }
      >
        <TrafficChart compact href={href} selected={selected} range={range} />
      </Panel>
      <Panel
        title={isSessions ? "Sessions" : "Request events"}
        label="Observed"
        action={
          <span className="muted">
            {isSessions ? sessionList.length : filtered.length} matching{" "}
            {isSessions ? "session" : "event"}
            {(isSessions ? sessionList.length : filtered.length) === 1
              ? ""
              : "s"}
          </span>
        }
      >
        {isSessions ? (
          sessionList.length ? (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Session</th>
                    <th>Agent / client</th>
                    <th>Confidence</th>
                    <th>Started</th>
                    <th>State</th>
                    <th>Requests</th>
                    <th>Pages</th>
                    <th>Signals</th>
                    <th>Reached</th>
                  </tr>
                </thead>
                <tbody>
                  {sessionList.map((s) => {
                    const a = agents.find((a) => a.id === s.agentId)!;
                    return (
                      <tr key={s.id}>
                        <td>
                          <TextLink
                            className="mono"
                            onClick={() => open("session", s.id)}
                          >
                            {s.id}
                          </TextLink>
                        </td>
                        <td>
                          <TextLink onClick={() => open("agent", a.id)}>
                            {a.name}
                          </TextLink>
                          <div className="table-subline">
                            <ClassName id={a.classId} />
                          </div>
                        </td>
                        <td>
                          <Confidence value={s.confidence} />
                        </td>
                        <td className="mono muted">{s.started}</td>
                        <td>
                          <Status value={s.state} />
                        </td>
                        <td>
                          <NumberLink
                            value={s.requests}
                            href={href("/events", { session: s.id })}
                          />
                        </td>
                        <td>{s.pageCount}</td>
                        <td>
                          <div className="signal-tags">
                            {s.retry && <span>Retry</span>}
                            {s.loop && <span>Loop</span>}
                            {!s.retry && !s.loop && (
                              <span className="muted">—</span>
                            )}
                          </div>
                        </td>
                        <td>
                          Step {s.reached}
                          <span className="table-subline">Outcome unknown</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty reset={reset} active={active} />
          )
        ) : list.length ? (
          <div className="table-scroll">
            <table className="events-table">
              <thead>
                <tr>
                  <th aria-sort="descending">Time ↓</th>
                  <th>Request path</th>
                  <th>Status</th>
                  <th>Method</th>
                  <th>Traffic class</th>
                  <th>Agent</th>
                  <th>Verification</th>
                  <th>Source</th>
                  <th>Session</th>
                </tr>
              </thead>
              <tbody>
                {list.map((e) => {
                  const a = agents.find((a) => a.id === e.agentId)!;
                  return (
                    <tr key={e.id}>
                      <td className="mono">{e.time}</td>
                      <td>
                        <TextLink
                          className="mono path-link"
                          onClick={() => open("event", e.id)}
                        >
                          {e.path}
                        </TextLink>
                      </td>
                      <td>
                        <span
                          className={`http-code ${e.status >= 400 ? "error" : "ok"}`}
                        >
                          {e.status}
                        </span>
                      </td>
                      <td>
                        <span className="method">{e.method}</span>
                      </td>
                      <td>
                        <ClassName id={e.classId} />
                      </td>
                      <td>
                        <TextLink onClick={() => open("agent", a.id)}>
                          {a.name}
                        </TextLink>
                      </td>
                      <td>
                        <Status value={e.verdict} />
                      </td>
                      <td>
                        <span
                          className={`source-badge ${e.source.toLowerCase()}`}
                        >
                          {e.source}
                        </span>
                      </td>
                      <td>
                        <TextLink
                          className="mono muted"
                          onClick={() => open("session", e.sessionId)}
                        >
                          {e.sessionId}
                        </TextLink>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty reset={reset} active={active} />
        )}
        <TableFooter
          count={isSessions ? sessionList.length : list.length}
          total={
            narrowed
              ? undefined
              : isSessions
                ? `${number(sessionTotal)} sessions`
                : `${number(eventTotal)} requests`
          }
          noun={`${narrowed ? "matching " : ""}${isSessions ? "session" : "event"}${(isSessions ? sessionList.length : list.length) === 1 ? "" : "s"}`}
        />
      </Panel>
      <div className="meta-line">
        <Label type="Inferred" />
        <span>Sessions group requests by client and time gap.</span>
        <Label type="Unknown" />
        <span>Logs cannot show task completion.</span>
      </div>
    </>
  );
}

export function PagesJourneys({
  href,
  open,
  filters,
  setFilter,
  reset,
  isJourneys,
}: Props & { isJourneys: boolean }) {
  const search = filters.get("q") || "",
    preset = filters.get("preset") || "",
    range = filters.get("range") || "24h",
    classFiltered = Boolean(filters.get("class"));
  const presetTests: Record<string, (p: (typeof pages)[number]) => boolean> =
    {
      "": () => true,
      errors: (p) => p.errors > 0,
      blocks: (p) => p.blocks > 0,
      retries: (p) => p.retries > 0,
      unreached: (p) => p.requests === 0,
    };
  const searched = pages.filter(
    (p) => !search || p.path.toLowerCase().includes(search.toLowerCase()),
  );
  // Counts follow the search, so each choice shows what it will return.
  const presets = [
    { value: "", label: "All pages" },
    { value: "errors", label: "Errors" },
    { value: "blocks", label: "Blocks" },
    { value: "retries", label: "Retries" },
    { value: "unreached", label: "Never reached" },
  ].map((p) => ({ ...p, count: searched.filter(presetTests[p.value]).length }));
  const list = searched.filter(presetTests[preset] || presetTests[""]);
  return (
    <>
      <div className="page-tabs">
        <Link
          className={!isJourneys ? "active" : ""}
          aria-current={!isJourneys ? "page" : undefined}
          href={href("/pages")}
        >
          Pages<span>156</span>
        </Link>
        <Link
          className={isJourneys ? "active" : ""}
          aria-current={isJourneys ? "page" : undefined}
          href={href("/journeys")}
        >
          Journeys<span>3</span>
        </Link>
      </div>
      {isJourneys ? (
        <>
          <div className="notice compact-notice">
            <Info size={15} />
            <span>
              Step counts show pages reached. They do not show task completion.
            </span>
            <Label type="Unknown" />
          </div>
          <div className="journey-list">
            {journeys.map((j) => (
              <Panel
                key={j.id}
                title={j.name}
                action={
                  <>
                    <span
                      className={`journey-critical ${j.critical ? "critical" : ""}`}
                    >
                      {j.critical ? "Critical journey" : "Standard journey"}
                    </span>
                  </>
                }
              >
                <div className="journey-description">
                  {j.description}
                  <Label />
                </div>
                <div className="journey-steps">
                  {j.steps.map((step, i) => (
                    <div className="journey-step" key={step}>
                      <div className="step-top">
                        <span className="step-number">{i + 1}</span>
                        <span className="mono">{step}</span>
                        {i < j.steps.length - 1 && <ArrowRight size={14} />}
                      </div>
                      <CountLink
                        href={href("/sessions", {
                          journey: j.id,
                          reached: String(i + 1),
                        })}
                      >
                        {number(j.counts[i])}
                        <span>sessions reached</span>
                      </CountLink>
                      <div className="step-bar">
                        <span
                          style={{
                            width: `${Math.max(1, (j.counts[i] / j.counts[0]) * 100)}%`,
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
                <div className="journey-foot">
                  <span className="amber-text">
                    {j.retry} sessions with retries or loops
                  </span>
                  <span>
                    Task outcome <strong>Unknown</strong>
                  </span>
                  <button
                    className="text-link"
                    onClick={() => open("journey", j.id)}
                  >
                    View evidence
                    <ArrowRight size={13} />
                  </button>
                </div>
              </Panel>
            ))}
          </div>
        </>
      ) : (
        <>
          <div className="filter-toolbar">
            <SearchField
              placeholder="Search page paths…"
              value={search}
              onChange={(v) => setFilter("q", v)}
            />
            <Segmented
              label="Show pages"
              value={presetTests[preset] ? preset : ""}
              onChange={(v) => setFilter("preset", v)}
              options={presets}
            />
            <span className="toolbar-end">
              {classFiltered && "Page totals include all classes · "}
              {list.length} sample pages · sorted by agent requests
            </span>
          </div>
          <Panel title="Pages" label="Observed">
            {list.length ? (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Page path</th>
                      <th aria-sort="descending">Agent requests ↓</th>
                      <th>Sessions</th>
                      <th>Agents</th>
                      <th>Error rate</th>
                      <th>Denial rate</th>
                      <th>Retries</th>
                      <th>Median bytes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.map((p) => (
                      <tr key={p.id}>
                        <td>
                          <TextLink
                            className="mono path-link"
                            onClick={() => open("page", p.id)}
                          >
                            {p.path}
                          </TextLink>
                          {p.tag && <span className="page-tag">{p.tag}</span>}
                        </td>
                        <td>
                          <NumberLink
                            value={scaled(p.requests, range)}
                            href={href("/events", { path: p.path })}
                          />
                        </td>
                        <td>
                          <NumberLink
                            value={scaled(p.sessions, range)}
                            href={href("/sessions", { path: p.path })}
                          />
                        </td>
                        <td>{p.agents}</td>
                        <td>
                          <NumberLink
                            value={`${p.errors.toFixed(1)}%`}
                            href={href("/events", {
                              path: p.path,
                              status: "errors",
                            })}
                          />
                        </td>
                        <td className={p.blocks > 10 ? "negative" : ""}>
                          <NumberLink
                            value={`${p.blocks.toFixed(1)}%`}
                            href={href("/events", {
                              path: p.path,
                              status: "denied",
                            })}
                          />
                        </td>
                        <td>
                          <NumberLink
                            value={p.retries}
                            href={href("/sessions", {
                              path: p.path,
                              retry: "yes",
                            })}
                          />
                        </td>
                        <td className="mono muted">{p.bytes}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <Empty
                reset={reset}
                active={[
                  search && `“${search}”`,
                  preset && presets.find((x) => x.value === preset)?.label,
                ].filter(Boolean) as string[]}
              />
            )}
            <TableFooter count={list.length} total="156 pages" noun="pages" />
          </Panel>
          <div className="notice">
            <GitBranch size={16} />
            <div>
              <strong>Look beyond a single page.</strong>
              <p>
                See how far agents reach in your key journeys, and where they
                retry.
              </p>
            </div>
            <Link className="text-link" href={href("/journeys")}>
              Explore journeys
              <ArrowRight size={13} />
            </Link>
          </div>
        </>
      )}
    </>
  );
}

export function DataPipeline({ href, open, filters }: Props) {
  const tab = filters.get("tab") || "sources";
  return (
    <>
      <div className="health-strip">
        <span>
          <i className="live-dot" />
          <strong>Fast lane healthy</strong>
          <span>Last complete 14:05</span>
        </span>
        <span>
          <i className="live-dot" />
          <strong>Recommendations healthy</strong>
          <span>Last complete 14:02</span>
        </span>
        {tab === "health" ? (
          <span className="amber-text">
            <CircleAlert size={12} />1 open alert · store.example.com
          </span>
        ) : (
          <Link className="amber-text" href={href("/data", { tab: "health" })}>
            <CircleAlert size={12} />1 open alert · store.example.com
          </Link>
        )}
      </div>
      <div className="page-tabs">
        {[
          { id: "sources", name: "Sources" },
          { id: "imports", name: "Import runs" },
          { id: "runs", name: "Pipeline runs" },
          { id: "health", name: "Health & alerts" },
          { id: "settings", name: "Settings" },
        ].map((t) => (
          <Link
            key={t.id}
            className={tab === t.id ? "active" : ""}
            aria-current={tab === t.id ? "page" : undefined}
            href={href("/data", { tab: t.id })}
            scroll={false}
          >
            {t.name}
          </Link>
        ))}
      </div>
      {tab === "sources" && (
        <>
          <Panel
            title="Data sources"
            label="Observed"
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Site / source</th>
                    <th>Format</th>
                    <th>Last file</th>
                    <th>Last event</th>
                    <th>Origin pairing</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <strong>example.com</strong>
                      <div className="table-subline">CDN log</div>
                    </td>
                    <td>
                      <code>edge-field-map.yaml</code>
                    </td>
                    <td className="mono">14:01:08</td>
                    <td className="mono">14:04:59</td>
                    <td>98.0%</td>
                    <td>
                      <Status value="Healthy" />
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <strong>example.com</strong>
                      <div className="table-subline">Origin log</div>
                    </td>
                    <td>
                      <code>nginx combined</code>
                    </td>
                    <td className="mono">14:00:42</td>
                    <td className="mono">14:04:52</td>
                    <td className="muted">—</td>
                    <td>
                      <Status value="Healthy" />
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <strong>store.example.com</strong>
                      <div className="table-subline">Origin log</div>
                    </td>
                    <td>
                      <code>nginx combined</code>
                    </td>
                    <td className="mono">12:58:14</td>
                    <td className="mono">12:57:48</td>
                    <td>
                      <Label type="Unknown" />
                    </td>
                    <td>
                      <span className="amber-text">
                        <CircleAlert size={12} />
                        No data &gt; 1h
                      </span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>
          <div className="two-column equal-columns">
            <Panel title="Source coverage" label="Observed">
              <div className="coverage-summary">
                <strong>
                  98.0% <span>origin requests paired</span>
                </strong>
                <div className="pairing-bar">
                  <span />
                </div>
                <p>
                  CDN and origin records share a request ID. A paired record
                  counts as one request.
                </p>
                <Link
                  className="text-link"
                  href={href("/events", { source: "Paired" })}
                >
                  Inspect paired requests
                  <ArrowRight size={13} />
                </Link>
              </div>
            </Panel>
            <Panel title="Current data gaps" label="Unknown">
              <div className="gap-list">
                <div>
                  <CircleAlert size={15} />
                  <span>
                    <strong>store.example.com has no CDN log</strong>
                    <p>Edge blocks cannot be measured for this site.</p>
                  </span>
                </div>
                <div>
                  <Info size={15} />
                  <span>
                    <strong>Task outcomes are not visible</strong>
                    <p>
                      Request logs cannot show content, clicks, or form
                      completion.
                    </p>
                  </span>
                </div>
              </div>
            </Panel>
          </div>
        </>
      )}
      {tab === "imports" && (
        <Panel title="Import runs" label="Observed">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>File</th>
                  <th>Source</th>
                  <th>Received</th>
                  <th>Status</th>
                  <th>Lines</th>
                  <th>Imported</th>
                  <th>Rejected</th>
                  <th>Duplicates</th>
                </tr>
              </thead>
              <tbody>
                {imports.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <TextLink
                        className="mono"
                        onClick={() => open("import", r.id)}
                      >
                        {r.file.replace("bank-", "example-")}
                      </TextLink>
                    </td>
                    <td>{r.source}</td>
                    <td className="mono">{r.received}</td>
                    <td>
                      <Status value={r.status} />
                    </td>
                    <td>{number(r.lines)}</td>
                    <td>{number(r.imported)}</td>
                    <td className={r.rejected ? "amber-text" : "muted"}>
                      {r.rejected}
                    </td>
                    <td className="muted">{r.duplicates}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <TableFooter count={5} noun="import runs" />
        </Panel>
      )}
      {tab === "runs" && (
        <Panel title="Pipeline runs" label="Observed">
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Lane</th>
                  <th>Started</th>
                  <th>Duration</th>
                  <th>Status</th>
                  <th>Processed / failed step</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <TextLink
                        className="mono"
                        onClick={() => open("run", r.id)}
                      >
                        {r.id}
                      </TextLink>
                    </td>
                    <td>{r.lane}</td>
                    <td className="mono">{r.started}</td>
                    <td className="mono">{r.duration}</td>
                    <td>
                      <Status value={r.status} />
                    </td>
                    <td
                      className={r.status === "Failed" ? "negative" : "muted"}
                    >
                      {r.count}
                    </td>

                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <TableFooter count={5} noun="pipeline runs" />
        </Panel>
      )}
      {tab === "health" && (
        <>
          <Panel title="Health" label="Observed">
            <div className="health-rows">
              <div>
                <Check size={16} />
                <strong>Fast lane</strong>
                <span>Last complete · 14:05</span>
                <Status value="Healthy" />
              </div>
              <div>
                <Check size={16} />
                <strong>Recommendation lane</strong>
                <span>Last complete · 14:02</span>
                <Status value="Healthy" />
              </div>
            </div>
          </Panel>
          <Panel
            title="Alerts"
            action={<span className="amber-text">1 open</span>}
          >
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Alert</th>
                    <th>Site</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="mono">13:58</td>
                    <td>
                      <Link
                        className="amber-text text-link"
                        href={href("/data", { tab: "sources" })}
                      >
                        No new logs for more than 1 hour
                      </Link>
                    </td>
                    <td>store.example.com</td>
                    <td>
                      <Status value="Open" />
                    </td>
                  </tr>
                  <tr>
                    <td className="mono">13:55</td>
                    <td>
                      <TextLink onClick={() => open("run", "run-1840")}>
                        Verify step failed
                      </TextLink>
                    </td>
                    <td>example.com</td>
                    <td>
                      <span className="muted">Cleared at 14:00</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
      {tab === "settings" && (
        <>
          <div className="notice compact-notice">
            <LockKeyhole size={14} />
            <span>
              Configuration is read-only. These values are a sample
              configuration.
            </span>
          </div>
          <Panel
            title="Site configuration"
            action={<code className="muted">v3 · Oct 16, 2026</code>}
          >
            <div className="settings-grid">
              <div>
                <h3>Key pages</h3>
                <p className="code-list">
                  /cards
                  <br />
                  /products
                  <br />
                  /pricing
                  <br />
                  /rates
                </p>
              </div>
              <div>
                <h3>Conversion pages</h3>
                <p className="code-list">
                  /cards/apply
                  <br />
                  /apply
                  <br />
                  /accounts/open/done
                </p>
              </div>
              <div>
                <h3>Journeys</h3>
                {journeys.map((j) => (
                  <p key={j.id}>
                    {j.name}
                    {j.critical && <span className="page-tag">Critical</span>}
                  </p>
                ))}
              </div>
              <div>
                <h3>Access policy</h3>
                <p>robots.txt snapshot · Oct 16</p>
                <p className="muted">Key pages allow crawler access.</p>
              </div>
            </div>
          </Panel>
          <Panel title="Rules & registry">
            <dl className="config-list">
              <div>
                <dt>Recommendation window</dt>
                <dd>6 hours</dd>
              </div>
              <div>
                <dt>Pattern thresholds</dt>
                <dd>3 key pages · 5 blocked requests · 3 retry sessions</dd>
              </div>
              <div>
                <dt>Session gap</dt>
                <dd>30 minutes · agent clients: 2 minutes</dd>
              </div>
              <div>
                <dt>Identity registry</dt>
                <dd>v12 · 24 agents · IP snapshot: Oct 16, 2026</dd>
              </div>
              <div>
                <dt>Rule / prompt</dt>
                <dd>v3 / v2</dd>
              </div>
              <div>
                <dt>Source retention</dt>
                <dd>7 days after a complete import</dd>
              </div>
              <div>
                <dt>Sitemap</dt>
                <dd>156 URLs · 18 key-content URLs</dd>
              </div>
            </dl>
          </Panel>
        </>
      )}
      <div className="meta-line">
        <FileText size={12} />
        <span>
          All files, runs, and health states are fixed sample records.
        </span>
      </div>
    </>
  );
}
