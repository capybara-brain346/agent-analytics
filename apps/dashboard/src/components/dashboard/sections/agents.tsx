"use client";

import { ArrowRight, Info } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import type { AgentRow } from "@/lib/api/types";
import { useScopedApi } from "@/lib/api/use-api";
import { dateTimeUTC, number } from "@/lib/format";
import {
  ApiGate,
  ClassName,
  Empty,
  Gap,
  Label,
  LoadingState,
  NumberLink,
  Panel,
  SearchField,
  Select,
  Status,
  TableFooter,
  Tip,
} from "../shared";
import { Props, option } from "./common";

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

const when = (iso: string | null) =>
  iso ? (
    <span className="mono muted">{dateTimeUTC(iso)}</span>
  ) : (
    <Gap>None</Gap>
  );

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
          options={option(
            ["VERIFIED", "CLAIMED", "UNVERIFIED", "SPOOFED", "UNKNOWN"],
            "All verification",
          )}
        />
        <span className="toolbar-end">
          {state.data ? `${state.data.length} agent groups` : ""}
        </span>
      </div>
      <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
        {(list) => (
          <>
            <div className="inline-stats">
              <span>
                <strong>{number(list.length)}</strong> agent groups <Label />
              </span>
              <span>
                <strong>
                  {number(
                    list.filter((a) => a.verification === "VERIFIED").length,
                  )}
                </strong>{" "}
                verified identities
              </span>
              <span className="muted">
                <Info size={13} />A user agent is a claim, not proof of
                identity.
              </span>
            </div>
            <Panel
              title="Agent directory"
              label="Observed"
              action={
                <Tip text="Verified means the source matched the vendor's published list. Other names are claims. Rows with the same name can differ by traffic class." />
              }
            >
              {list.length ? (
                <div className="table-scroll">
                  <table className="agents-table">
                    <thead>
                      <tr>
                        <th>Agent / client</th>
                        <th>Traffic class</th>
                        <th>Verification</th>
                        <th>First seen</th>
                        <th>Last seen</th>
                        <th aria-sort="descending">Requests ↓</th>
                        <th>Sessions</th>
                        <th>Pages</th>
                        <th>Common paths</th>
                      </tr>
                    </thead>
                    <tbody>
                      {list.map((a) => (
                        <tr key={`${a.agent_id}|${a.traffic_class}`}>
                          <td>
                            <button
                              className="agent-cell"
                              onClick={() => open("agent", a.agent_id)}
                            >
                              <span>
                                <strong>{agentTitle(a)}</strong>
                                <small>{agentSubtitle(a)}</small>
                              </span>
                            </button>
                          </td>
                          <td>
                            <ClassName id={a.traffic_class} />
                          </td>
                          <td>
                            {a.verification ? (
                              <Status value={a.verification} />
                            ) : (
                              <Gap>Not checked</Gap>
                            )}
                          </td>
                          <td>{when(a.first_seen)}</td>
                          <td>{when(a.last_seen)}</td>
                          <td>
                            <NumberLink
                              value={a.requests}
                              href={href("/events", { agent: a.agent_id })}
                            />
                          </td>
                          <td>
                            <NumberLink
                              value={a.sessions}
                              href={href("/sessions", { agent: a.agent_id })}
                            />
                          </td>
                          <td>{number(a.distinct_pages)}</td>
                          <td>
                            {a.common_paths.length ? (
                              <code>
                                {a.common_paths.slice(0, 3).join(" ")}
                              </code>
                            ) : (
                              <span className="muted">None</span>
                            )}
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
            </Panel>
          </>
        )}
      </ApiGate>
      <div className="notice">
        <Info size={15} />
        <div>
          <strong>Some traffic cannot be identified.</strong>
          <p>
            Browser requests without an edge signal remain Unknown. A shared IP
            can include more than one agent.
          </p>
        </div>
        <button className="text-link" onClick={() => open("legend", "labels")}>
          Read the label guide
          <ArrowRight size={13} />
        </button>
      </div>
    </>
  );
}
