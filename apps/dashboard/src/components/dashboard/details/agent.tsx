"use client";

import Link from "next/link";
import { ArrowUpRight, ChevronRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import type { AgentDetail as AgentDetailData } from "@/lib/api/types";
import { useScopedApi } from "@/lib/api/use-api";
import { capitalize, dateTimeUTC, number } from "@/lib/format";
import { ApiGate, ClassName, Confidence, Gap, LoadingState } from "../shared";
import {
  VerificationPill,
  agentSubtitle,
  agentTitle,
} from "../sections/agents";
import { DetailSection, Fields, DetailProps } from "./common";

const time = (iso: string | null) =>
  iso ? dateTimeUTC(iso) : <Gap>Unknown</Gap>;
const or = (v: string | null | undefined) => v ?? <Gap>Unknown</Gap>;
// Raw machine values (enums, ids, IPs, keys) render in mono.
const raw = (v: string | null | undefined) =>
  v ? <code>{v}</code> : <Gap>Unknown</Gap>;
// Enum values such as UNVERIFIED are read as words.
const word = (v: string | null | undefined) =>
  v ? capitalize(v.toLowerCase()) : <Gap>Unknown</Gap>;

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
      <div className="agent-head">
        <strong className="agent-head-name">{agentTitle(a)}</strong>
        <p className="agent-head-meta">
          {named
            ? agentSubtitle(a) || "No verification note"
            : "Exact client identity unknown · the name is a label, not proof"}
        </p>
        <div className="agent-head-tags">
          <VerificationPill value={a.verification} />
          <ClassName id={a.traffic_class} full />
          {a.confidence && <Confidence value={capitalize(a.confidence)} />}
        </div>
      </div>
      <DetailSection title="Activity" label="Observed">
        <div className="agent-facts">
          <Link href={href("/events", { agent: a.agent_id })}>
            <strong>{number(a.requests)}</strong>
            {a.requests === 1 ? "request" : "requests"}
          </Link>
          <Link href={href("/sessions", { agent: a.agent_id })}>
            <strong>{number(a.sessions)}</strong>
            {a.sessions === 1 ? "session" : "sessions"}
          </Link>
          <div>
            <strong>{number(a.distinct_pages)}</strong>
            {a.distinct_pages === 1 ? "distinct page" : "distinct pages"}
          </div>
        </div>
        <Fields
          items={[
            ["Vendor", or(a.vendor)],
            ["First seen", time(a.first_seen)],
            ["Last seen", time(a.last_seen)],
          ]}
        />
        {d.activity.length > 0 && (
          <>
            <div
              className="agent-bars"
              role="img"
              aria-label="Requests by hour"
            >
              {d.activity.map((p) => (
                <i
                  key={p.hour}
                  title={`${dateTimeUTC(p.hour)} · ${number(p.requests)} requests`}
                  style={{
                    height: `${Math.max(4, Math.round((p.requests / peak) * 100))}%`,
                  }}
                />
              ))}
            </div>
            <div className="agent-bars-caption">
              <span>{dateTimeUTC(d.activity[0].hour)}</span>
              {d.activity.length > 1 && (
                <span>
                  {dateTimeUTC(d.activity[d.activity.length - 1].hour)}
                </span>
              )}
            </div>
          </>
        )}
        {d.top_paths.length > 0 ? (
          <div className="agent-rows">
            {d.top_paths.map((p) => (
              <Link
                key={p.path}
                href={href("/events", { agent: a.agent_id, path: p.path })}
              >
                <code>{p.path}</code>
                <span>{number(p.requests)}</span>
                <ChevronRight size={14} />
              </Link>
            ))}
          </div>
        ) : (
          a.common_paths.length > 0 && (
            <Fields
              items={[
                [
                  "Common paths",
                  <code key="paths">{a.common_paths.join(" ")}</code>,
                ],
              ]}
            />
          )
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
            ["Identity input", word(why.inputs.verdict)],
            ["Registry category", raw(why.inputs.registry_category)],
            ["UA type", raw(why.inputs.ua_type)],
            ["Edge signal", raw(why.inputs.edge_signal)],
            ["Evidence", or(why.evidence)],
            [
              "Versions",
              why.rule_version || why.registry_version ? (
                <code key="v">{`rule v${why.rule_version ?? "?"} · registry v${why.registry_version ?? "?"}`}</code>
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
                <VerificationPill value={v.verdict} />
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
                ["User agent", raw(k.user_agent)],
                ["Client IP", raw(k.client_ip)],
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
        <div className="agent-rows">
          {d.sessions.map((s) => (
            <button
              key={s.session_id}
              onClick={() => open("session", s.session_id)}
            >
              <code>{s.session_id}</code>
              <span>
                {number(s.requests)} {s.requests === 1 ? "request" : "requests"}
              </span>
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
            {a.sessions === 1
              ? "View the session"
              : `All ${number(a.sessions)} sessions`}
            <ArrowUpRight size={12} />
          </Link>
        )}
      </DetailSection>
    </>
  );
}
