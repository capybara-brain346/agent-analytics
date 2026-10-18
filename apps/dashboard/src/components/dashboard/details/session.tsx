"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import type { SessionDetail as SessionData } from "@/lib/api/types";
import { capitalize, dateTimeUTC, number } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Confidence,
  Gap,
  Label,
  LoadingState,
  Status,
} from "../shared";
import { DetailSection, Fields, DetailProps } from "./common";

const flagNames: Record<string, string> = {
  retry: "Retry",
  loop: "Loop",
  key_page: "Key page",
  conversion_page: "Conversion page",
};

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
        return (
          <>
            <div className="detail-chips">
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
              <Status value={s.in_progress ? "In progress" : "Closed"} />
            </div>
            <DetailSection
              title="Session summary"
              label={capitalize(d.facts_label)}
            >
              <div className="detail-metrics">
                <Link href={href("/events", { session: s.session_id })}>
                  <strong>{number(f.requests)}</strong>requests
                </Link>
                <div>
                  <strong>{number(f.distinct_pages)}</strong>distinct pages
                </div>
                <div>
                  <strong>{f.key_pages_visited}</strong>key pages visited
                </div>
              </div>
              <Fields
                items={[
                  ["Started", `${dateTimeUTC(s.started)} UTC`],
                  ["Last seen", `${dateTimeUTC(s.last_seen)} UTC`],
                  ["State", f.state],
                  [
                    "Confidence",
                    s.confidence ? (
                      <Confidence key="c" value={capitalize(s.confidence)} />
                    ) : (
                      <Gap>Not recorded</Gap>
                    ),
                  ],
                  [
                    "Confidence reason",
                    d.confidence_reason.text ?? <Gap>Not recorded</Gap>,
                  ],
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
                    "Journey steps reached",
                    journeys.length
                      ? journeys.map(([j, n]) => `${j}: step ${n}`).join(" · ")
                      : "No journey step",
                  ],
                  [
                    "Conversion page",
                    f.reached_conversion ? "Reached" : "Not reached",
                  ],
                ]}
              />
            </DetailSection>
            <div className="detail-notice">
              <Label type={capitalize(d.grouping.label)} />
              <p>{d.grouping.text}</p>
            </div>
            <DetailSection title="Request sequence" label="Observed">
              <div className="request-sequence">
                {d.steps.map((e) => (
                  <button
                    key={e.event_id}
                    onClick={() => open("event", String(e.event_id))}
                  >
                    <span className="sequence-number">{e.seq}</span>
                    <span className="sequence-main">
                      <code>{e.path}</code>
                      <small>
                        {dateTimeUTC(e.ts)} ·{" "}
                        {e.delta_seconds === null
                          ? "First request"
                          : `+${Math.round(e.delta_seconds)} s`}
                        {e.flags.length
                          ? ` · ${e.flags.map((x) => flagNames[x] ?? x).join(", ")}`
                          : ""}
                      </small>
                    </span>
                    {e.status !== null && (
                      <span
                        className={`http-code ${e.status >= 400 ? "error" : "ok"}`}
                      >
                        {e.status}
                      </span>
                    )}
                    <ChevronRight size={12} />
                  </button>
                ))}
              </div>
            </DetailSection>
            <div className="outcome-panel">
              <Label type="Unknown" />
              <h3>Task outcome is unknown</h3>
              <p>
                {d.outcome.text ??
                  "Request logs show pages reached and response codes. They cannot show whether the task was completed."}
              </p>
            </div>
            <DetailSection title="Evidence gaps" label="Unknown">
              {d.gaps.length ? (
                <ul className="plain-list">
                  {d.gaps.map((g) => (
                    <li key={g.text}>
                      {g.text} <Label type={capitalize(g.label)} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">The API lists no gaps for this session.</p>
              )}
            </DetailSection>
            <DetailSection title="Recommendations">
              {d.recommendations.length ? (
                <ul className="plain-list">
                  {d.recommendations.map((r) => (
                    <li key={r.id}>
                      <button
                        className="text-link"
                        onClick={() => open("recommendation", String(r.id))}
                      >
                        {r.target} · {r.pattern} · score {r.score}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">
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
