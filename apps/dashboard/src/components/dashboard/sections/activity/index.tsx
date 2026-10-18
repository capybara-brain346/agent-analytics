"use client";

import { useState } from "react";
import Link from "next/link";
import { X } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { AgentRow, EventRow, Paged, SessionRow } from "@/lib/api/types";
import { classOf } from "@/lib/classes";
import { number } from "@/lib/format";
import { ApiGate, Empty, Gap, LoadingState } from "../../shared";
import type { Props } from "../common";
import {
  PAGE_SIZE,
  clean,
  sourceLabel,
  stateParam,
  statusParam,
} from "./config";
import { EventsTable } from "./events-table";
import { PagerFooter } from "./pager";
import { RecEvidence } from "./rec-evidence";
import { SessionsTable } from "./sessions-table";
import { ActivityToolbar } from "./toolbar";

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
    !isSessions && source && `source ${sourceLabel(source)}`,
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
      <div className="page-tabs" role="navigation" aria-label="Views">
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
      <ActivityToolbar
        isSessions={isSessions}
        filters={filters}
        setFilter={setFilter}
        agentNames={agentNames}
        total={total}
        noun={noun}
        matching={active.length > 0}
      />
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
        <section className="panel">
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
        </section>
      )}
    </>
  );
}
