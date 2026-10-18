"use client";

import { useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  ChevronRight,
  Info,
} from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import type {
  EventDetail as EventData,
  SessionDetail as SessionData,
} from "@/lib/api/types";
import { capitalize, dateTimeUTC } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Confidence,
  LoadingState,
  TextLink,
} from "../shared";
import { HttpPill, VerdictPill } from "../sections/activity/cells";
import { DetailSection, DetailProps } from "./common";
import { sourceLabel } from "../sections/activity/config";
import { Dash, Facts, Note } from "./facts";

const text = (v: string | number | null | undefined, unit = "") =>
  v === null || v === undefined || v === "" ? <Dash /> : `${v}${unit}`;

function SessionNav({
  sessionId,
  eventId,
  position,
  of,
  open,
}: {
  sessionId: string;
  eventId: number;
  position: number;
  of: number;
  open: DetailProps["open"];
}) {
  const site = useSearchParams().get("site") || undefined;
  const state = useApi<SessionData>(
    `sessions/${encodeURIComponent(sessionId)}`,
    { site },
  );
  const steps = state.data?.steps ?? [];
  const at = steps.findIndex((s) => s.event_id === eventId);
  const prev = at > 0 ? steps[at - 1] : undefined;
  const next = at >= 0 ? steps[at + 1] : undefined;

  return (
    <>
      <div className="detail-rows">
        <button
          className="detail-row"
          onClick={() => open("session", sessionId)}
        >
          <span className="detail-row-main">
            <strong>{sessionId}</strong>
            <span className="sans">
              Request {position} of {of}
            </span>
          </span>
          <ChevronRight size={14} />
        </button>
      </div>

      <div className="sibling-buttons">
        <button
          disabled={!prev}
          onClick={() => prev && open("event", String(prev.event_id))}
        >
          <ArrowLeft size={13} />
          Previous request
        </button>
        <button
          disabled={!next}
          onClick={() => next && open("event", String(next.event_id))}
        >
          Next request
          <ArrowRight size={13} />
        </button>
      </div>
    </>
  );
}

export function EventDetail({ id, open }: DetailProps) {
  const site = useSearchParams().get("site") || undefined;
  const state = useApi<EventData>(`events/${encodeURIComponent(id)}`, { site });

  return (
    <ApiGate state={state} skeleton={<LoadingState rows={8} />}>
      {(e) => {
        const r = e.request,
          s = e.source,
          v = e.verdict,
          c = e.classification;

        return (
          <>
            <div className="event-head">
              <span className="method">{r.method ?? "—"}</span>
              <code>{r.path}</code>
              <HttpPill code={r.status} />
            </div>
            <p className="event-sub">{dateTimeUTC(r.ts)} UTC</p>

            <DetailSection title="Request" label={capitalize(e.request_label)}>
              <Facts
                items={[
                  ["Host", text(r.host)],
                  ["Response time", text(r.response_time_ms, " ms")],
                  ["Bytes sent", text(r.bytes_sent)],
                  ["Referrer", text(r.referrer)],
                  ["Client IP", text(r.client_ip)],
                  ["Client key", text(r.client_key)],
                  ["User agent", text(r.user_agent)],
                ]}
              />
            </DetailSection>

            <DetailSection title="Source" label="Observed">
              <Facts
                items={[
                  ["Record type", `${sourceLabel(s.source)} · ${s.pair_state}`],
                  [
                    "CDN / origin status",
                    `${s.edge_status ?? "not seen"} / ${s.origin_status ?? "not seen"}`,
                  ],
                  [
                    "Import run",
                    e.import_file ? (
                      <TextLink
                        key="import"
                        onClick={() => open("import", e.import_file!.id)}
                      >
                        {e.import_file.id}
                      </TextLink>
                    ) : (
                      <Dash />
                    ),
                  ],
                  [
                    "CDN bypass",
                    s.cdn_bypass === null ? (
                      <Dash />
                    ) : s.cdn_bypass ? (
                      "Yes"
                    ) : (
                      "No"
                    ),
                  ],
                  ["Request ID", text(s.request_id ?? s.edge_request_id)],
                  [
                    "File / line",
                    s.line_no !== null ? (
                      `${e.import_file?.object_key ?? s.file_id ?? "file"} · line ${s.line_no}`
                    ) : (
                      <Dash />
                    ),
                  ],
                ]}
              />
            </DetailSection>

            <DetailSection title="Identity and classification" label="Inferred">
              {v ? (
                <Facts
                  items={[
                    [
                      "Identity",
                      v.verdict === "VERIFIED"
                        ? (v.claimed_agent ?? "Verified")
                        : v.claimed_agent
                          ? `Claims to be ${v.claimed_agent}, unverified`
                          : "No agent name in the request",
                    ],
                    [
                      "Verdict",
                      <VerdictPill key="verdict" verdict={v.verdict} />,
                    ],
                    ["Method", v.method],
                    [
                      "Class",
                      c ? (
                        <ClassName key="class" id={c.traffic_class} full />
                      ) : (
                        <Dash why="Not classified" />
                      ),
                    ],
                    [
                      "Confidence",
                      c?.confidence ? (
                        <Confidence
                          key="confidence"
                          value={capitalize(c.confidence)}
                        />
                      ) : (
                        <Dash />
                      ),
                    ],
                    ...(c
                      ? ([
                          [
                            "Rule",
                            `${c.rule_id ?? "unknown"} v${c.rule_version ?? "?"}`,
                          ],
                        ] as [string, React.ReactNode][])
                      : []),
                    ["Evidence", text(v.evidence)],
                    ...(c
                      ? ([
                          ["Class evidence", text(c.evidence)],
                          [
                            "Inputs",
                            `verdict ${c.inputs.verdict ?? "none"} · category ${c.inputs.registry_category ?? "none"} · UA type ${c.inputs.ua_type ?? "none"} · edge signal ${c.inputs.edge_signal ?? "none"}`,
                          ],
                        ] as [string, React.ReactNode][])
                      : []),
                    [
                      "Registry / IP list",
                      `${v.registry_version ?? "unknown"} / ${v.ip_snapshot_version ?? "none"} · checked ${dateTimeUTC(v.checked_at)}`,
                    ],
                    [
                      "Verdict row",
                      v.claimed_agent ? (
                        <TextLink
                          key="verdictrow"
                          onClick={() => open("agent", v.claimed_agent!)}
                        >
                          #{v.id} · view agent history
                          <ArrowUpRight size={12} />
                        </TextLink>
                      ) : (
                        `#${v.id}`
                      ),
                    ],
                  ]}
                />
              ) : (
                <p className="detail-empty">No verdict for this request yet.</p>
              )}
            </DetailSection>

            <DetailSection title="Session">
              {e.session ? (
                <SessionNav
                  sessionId={e.session.session_id}
                  eventId={e.id}
                  position={e.session.position}
                  of={e.session.of}
                  open={open}
                />
              ) : (
                <p className="detail-empty">
                  This request is not part of a session.
                </p>
              )}
            </DetailSection>

            <DetailSection title="Recommendations">
              {e.recommendations.length ? (
                <div className="detail-rows">
                  {e.recommendations.map((rec) => (
                    <button
                      key={rec.id}
                      className="detail-row"
                      onClick={() => open("recommendation", String(rec.id))}
                    >
                      <span className="detail-row-main">
                        <span className="sans">{rec.target}</span>
                        <span>
                          {rec.pattern} · score {rec.score}
                        </span>
                      </span>
                      <ChevronRight size={14} />
                    </button>
                  ))}
                </div>
              ) : (
                <p className="detail-empty">
                  No recommendation uses this request as evidence.
                </p>
              )}
            </DetailSection>

            <Note label={<Info size={14} />}>
              {r.status !== null && r.status < 400
                ? "The status code is observed. It does not prove that the task was completed."
                : "This status is observed. Its effect on the agent’s task is unknown."}
            </Note>
          </>
        );
      }}
    </ApiGate>
  );
}
