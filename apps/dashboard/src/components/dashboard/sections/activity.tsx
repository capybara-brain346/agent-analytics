"use client";

import { useState } from "react";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Sparkles, X } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useApi, useScopedApi } from "@/lib/api/use-api";
import type {
  AgentRow,
  EventRow,
  Paged,
  RecommendationDetail,
  SessionRow,
} from "@/lib/api/types";
import { classOf } from "@/lib/classes";
import { capitalize, dateTimeUTC, number } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Confidence,
  Empty,
  Gap,
  Label,
  LoadingState,
  Panel,
  SearchField,
  Select,
  Status,
  TextLink,
} from "../shared";
import type { Props } from "./common";

const PAGE_SIZE = 50;

// Old and short URL values -> what the API accepts.
const statusParam = (v: string) =>
  v === "denied" ? "403,429" : v === "errors" ? "4xx,5xx" : v;
const stateParam = (v: string) =>
  v.toLowerCase().replace(/\s+/g, "_") === "in_progress"
    ? "in_progress"
    : v.toLowerCase() === "closed"
      ? "closed"
      : "";

type Query = Record<string, string | number | boolean | undefined>;
const clean = (q: Query): Query =>
  Object.fromEntries(
    Object.entries(q).filter(([, v]) => v !== "" && v !== undefined),
  );

function PagerFooter({
  page,
  shown,
  noun,
  onPage,
}: {
  page: { offset: number; total: number; next_offset: number | null };
  shown: number;
  noun: string;
  onPage: (offset: number) => void;
}) {
  const from = shown ? page.offset + 1 : 0;
  return (
    <div className="table-footer">
      <span>
        Showing {number(from)}–{number(page.offset + shown)} of{" "}
        {number(page.total)} {noun}
        {page.total === 1 ? "" : "s"} in this window
      </span>
      <span className="pager">
        <button
          className="text-link"
          disabled={page.offset === 0}
          onClick={() => onPage(Math.max(0, page.offset - PAGE_SIZE))}
        >
          <ArrowLeft size={13} />
          Previous
        </button>{" "}
        <button
          className="text-link"
          disabled={page.next_offset === null}
          onClick={() => page.next_offset !== null && onPage(page.next_offset)}
        >
          Next
          <ArrowRight size={13} />
        </button>
      </span>
    </div>
  );
}

function EventsTable({
  rows,
  open,
}: {
  rows: EventRow[];
  open: Props["open"];
}) {
  return (
    <div className="table-scroll">
      <table className="events-table">
        <thead>
          <tr>
            <th aria-sort="descending">Time (UTC) ↓</th>
            <th>Request path</th>
            <th>Status</th>
            <th>Method</th>
            <th>Traffic class</th>
            <th>Agent (claimed)</th>
            <th>Verification</th>
            <th>Confidence</th>
            <th>Source</th>
            <th>Session</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((e) => (
            <tr key={e.id}>
              <td className="mono">{dateTimeUTC(e.ts)}</td>
              <td>
                <TextLink
                  className="mono path-link"
                  onClick={() => open("event", String(e.id))}
                >
                  {e.path}
                </TextLink>
              </td>
              <td>
                {e.status === null ? (
                  <span className="muted">Unknown</span>
                ) : (
                  <span
                    className={`http-code ${e.status >= 400 ? "error" : "ok"}`}
                  >
                    {e.status}
                  </span>
                )}
              </td>
              <td>
                <span className="method">{e.method ?? "—"}</span>
              </td>
              <td>
                {e.traffic_class ? (
                  <ClassName id={e.traffic_class} />
                ) : (
                  <span className="muted">Unclassified</span>
                )}
              </td>
              <td>
                {e.claimed_agent ? (
                  <>
                    <TextLink onClick={() => open("agent", e.claimed_agent!)}>
                      {e.claimed_agent}
                    </TextLink>
                    {e.verdict !== "VERIFIED" && (
                      <div className="table-subline">claimed, unverified</div>
                    )}
                  </>
                ) : (
                  <span className="muted">No agent name</span>
                )}
              </td>
              <td>
                {e.verdict ? (
                  <Status value={e.verdict} />
                ) : (
                  <span className="muted">Unknown</span>
                )}
              </td>
              <td>
                {e.confidence ? (
                  <Confidence value={capitalize(e.confidence)} />
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>
                <span className={`source-badge ${e.source.toLowerCase()}`}>
                  {capitalize(e.source)}
                </span>
              </td>
              <td>
                {e.session_id ? (
                  <TextLink
                    className="mono muted"
                    onClick={() => open("session", e.session_id!)}
                  >
                    {e.session_id}
                  </TextLink>
                ) : (
                  <span className="muted">None</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SessionsTable({
  rows,
  open,
  href,
}: {
  rows: SessionRow[];
  open: Props["open"];
  href: Props["href"];
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Session</th>
            <th>Agent / client</th>
            <th>Confidence</th>
            <th>Started (UTC)</th>
            <th>Last seen (UTC)</th>
            <th>State</th>
            <th>Requests</th>
            <th>Pages</th>
            <th>Signals</th>
            <th>Reached</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((s) => {
            const journeys = Object.entries(s.journeys_reached);
            return (
              <tr key={s.session_id}>
                <td>
                  <TextLink
                    className="mono"
                    onClick={() => open("session", s.session_id)}
                  >
                    {s.session_id}
                  </TextLink>
                </td>
                <td>
                  {s.agent ? (
                    <TextLink onClick={() => open("agent", s.agent!)}>
                      {s.agent}
                    </TextLink>
                  ) : (
                    <span className="muted">No agent name</span>
                  )}
                  {s.traffic_class && (
                    <div className="table-subline">
                      <ClassName id={s.traffic_class} />
                    </div>
                  )}
                </td>
                <td>
                  {s.confidence ? (
                    <Confidence value={capitalize(s.confidence)} />
                  ) : (
                    <span className="muted">—</span>
                  )}
                </td>
                <td className="mono muted">{dateTimeUTC(s.started)}</td>
                <td className="mono muted">{dateTimeUTC(s.last_seen)}</td>
                <td>
                  <Status value={s.in_progress ? "In progress" : "Closed"} />
                </td>
                <td>
                  <Link
                    className="number-link"
                    href={href("/events", { session: s.session_id })}
                  >
                    {number(s.requests)}
                  </Link>
                </td>
                <td>{number(s.distinct_pages)}</td>
                <td>
                  <div className="signal-tags">
                    {s.has_retry && <span>Retry</span>}
                    {s.has_loop && <span>Loop</span>}
                    {!s.has_retry && !s.has_loop && (
                      <span className="muted">—</span>
                    )}
                  </div>
                </td>
                <td>
                  {journeys.length ? (
                    journeys.map(([id, step]) => (
                      <div key={id}>
                        {id}: step {step}
                      </div>
                    ))
                  ) : (
                    <span className="muted">No journey step</span>
                  )}
                  {s.reached_conversion && (
                    <div className="table-subline">Conversion page reached</div>
                  )}
                  <span className="table-subline">Outcome unknown</span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// The API cannot filter by recommendation. Show the evidence it names instead.
function RecEvidence({
  id,
  isSessions,
  open,
  href,
  onRemove,
}: {
  id: string;
  isSessions: boolean;
  open: Props["open"];
  href: Props["href"];
  onRemove: () => void;
}) {
  const state = useApi<RecommendationDetail>(
    `recommendations/${encodeURIComponent(id)}`,
  );
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={2} />}>
      {(r) => {
        const ids = isSessions
          ? r.evidence.session_ids
          : r.evidence.event_ids.map(String);
        return (
          <>
            <div className="evidence-context" role="note">
              <Sparkles size={14} />
              <span>
                <span>
                  Evidence for <strong>{r.target}</strong>
                </span>
                <small>
                  {number(r.evidence.events_count)} requests ·{" "}
                  {number(r.evidence.sessions_count)} sessions ·{" "}
                  {r.pattern_name}
                </small>
              </span>
              <Link
                className="text-link"
                href={href(`/recommendations/${r.id}`)}
              >
                <ArrowLeft size={13} />
                Back to recommendation
              </Link>
              <button
                className="icon-button"
                aria-label="Remove recommendation filter"
                onClick={onRemove}
              >
                <X size={13} />
              </button>
            </div>
            <Panel
              title={isSessions ? "Evidence sessions" : "Evidence requests"}
              label="Observed"
            >
              {ids.length ? (
                <div className="signal-tags">
                  {ids.map((x) => (
                    <TextLink
                      key={x}
                      className="mono"
                      onClick={() => open(isSessions ? "session" : "event", x)}
                    >
                      {isSessions ? x : `#${x}`}
                    </TextLink>
                  ))}
                </div>
              ) : (
                <Gap>
                  This recommendation names no{" "}
                  {isSessions ? "sessions" : "requests"}.
                </Gap>
              )}
              <div className="meta-line">
                <Gap>
                  The list API cannot filter by recommendation, so the evidence
                  IDs are listed here instead of a table.
                </Gap>
              </div>
            </Panel>
          </>
        );
      }}
    </ApiGate>
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
  const scope = scopeFromQuery(filters);
  const f = (k: string) => filters.get(k) || "";
  const q = f("q"),
    agent = f("agent"),
    status = f("status"),
    source = f("source"),
    state = f("state"),
    rec = f("rec");

  const eventQuery = clean({
    agent,
    path: f("path") || q,
    status: statusParam(status),
    verdict: f("verdict").toUpperCase(),
    verdict_id: f("verdict_id"),
    confidence: f("confidence").toLowerCase(),
    client_key: f("client_key"),
    session: f("session"),
    source: source.toLowerCase(),
    import_file: f("import_file"),
  });
  const sessionQuery = clean({
    agent,
    confidence: f("confidence").toLowerCase(),
    state: stateParam(state),
    has_retry: f("retry") ? true : undefined,
    has_loop: f("loop") ? true : undefined,
    reached_conversion: f("conversion") ? true : undefined,
    journey: f("journey"),
    reached_step: f("reached"),
    client_key: f("client_key"),
  });

  // Paging belongs to one filter set. A new set starts at the first page.
  const pageKey = `${isSessions}|${scope.site}|${scope.range}|${scope.classes}|${JSON.stringify(
    isSessions ? sessionQuery : eventQuery,
  )}`;
  const [paging, setPaging] = useState({ key: "", offset: 0 });
  const offset = paging.key === pageKey ? paging.offset : 0;
  const onPage = (o: number) => setPaging({ key: pageKey, offset: o });

  const events = useScopedApi<Paged<EventRow>>("events", scope, {
    ...eventQuery,
    limit: isSessions ? 1 : PAGE_SIZE,
    offset: isSessions ? 0 : offset,
  });
  const sessions = useScopedApi<Paged<SessionRow>>("sessions", scope, {
    ...sessionQuery,
    limit: isSessions ? PAGE_SIZE : 1,
    offset: isSessions ? offset : 0,
  });
  const agentList = useScopedApi<AgentRow[]>("agents", scope);
  const agentNames = (agentList.data ?? []).map((a) => a.agent_id);
  if (agent && !agentNames.includes(agent)) agentNames.push(agent);

  // Filters without their own control on this page. Each one gets a chip.
  const hiddenKeys: [string, string][] = isSessions
    ? [
        ["confidence", "Confidence"],
        ["journey", "Journey"],
        ["reached", "Reached step"],
        ["client_key", "Client key"],
      ]
    : [
        ["path", "Path"],
        ["session", "Session"],
        ["confidence", "Confidence"],
        ["verdict", "Verification"],
        ["verdict_id", "Verdict row"],
        ["client_key", "Client key"],
        ["import_file", "Import run"],
      ];
  const hidden = hiddenKeys.filter(([k]) => filters.get(k));
  // Filters the other tab cannot use.
  const ignored = isSessions
    ? [
        ["path", "path"],
        ["session", "session"],
        ["status", "status"],
        ["source", "source"],
        ["verdict", "verification"],
        ["q", "search"],
      ].filter(([k]) => filters.get(k))
    : [
        ["state", "state"],
        ["retry", "retry"],
        ["loop", "loop"],
        ["journey", "journey"],
        ["reached", "reached step"],
        ["conversion", "conversion"],
      ].filter(([k]) => filters.get(k));

  const shared = Object.fromEntries(
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
      "client_key",
      "journey",
      "reached",
    ]
      .map((k) => [k, f(k)])
      .filter(([, v]) => v),
  );
  const active = [
    rec && `the evidence for recommendation ${rec}`,
    scope.classes &&
      `class ${scope.classes
        .split(",")
        .map((id) => classOf(Number(id)).short)
        .join(", ")}`,
    q && `“${q}”`,
    agent,
    !isSessions && status && `status ${status}`,
    !isSessions && source && `source ${source}`,
    isSessions && state && `state ${state}`,
    isSessions && f("retry") && "has retry",
    isSessions && f("loop") && "has loop",
    isSessions && f("conversion") && "reached conversion page",
    ...hidden.map(([k, label]) => `${label.toLowerCase()} ${f(k)}`),
  ].filter(Boolean) as string[];

  const list = isSessions ? sessions : events;
  const listPaged = list.data as Paged<EventRow | SessionRow> | null;
  const total = listPaged?.page.total;
  const noun = isSessions ? "session" : "event";

  return (
    <>
      <div className="page-tabs">
        <Link
          className={!isSessions ? "active" : ""}
          aria-current={!isSessions ? "page" : undefined}
          href={href("/events", shared)}
        >
          Events
          {events.data && <span>{number(events.data.page.total)}</span>}
        </Link>
        <Link
          className={isSessions ? "active" : ""}
          aria-current={isSessions ? "page" : undefined}
          href={href("/sessions", shared)}
        >
          Sessions
          {sessions.data && <span>{number(sessions.data.page.total)}</span>}
        </Link>
      </div>
      <div className="filter-toolbar">
        {!isSessions && (
          <SearchField
            placeholder="Search paths…"
            value={q}
            onChange={(v) => setFilter("q", v)}
          />
        )}
        <Select
          label="Agent"
          value={agent}
          onChange={(v) => setFilter("agent", v)}
          options={[
            { value: "", label: "All agents" },
            ...agentNames.map((a) => ({ value: a, label: a })),
          ]}
        />
        {isSessions ? (
          <>
            <Select
              label="Session state"
              value={stateParam(state)}
              onChange={(v) => setFilter("state", v)}
              options={[
                { value: "", label: "All states" },
                { value: "closed", label: "Closed" },
                { value: "in_progress", label: "In progress" },
              ]}
            />
            {(
              [
                ["retry", "Has retry"],
                ["loop", "Has loop"],
                ["conversion", "Reached conversion page"],
              ] as const
            ).map(([k, label]) => (
              <button
                key={k}
                className={`filter-chip ${f(k) ? "selected" : ""}`}
                onClick={() => setFilter(k, f(k) ? "" : "yes")}
              >
                {label}
              </button>
            ))}
          </>
        ) : (
          <>
            <Select
              label="HTTP status"
              value={statusParam(status)}
              onChange={(v) => setFilter("status", v)}
              options={[
                { value: "", label: "All status codes" },
                { value: "200", label: "200 · OK" },
                { value: "403", label: "403 · Forbidden" },
                { value: "429", label: "429 · Rate limited" },
                { value: "403,429", label: "Denied · 403 / 429" },
                { value: "4xx", label: "4xx · Client errors" },
                { value: "5xx", label: "5xx · Server errors" },
                { value: "4xx,5xx", label: "All errors · 4xx / 5xx" },
                ...(status &&
                ![
                  "200",
                  "403",
                  "429",
                  "denied",
                  "errors",
                  "403,429",
                  "4xx",
                  "5xx",
                  "4xx,5xx",
                ].includes(status)
                  ? [{ value: status, label: status }]
                  : []),
              ]}
            />
            <Select
              label="Source"
              value={source.toLowerCase()}
              onChange={(v) => setFilter("source", v)}
              options={[
                { value: "", label: "All sources" },
                { value: "paired", label: "Paired" },
                { value: "cdn", label: "CDN" },
                { value: "origin", label: "Origin" },
              ]}
            />
          </>
        )}
      </div>
      {hidden.length > 0 && (
        <div className="active-filters">
          {hidden.map(([k, label]) => (
            <button
              key={k}
              aria-label={`Remove filter ${label} ${f(k)}`}
              onClick={() => setFilter(k, "")}
            >
              {label}: {f(k)}
              <X size={11} />
            </button>
          ))}
          <button onClick={reset}>Clear filters</button>
        </div>
      )}
      {ignored.length > 0 && (
        <div className="meta-line">
          <Gap>
            Not applied on this tab: {ignored.map(([, l]) => l).join(", ")}.
          </Gap>
        </div>
      )}
      {rec ? (
        <RecEvidence
          id={rec}
          isSessions={isSessions}
          open={open}
          href={href}
          onRemove={() => setFilter("rec", "")}
        />
      ) : (
        <Panel
          title={isSessions ? "Sessions" : "Request events"}
          label="Observed"
          action={
            total !== undefined && (
              <span className="muted">
                {number(total)} {active.length ? "matching " : ""}
                {noun}
                {total === 1 ? "" : "s"}
              </span>
            )
          }
        >
          {isSessions ? (
            <ApiGate state={sessions} skeleton={<LoadingState rows={8} />}>
              {(d) =>
                d.items.length ? (
                  <>
                    <SessionsTable rows={d.items} open={open} href={href} />
                    <PagerFooter
                      page={d.page}
                      shown={d.items.length}
                      noun={noun}
                      onPage={onPage}
                    />
                  </>
                ) : (
                  <Empty reset={reset} active={active} />
                )
              }
            </ApiGate>
          ) : (
            <ApiGate state={events} skeleton={<LoadingState rows={8} />}>
              {(d) =>
                d.items.length ? (
                  <>
                    <EventsTable rows={d.items} open={open} />
                    <PagerFooter
                      page={d.page}
                      shown={d.items.length}
                      noun={noun}
                      onPage={onPage}
                    />
                  </>
                ) : (
                  <Empty reset={reset} active={active} />
                )
              }
            </ApiGate>
          )}
        </Panel>
      )}
      <div className="meta-line">
        <Label type="Inferred" />
        <span>Sessions group requests by client and time gap.</span>
        <Label type="Unknown" />
        <span>Logs cannot show task completion.</span>
      </div>
    </>
  );
}
