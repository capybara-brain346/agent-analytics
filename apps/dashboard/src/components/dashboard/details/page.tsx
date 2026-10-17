"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, Check, ChevronRight, X } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { PageDetail as PageDetailData } from "@/lib/api/types";
import { formatBytes, number, percent } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Confidence,
  Gap,
  Label,
  LoadingState,
  NumberLink,
  Status,
} from "../shared";
import { DetailSection, Fields, DetailProps } from "./common";

export function PageDetail({ id, href, open }: DetailProps) {
  const state = useScopedApi<PageDetailData>(
    "pages",
    scopeFromQuery(useSearchParams()),
    { path: id },
  );
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
      {(d) => {
        const p = d.page;
        const events = (extra: Record<string, string> = {}) =>
          href("/events", { path: p.path, ...extra });
        const peak = Math.max(1, ...d.over_time.map((h) => h.requests));
        return (
          <>
            <div className="detail-chips">
              {p.tags.map((t) => (
                <span key={t} className="page-tag">
                  {t}
                </span>
              ))}
              <span className="muted">
                {d.in_sitemap ? <Check size={12} /> : <X size={12} />}
                {d.in_sitemap ? "In sitemap" : "Not in sitemap"}
              </span>
              <Status
                value={
                  d.access_policy === "allowed"
                    ? "Allowed by policy"
                    : "Blocked by intent"
                }
              />
            </div>
            <DetailSection title="Page traffic" label="Observed">
              <div className="detail-metrics">
                <Link href={events()}>
                  <strong>{number(p.agent_requests)}</strong>agent requests
                </Link>
                <span className="count-static">
                  <strong>{number(p.requests)}</strong>all requests
                </span>
                <span className="count-static">
                  <strong>{number(p.sessions)}</strong>sessions
                </span>
              </div>
            </DetailSection>
            <DetailSection title="Response by traffic class" label="Observed">
              {d.by_class.length ? (
                <div className="detail-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Class</th>
                        <th>Requests</th>
                        <th>2xx</th>
                        <th>3xx</th>
                        <th>403</th>
                        <th>429</th>
                        <th>Other 4xx</th>
                        <th>5xx</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.by_class.map((c) => {
                        const cls = c.traffic_class;
                        const link = (n: number, status: string) => (
                          <NumberLink
                            value={n}
                            href={events({
                              status,
                              ...(cls ? { class: String(cls) } : {}),
                            })}
                          />
                        );
                        return (
                          <tr key={cls ?? "none"}>
                            <td>
                              {cls ? <ClassName id={cls} /> : "Unclassified"}
                            </td>
                            <td>
                              <NumberLink
                                value={c.requests}
                                href={events(cls ? { class: String(cls) } : {})}
                              />
                            </td>
                            <td>{number(c.n_2xx)}</td>
                            <td>{number(c.n_3xx)}</td>
                            <td>{link(c.n_403, "403")}</td>
                            <td>{link(c.n_429, "429")}</td>
                            <td>{link(c.n_4xx, "4xx")}</td>
                            <td>{link(c.n_5xx, "5xx")}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              ) : (
                <Gap>No requests for this page in this window.</Gap>
              )}
            </DetailSection>
            <DetailSection title="Page signals" label="Observed">
              <Fields
                items={[
                  [
                    "Errors",
                    p.error_rate_pct === null ? (
                      <Gap>Unknown</Gap>
                    ) : (
                      <NumberLink
                        value={percent(p.error_rate_pct)}
                        href={events({ status: "4xx,5xx" })}
                      />
                    ),
                  ],
                  [
                    "Blocked requests (403 / 429)",
                    p.block_rate_pct === null ? (
                      <Gap>Unknown</Gap>
                    ) : (
                      <NumberLink
                        value={percent(p.block_rate_pct)}
                        href={events({ status: "403,429" })}
                      />
                    ),
                  ],
                  ["Retries", number(p.retries)],
                  [
                    "Median response size",
                    formatBytes(p.median_bytes) ?? <Gap>Unknown</Gap>,
                  ],
                  ["Agents", number(p.distinct_agents)],
                ]}
              />
            </DetailSection>
            <DetailSection title="Over time" label="Observed">
              {d.over_time.length ? (
                <div
                  role="img"
                  aria-label={`Requests per hour, peak ${peak}`}
                  style={{
                    display: "flex",
                    alignItems: "flex-end",
                    gap: 1,
                    height: 56,
                  }}
                >
                  {d.over_time.map((h) => (
                    <span
                      key={h.hour}
                      title={`${h.hour}: ${h.requests} requests, ${h.errors} errors`}
                      style={{
                        flex: 1,
                        height: `${Math.max(4, (h.requests / peak) * 100)}%`,
                        background: h.errors
                          ? "var(--negative, #d66)"
                          : "var(--muted, #888)",
                      }}
                    />
                  ))}
                </div>
              ) : (
                <Gap>No hourly data in this window.</Gap>
              )}
            </DetailSection>
            <DetailSection title="Agents" label="Observed">
              {d.agents.length ? (
                <div className="detail-table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Claimed agent</th>
                        <th>Class</th>
                        <th>Sessions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.agents.map((a, i) => (
                        <tr key={i}>
                          <td>
                            {a.claimed_agent ?? (
                              <span className="muted">Unknown</span>
                            )}
                          </td>
                          <td>
                            {a.traffic_class ? (
                              <ClassName id={a.traffic_class} />
                            ) : (
                              "Unclassified"
                            )}
                          </td>
                          <td>{number(a.sessions)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="muted">No agent fetched this page.</p>
              )}
            </DetailSection>
            <DetailSection title="Sessions on this page">
              <div className="detail-link-list">
                {d.sessions.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => open("session", s.session_id)}
                  >
                    <span>
                      {s.agent ?? s.class_name ?? "Unknown client"} ·{" "}
                      {number(s.requests)} requests
                    </span>
                    <ChevronRight size={13} />
                  </button>
                ))}
                {!d.sessions.length && (
                  <p className="muted">No session includes this page.</p>
                )}
              </div>
            </DetailSection>
            <DetailSection title="Related recommendations">
              <div className="detail-link-list">
                {d.recommendations.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => open("recommendation", String(r.id))}
                  >
                    <span>
                      {r.pattern} · {r.target}
                    </span>
                    {r.confidence && (
                      <Confidence
                        value={
                          r.confidence.charAt(0).toUpperCase() +
                          r.confidence.slice(1)
                        }
                      />
                    )}
                    <ChevronRight size={13} />
                  </button>
                ))}
                {!d.recommendations.length && (
                  <p className="muted">No open recommendation for this page.</p>
                )}
              </div>
            </DetailSection>
            <Link className="detail-related-link" href={events()}>
              Inspect requests for this page
              <ArrowRight size={16} />
            </Link>
            <div className="outcome-panel">
              <Label type="Unknown" />
              <p>
                Page content and task completion cannot be measured from request
                logs.
              </p>
            </div>
          </>
        );
      }}
    </ApiGate>
  );
}
