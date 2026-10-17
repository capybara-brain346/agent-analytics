"use client";

import { useSearchParams } from "next/navigation";
import { ArrowLeft, ArrowRight, ArrowUpRight, Info } from "lucide-react";
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
  Gap,
  LoadingState,
  Status,
  TextLink,
} from "../shared";
import { DetailSection, Fields, DetailProps } from "./common";

const text = (v: string | number | null | undefined, unit = "") =>
  v === null || v === undefined || v === "" ? (
    <Gap>Not recorded</Gap>
  ) : (
    `${v}${unit}`
  );

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
    {
      site,
    },
  );
  const steps = state.data?.steps ?? [];
  const at = steps.findIndex((s) => s.event_id === eventId);
  const prev = at > 0 ? steps[at - 1] : undefined;
  const next = at >= 0 ? steps[at + 1] : undefined;
  return (
    <>
      <button
        className="detail-related-link"
        onClick={() => open("session", sessionId)}
      >
        <span>
          <code>{sessionId}</code>
          <small>
            Request {position} of {of}
          </small>
        </span>
        <ArrowRight size={16} />
      </button>
      <div className="sibling-nav">
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
            <div className="request-heading">
              <span className="method">{r.method ?? "—"}</span>
              <code>{r.path}</code>
              {r.status !== null && (
                <span
                  className={`http-code ${r.status >= 400 ? "error" : "ok"}`}
                >
                  {r.status}
                </span>
              )}
            </div>
            <DetailSection title="Request" label={capitalize(e.request_label)}>
              <Fields
                items={[
                  ["Time", `${dateTimeUTC(r.ts)} UTC`],
                  ["Host", text(r.host)],
                  ["Response", text(r.status)],
                  ["Response time", text(r.response_time_ms, " ms")],
                  ["Bytes", text(r.bytes_sent)],
                  ["Referrer", text(r.referrer)],
                  ["User agent", text(r.user_agent)],
                  ["Client IP", text(r.client_ip)],
                  ["Client key", text(r.client_key)],
                ]}
              />
            </DetailSection>
            <DetailSection title="Source" label="Observed">
              <Fields
                items={[
                  ["Record type", `${capitalize(s.source)} · ${s.pair_state}`],
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
                      <Gap>Not recorded</Gap>
                    ),
                  ],
                  [
                    "File / line",
                    s.line_no !== null
                      ? `${e.import_file?.object_key ?? s.file_id ?? "file"} · line ${s.line_no}`
                      : text(null),
                  ],
                  ["Request ID", text(s.request_id ?? s.edge_request_id)],
                  [
                    "CDN bypass",
                    s.cdn_bypass === null
                      ? text(null)
                      : s.cdn_bypass
                        ? "Yes"
                        : "No",
                  ],
                ]}
              />
            </DetailSection>
            <DetailSection title="Identity & classification" label="Inferred">
              {v ? (
                <Fields
                  items={[
                    [
                      "Identity",
                      v.verdict === "VERIFIED"
                        ? (v.claimed_agent ?? "Verified")
                        : v.claimed_agent
                          ? `Claims to be ${v.claimed_agent}, unverified`
                          : "No agent name in the request",
                    ],
                    ["Verdict", <Status key="verdict" value={v.verdict} />],
                    ["Method", v.method],
                    ["Evidence", text(v.evidence)],
                    [
                      "Registry / IP list",
                      `${v.registry_version ?? "unknown"} / ${v.ip_snapshot_version ?? "none"} · checked ${dateTimeUTC(v.checked_at)}`,
                    ],
                    [
                      "Class",
                      c ? (
                        <ClassName key="class" id={c.traffic_class} full />
                      ) : (
                        <Gap>Not classified</Gap>
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
                        text(null)
                      ),
                    ],
                    ...(c
                      ? ([
                          [
                            "Rule",
                            `${c.rule_id ?? "unknown"} v${c.rule_version ?? "?"}`,
                          ],
                          [
                            "Inputs",
                            `verdict ${c.inputs.verdict ?? "none"} · category ${c.inputs.registry_category ?? "none"} · UA type ${c.inputs.ua_type ?? "none"} · edge signal ${c.inputs.edge_signal ?? "none"}`,
                          ],
                          ["Class evidence", text(c.evidence)],
                        ] as [string, React.ReactNode][])
                      : []),
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
                <Gap>No verdict for this request yet.</Gap>
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
                <Gap>This request is not part of a session.</Gap>
              )}
            </DetailSection>
            <DetailSection title="Recommendations">
              {e.recommendations.length ? (
                <ul className="plain-list">
                  {e.recommendations.map((rec) => (
                    <li key={rec.id}>
                      <TextLink
                        onClick={() => open("recommendation", String(rec.id))}
                      >
                        {rec.target} · {rec.pattern} · score {rec.score}
                      </TextLink>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="muted">
                  No recommendation uses this request as evidence.
                </p>
              )}
            </DetailSection>
            <div className="detail-notice">
              <Info size={14} />
              <p>
                {r.status !== null && r.status < 400
                  ? "The status code is observed. It does not prove that the task was completed."
                  : "This status is observed. Its effect on the agent’s task is unknown."}
              </p>
            </div>
          </>
        );
      }}
    </ApiGate>
  );
}
