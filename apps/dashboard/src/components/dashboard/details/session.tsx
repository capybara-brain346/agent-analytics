"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import type { SessionDetail as SessionData } from "@/lib/api/types";
import { capitalize, dateTimeUTC, number } from "@/lib/format";
import { ApiGate, ClassName, Confidence, Label, LoadingState } from "../shared";
import { HttpPill, Pill } from "../sections/activity/cells";
import { DetailSection, DetailProps } from "./common";
import { Dash, Facts, Note } from "./facts";

const flagNames: Record<string, string> = {
  retry: "Retry",
  loop: "Loop",
  key_page: "Key page",
  conversion_page: "Conversion page",
};

// The outcome block already states this gap.
const outcomeGap = /outcome|task completion|completed/i;

// The API text always says "These N requests". Singular needs its own wording.
const groupingText = (text: string, requests: number) =>
  requests === 1
    ? text.replace(/^These 1 requests likely form/, "This request likely forms")
    : text;

export function SessionDetail({ id, href, open }: DetailProps) {
  const site = useSearchParams().get("site") || undefined;
  const state = useApi<SessionData>(`sessions/${encodeURIComponent(id)}`, {
    site,
  });

  return (
    <ApiGate state={state} skeleton={<LoadingState rows={8} />}>
      {(d) => {
        const s = d.session,
          f = d.facts;
        const journeys = Object.entries(f.journeys_reached);
        const gaps = d.gaps.filter((g) => !outcomeGap.test(g.text));

        return (
          <>
            <div className="detail-links">
              {s.agent ? (
                <button
                  className="text-link"
                  onClick={() => open("agent", s.agent!)}
                >
                  {s.agent}
                  <ArrowUpRight size={12} />
                </button>
              ) : (
                <span className="muted">No agent name</span>
              )}
              {s.traffic_class && <ClassName id={s.traffic_class} />}
              <Pill tone={s.in_progress ? "green" : "neutral"}>
                {s.in_progress ? "In progress" : "Closed"}
              </Pill>
            </div>

            <DetailSection
              title="Session summary"
              label={capitalize(d.facts_label)}
            >
              <div className="session-metrics">
                <Link href={href("/events", { session: s.session_id })}>
                  <strong>{number(f.requests)}</strong>Requests
                </Link>
                <div>
                  <strong>{number(f.distinct_pages)}</strong>Distinct pages
                </div>
                <div>
                  <strong>{f.key_pages_visited}</strong>Key pages visited
                </div>
              </div>

              <Facts
                items={[
                  ["Started", `${dateTimeUTC(s.started)} UTC`],
                  ["Last seen", `${dateTimeUTC(s.last_seen)} UTC`],
                  ["State", capitalize(f.state)],
                  [
                    "Confidence",
                    s.confidence ? (
                      <Confidence key="c" value={capitalize(s.confidence)} />
                    ) : (
                      <Dash />
                    ),
                  ],
                  ["Confidence reason", d.confidence_reason.text ?? <Dash />],
                  [
                    "Status counts",
                    Object.entries(f.status_counts)
                      .map(([k, n]) => `${k}: ${number(n)}`)
                      .join(" · ") || "None",
                  ],
                  [
                    "Signals",
                    `${f.has_retry ? `Retry detected (${f.retries})` : "No retry"} · ${f.has_loop ? "Loop detected" : "No loop"}`,
                  ],
                  [
                    "Conversion page",
                    f.reached_conversion ? "Reached" : "Not reached",
                  ],
                  [
                    "Journey steps reached",
                    journeys.length
                      ? journeys.map(([j, n]) => `${j}: step ${n}`).join(" · ")
                      : "No journey step",
                  ],
                ]}
              />
            </DetailSection>

            <Note label={<Label type={capitalize(d.grouping.label)} />}>
              {groupingText(d.grouping.text ?? "", f.requests)}
            </Note>

            <DetailSection title="Request sequence" label="Observed">
              <div className="detail-rows">
                {d.steps.map((e) => (
                  <button
                    key={e.event_id}
                    className="detail-row"
                    onClick={() => open("event", String(e.event_id))}
                  >
                    <span className="seq-num">{e.seq}</span>
                    <span className="detail-row-main">
                      <code>{e.path}</code>
                      <span>
                        {dateTimeUTC(e.ts)} ·{" "}
                        {e.delta_seconds === null
                          ? "first request"
                          : `+${Math.round(e.delta_seconds)} s`}
                        {e.flags.length
                          ? ` · ${e.flags.map((x) => (flagNames[x] ?? x).toLowerCase()).join(", ")}`
                          : ""}
                      </span>
                    </span>
                    <HttpPill code={e.status} />
                    <ChevronRight size={14} className="row-chev" />
                  </button>
                ))}
              </div>
            </DetailSection>

            <div className="outcome-note">
              <Label type="Unknown" />
              <strong>Task outcome unknown</strong>
              <p>
                Request logs show pages reached and response codes. They cannot
                show whether the task was completed.
              </p>
              {gaps.length > 0 && (
                <ul className="gap-list">
                  {gaps.map((g) => (
                    <li key={g.text}>
                      <Label type={capitalize(g.label)} />
                      {g.text}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <DetailSection title="Recommendations">
              {d.recommendations.length ? (
                <div className="detail-rows">
                  {d.recommendations.map((r) => (
                    <button
                      key={r.id}
                      className="detail-row"
                      onClick={() => open("recommendation", String(r.id))}
                    >
                      <span className="detail-row-main">
                        <span className="sans">{r.target}</span>
                        <span>
                          {r.pattern} · score {r.score}
                        </span>
                      </span>
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              ) : (
                <p className="detail-empty">
                  No recommendation uses this session as evidence.
                </p>
              )}
            </DetailSection>
          </>
        );
      }}
    </ApiGate>
  );
}
