"use client";

import { ChevronRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import type { AgentRow } from "@/lib/api/types";
import { useScopedApi } from "@/lib/api/use-api";
import { dateTimeUTC, number } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Empty,
  Gap,
  LoadingState,
  NumberLink,
  Panel,
  SearchField,
  Select,
  TableFooter,
  Tip,
} from "../shared";
import type { Props } from "./common";

// Names the API gives to clients without a bot name (for example "unknown:browser").
export function agentTitle(a: Pick<AgentRow, "name" | "traffic_class">) {
  if (!a.name.startsWith("unknown:")) return a.name;
  const kind = a.name.slice("unknown:".length);
  return `Unknown (${kind === "browser" ? "browser UA" : `${kind} UA`})`;
}

// R3: the identity is a claim unless the verification is VERIFIED.
export function agentSubtitle(a: AgentRow) {
  if (a.name.startsWith("unknown:")) return "No bot name · identity unknown";
  return a.verification === "VERIFIED"
    ? [a.vendor, a.verification_note].filter(Boolean).join(" · ")
    : a.verification_note;
}

const VERIFICATION: Record<string, [string, string]> = {
  VERIFIED: ["green", "Verified"],
  CLAIMED: ["amber", "Claimed"],
  UNVERIFIED: ["amber", "Unverified"],
  SPOOFED: ["red", "Spoofed"],
  UNKNOWN: ["neutral", "Unknown"],
};

// Sentence-case verification pill. Colour is never the only signal: the dot and the word stay.
export function VerificationPill({ value }: { value: string | null }) {
  const [tone, word] = (value && VERIFICATION[value]) || [
    "neutral",
    value ?? "Not checked",
  ];
  return (
    <span className={`status ${tone}`}>
      <span className="status-dot" />
      {word}
    </span>
  );
}

const when = (iso: string | null) =>
  iso ? <span className="mono">{dateTimeUTC(iso)}</span> : <Gap>None</Gap>;

export function Agents({ href, open, filters, setFilter, reset }: Props) {
  const search = filters.get("q") || "",
    verification = filters.get("verdict") || "",
    selected = filters.get("class") || "";
  const scope = scopeFromQuery(filters);
  const state = useScopedApi<AgentRow[]>("agents", scope, {
    verification,
    q: search,
  });
  return (
    <>
      <div className="filter-toolbar">
        <SearchField
          placeholder="Search agents…"
          value={search}
          onChange={(v) => setFilter("q", v)}
        />
        <Select
          label="Verification"
          value={verification}
          onChange={(v) => setFilter("verdict", v)}
          options={[
            { value: "", label: "All verification" },
            ...Object.entries(VERIFICATION).map(([value, [, label]]) => ({
              value,
              label,
            })),
          ]}
        />
        <span className="toolbar-end">
          {state.data ? `${state.data.length} agent groups` : ""}
        </span>
      </div>
      <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
        {(list) => {
          const verified = list.filter((a) => a.verification === "VERIFIED");
          const unproven = list.filter(
            (a) => a.verification && a.verification !== "VERIFIED",
          );
          const requests = list.reduce((n, a) => n + a.requests, 0);
          const stats: [string, number, string][] = [
            ["Agent groups", list.length, "name and traffic class"],
            ["Verified identities", verified.length, "matched a vendor list"],
            ["Claims only", unproven.length, "not proven by evidence"],
            ["Requests", requests, "across these groups"],
          ];
          return (
            <>
              <div className="metrics-strip agents-metrics">
                {stats.map(([label, value, note]) => (
                  <div className="metric-cell" key={label}>
                    <div className="metric-label">{label}</div>
                    <strong>{number(value)}</strong>
                    <div className="metric-bottom">{note}</div>
                  </div>
                ))}
              </div>
              <Panel title="Agent directory">
                {list.length ? (
                  <div className="table-scroll">
                    <table className="agents-table" aria-label="Agents">
                      <thead>
                        <tr>
                          <th>Agent</th>
                          <th>
                            Verification
                            <Tip text="Verified means the source matched the vendor's published list. Other names are claims. Rows with the same name can differ by traffic class." />
                          </th>
                          <th aria-sort="descending">Requests</th>
                          <th data-band>Traffic class</th>
                          <th data-time>Last seen</th>
                          <th data-wide>Sessions</th>
                          <th data-chev aria-label="Open" />
                        </tr>
                      </thead>
                      <tbody>
                        {list.map((a) => (
                          <tr
                            key={`${a.agent_id}|${a.traffic_class}`}
                            className="row-link"
                            onClick={(e) =>
                              !(e.target as HTMLElement).closest("a, button") &&
                              open("agent", a.agent_id)
                            }
                          >
                            <td>
                              <button
                                className="agent-identity"
                                onClick={() => open("agent", a.agent_id)}
                              >
                                <strong>{agentTitle(a)}</strong>
                                <small className="table-subline">
                                  {agentSubtitle(a)}
                                </small>
                              </button>
                            </td>
                            <td>
                              <VerificationPill value={a.verification} />
                            </td>
                            <td className="figure">
                              <NumberLink
                                value={a.requests}
                                href={href("/events", { agent: a.agent_id })}
                              />
                            </td>
                            <td data-band>
                              <ClassName id={a.traffic_class} full />
                            </td>
                            <td data-time>{when(a.last_seen)}</td>
                            <td data-wide>
                              <NumberLink
                                value={a.sessions}
                                href={href("/sessions", { agent: a.agent_id })}
                              />
                            </td>
                            <td data-chev>
                              <ChevronRight size={14} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <Empty
                    reset={reset}
                    active={[
                      search && `“${search}”`,
                      verification,
                      selected && `class ${selected}`,
                    ].filter(Boolean)}
                  />
                )}
                <TableFooter count={list.length} noun="agent groups" />
                <div className="panel-footnote agents-note">
                  <span>
                    A user agent is a claim, not proof. Browser requests without
                    an edge signal stay unknown.
                  </span>
                </div>
              </Panel>
            </>
          );
        }}
      </ApiGate>
    </>
  );
}
