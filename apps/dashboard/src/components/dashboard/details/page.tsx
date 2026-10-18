"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowRight, ChevronRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { PageDetail as PageDetailData } from "@/lib/api/types";
import { dateUTC, formatBytes, number, percent, timeUTC } from "@/lib/format";
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
import { DetailSection, DetailProps } from "./common";

const Unknown = () => (
  <span className="unknown-dash" title="Unknown: no requests in this window">
    —
  </span>
);

/** "Oct 16, 14:00"; falls back to the raw value when it is not a time. */
function hourLabel(hour: string) {
  return Number.isNaN(new Date(hour).getTime())
    ? hour
    : `${dateUTC(hour)}, ${timeUTC(hour)}`;
}

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
              <span className="qualifier">
                <i className={d.in_sitemap ? "ok" : ""} />
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
              <div className="dp-facts dp-facts-3">
                <Link className="dp-fact" href={events()}>
                  <span>Agent requests</span>
                  <strong>{number(p.agent_requests)}</strong>
                </Link>
                <div className="dp-fact">
                  <span>All requests</span>
                  <strong>{number(p.requests)}</strong>
                </div>
                <div className="dp-fact">
                  <span>Sessions</span>
                  <strong>{number(p.sessions)}</strong>
                </div>
              </div>
            </DetailSection>
            <DetailSection title="Response by traffic class" label="Observed">
              {d.by_class.length ? (
                <div className="dp-table">
                  <table aria-label="Response by traffic class">
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
              <div className="dp-facts">
                <div className="dp-fact">
                  <span>Error rate</span>
                  <strong>
                    {p.error_rate_pct === null ? (
                      <Unknown />
                    ) : (
                      <NumberLink
                        value={percent(p.error_rate_pct)}
                        href={events({ status: "4xx,5xx" })}
                      />
                    )}
                  </strong>
                </div>
                <div className="dp-fact">
                  <span>Block rate (403 / 429)</span>
                  <strong>
                    {p.block_rate_pct === null ? (
                      <Unknown />
                    ) : (
                      <NumberLink
                        value={percent(p.block_rate_pct)}
                        href={events({ status: "403,429" })}
                      />
                    )}
                  </strong>
                </div>
                <div className="dp-fact">
                  <span>Retries</span>
                  <strong>{number(p.retries)}</strong>
                </div>
                <div className="dp-fact">
                  <span>Median response size</span>
                  <strong>{formatBytes(p.median_bytes) ?? <Unknown />}</strong>
                </div>
                <div className="dp-fact">
                  <span>Agents</span>
                  <strong>{number(p.distinct_agents)}</strong>
                </div>
              </div>
            </DetailSection>
            <DetailSection title="Over time" label="Observed">
              {d.over_time.length ? (
                <>
                  <div
                    className="dp-bars"
                    role="img"
                    aria-label={`Requests per hour, peak ${peak}`}
                  >
                    {d.over_time.map((h) => (
                      <span
                        key={h.hour}
                        title={`${h.hour}: ${h.requests} requests, ${h.errors} errors`}
                        style={{
                          height: `${Math.max(4, (h.requests / peak) * 100)}%`,
                        }}
                      >
                        <i
                          style={{
                            height: `${h.requests ? (h.errors / h.requests) * 100 : 0}%`,
                          }}
                        />
                      </span>
                    ))}
                  </div>
                  <div className="dp-bars-axis">
                    <span>{hourLabel(d.over_time[0].hour)}</span>
                    <span className="dp-bars-key">
                      <i /> Requests <i className="has-errors" /> Errors
                    </span>
                    <span>
                      {hourLabel(d.over_time[d.over_time.length - 1].hour)}
                    </span>
                  </div>
                </>
              ) : (
                <Gap>No hourly data in this window.</Gap>
              )}
            </DetailSection>
            <DetailSection title="Agents" label="Observed">
              {d.agents.length ? (
                <div className="dp-table">
                  <table aria-label="Agents">
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
                          <td>{a.claimed_agent ?? <Unknown />}</td>
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
              <div className="dp-list">
                {d.sessions.map((s) => (
                  <button
                    key={s.session_id}
                    onClick={() => open("session", s.session_id)}
                  >
                    <span>
                      {s.agent ?? s.class_name ?? "Unknown client"} ·{" "}
                      {number(s.requests)}{" "}
                      {s.requests === 1 ? "request" : "requests"}
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
              <div className="dp-list">
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
            <div className="dp-foot">
              <Link className="btn-standard" href={events()}>
                Inspect requests for this page
                <ArrowRight size={14} />
              </Link>
              <p>
                <Label type="Unknown" />
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
