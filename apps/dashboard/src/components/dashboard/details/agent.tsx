"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronRight, Info } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import type { AgentDetail as AgentDetailData } from "@/lib/api/types";
import { useScopedApi } from "@/lib/api/use-api";
import { capitalize, dateTimeUTC, number } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Confidence,
  Gap,
  LoadingState,
  Status,
} from "../shared";
import { agentSubtitle, agentTitle } from "../sections/agents";
import { DetailSection, Fields, DetailProps } from "./common";

const time = (iso: string | null) =>
  iso ? dateTimeUTC(iso) : <Gap>Unknown</Gap>;
const or = (v: string | null | undefined) => v ?? <Gap>Unknown</Gap>;

export function AgentDetail({ id, href, open }: DetailProps) {
  // The detail sheet shares the page filters. Its URL holds no other state.
  const query =
    typeof window === "undefined"
      ? new URLSearchParams()
      : new URLSearchParams(window.location.search);
  const scope = scopeFromQuery(query);
  // The API ignores the class filter here, so it is left out of the key.
  const state = useScopedApi<AgentDetailData>(
    `agents/${encodeURIComponent(id)}`,
    { ...scope, classes: "" },
  );
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
      {(d) => <Body d={d} href={href} open={open} />}
    </ApiGate>
  );
}

function Body({
  d,
  href,
  open,
}: {
  d: AgentDetailData;
  href: DetailProps["href"];
  open: DetailProps["open"];
}) {
  const a = d.agent;
  const why = d.why_this_class;
  const named = !a.name.startsWith("unknown:");
  const peak = Math.max(1, ...d.activity.map((p) => p.requests));
  const totalStatus = d.status_mix.reduce((n, s) => n + s.requests, 0);
  return (
    <>
      <div className="detail-chips">
        {a.verification && <Status value={a.verification} />}
        <ClassName id={a.traffic_class} full />
        {a.confidence && <Confidence value={capitalize(a.confidence)} />}
      </div>
      <div className="detail-notice">
        <Info size={14} />
        {named
          ? a.verification_note
          : "The exact client identity is unknown. The name is a label, not proof."}
      </div>
      <DetailSection title="Activity" label="Observed">
        <div className="detail-metrics">
          <Link href={href("/events", { agent: a.agent_id })}>
            <strong>{number(a.requests)}</strong>requests
          </Link>
          <Link href={href("/sessions", { agent: a.agent_id })}>
            <strong>{number(a.sessions)}</strong>sessions
          </Link>
          <div>
            <strong>{number(a.distinct_pages)}</strong>distinct pages
          </div>
        </div>
        <Fields
          items={[
            ["Agent", agentTitle(a)],
            ["Identity", agentSubtitle(a)],
            ["Vendor", or(a.vendor)],
            ["First seen", time(a.first_seen)],
            ["Last seen", time(a.last_seen)],
            [
              "Common paths",
              a.common_paths.length ? (
                <code key="paths">{a.common_paths.join(" ")}</code>
              ) : (
                <Gap>None</Gap>
              ),
            ],
          ]}
        />
        {d.activity.length > 0 && (
          <div className="detail-bars" role="img" aria-label="Requests by hour">
            {d.activity.map((p) => (
              <div
                key={p.hour}
                title={`${dateTimeUTC(p.hour)} · ${number(p.requests)} requests`}
                style={{
                  display: "inline-block",
                  width: 8,
                  marginRight: 2,
                  height: Math.max(2, Math.round((p.requests / peak) * 40)),
                  background: "currentColor",
                  opacity: 0.6,
                }}
              />
            ))}
          </div>
        )}
        {d.top_paths.length > 0 && (
          <div className="detail-link-list">
            {d.top_paths.map((p) => (
              <Link
                key={p.path}
                href={href("/events", { agent: a.agent_id, path: p.path })}
              >
                <code>{p.path}</code>
                <span>{number(p.requests)} requests</span>
                <ChevronRight size={14} />
              </Link>
            ))}
          </div>
        )}
        {d.status_mix.length > 0 && (
          <Fields
            items={d.status_mix.map((s) => [
              s.status === null ? "No status" : `Status ${s.status}`,
              <Link
                key={String(s.status)}
                className="number-link"
                href={href("/events", {
                  agent: a.agent_id,
                  ...(s.status === null ? {} : { status: String(s.status) }),
                })}
              >
                {number(s.requests)} (
                {totalStatus ? Math.round((s.requests / totalStatus) * 100) : 0}
                %)
              </Link>,
            ])}
          />
        )}
      </DetailSection>
      <DetailSection title="Why this class" label="Inferred">
        <Fields
          items={[
            ["Class", <ClassName key="class" id={a.traffic_class} full />],
            [
              "Rule",
              why.rule_id ? (
                <code key="r">{why.rule_id}</code>
              ) : (
                <Gap>No rule recorded</Gap>
              ),
            ],
            ["Identity input", or(why.inputs.verdict)],
            ["Registry category", or(why.inputs.registry_category)],
            ["UA type", or(why.inputs.ua_type)],
            ["Edge signal", or(why.inputs.edge_signal)],
            ["Evidence", or(why.evidence)],
            [
              "Versions",
              why.rule_version || why.registry_version ? (
                `Rule v${why.rule_version ?? "?"} · registry v${why.registry_version ?? "?"}`
              ) : (
                <Gap>Unknown</Gap>
              ),
            ],
          ]}
        />
      </DetailSection>
      <DetailSection title="Verdict history" label="Observed">
        {d.verdict_history.length ? (
          d.verdict_history.map((v) => (
            <div className="history-item" key={v.id}>
              <div>
                <span className="timeline-dot" />
                <strong>{dateTimeUTC(v.checked_at)}</strong>
                <Status value={v.verdict} />
                <code>{v.method}</code>
              </div>
              <p>{v.evidence ?? "No evidence text recorded."}</p>
              <Link
                className="text-link"
                href={href("/events", { verdict_id: String(v.id) })}
              >
                Inspect requests with this verdict
                <ArrowUpRight size={12} />
              </Link>
            </div>
          ))
        ) : (
          <p className="muted">
            No identity check is recorded for this agent. The identity stays a
            claim.
          </p>
        )}
      </DetailSection>
      <DetailSection title="Client keys" label="Observed">
        {d.client_keys.length ? (
          d.client_keys.map((k) => (
            <Fields
              key={k.client_key}
              items={[
                ["Client key", <code key="k">{k.client_key}</code>],
                ["User agent", or(k.user_agent)],
                ["Client IP", or(k.client_ip)],
                [
                  "Shared IP",
                  k.shared_ip
                    ? "Yes · one address may hold more than one agent"
                    : "No shared-IP flag",
                ],
              ]}
            />
          ))
        ) : (
          <p className="muted">No client key is recorded for this agent.</p>
        )}
      </DetailSection>
      <DetailSection title="Sessions">
        <div className="detail-link-list">
          {d.sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => open("session", s.session_id)}
            >
              <code>{s.session_id}</code>
              <span>{number(s.requests)} requests</span>
              <ChevronRight size={14} />
            </button>
          ))}
          {d.sessions.length === 0 && (
            <p className="muted">
              No session is linked to this agent in this window.
            </p>
          )}
        </div>
        {a.sessions > 0 && (
          <Link
            className="text-link"
            href={href("/sessions", { agent: a.agent_id })}
          >
            All {number(a.sessions)} sessions
            <ArrowUpRight size={12} />
          </Link>
        )}
      </DetailSection>
    </>
  );
}
