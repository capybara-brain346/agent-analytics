import { number } from "@/lib/format";
import { SearchField, Select } from "../../shared";
import type { Props } from "../common";
import { statusParam, stateParam } from "./config";

const knownStatus = [
  "200",
  "403",
  "429",
  "denied",
  "errors",
  "403,429",
  "4xx",
  "5xx",
  "4xx,5xx",
];

export function ActivityToolbar({
  isSessions,
  filters,
  setFilter,
  agentNames,
  total,
  noun,
  matching,
}: Pick<Props, "filters" | "setFilter"> & {
  isSessions: boolean;
  agentNames: string[];
  total: number | undefined;
  noun: string;
  matching: boolean;
}) {
  const f = (k: string) => filters.get(k) || "";
  const status = f("status");

  return (
    <div className="filter-toolbar activity-toolbar">
      {!isSessions && (
        <SearchField
          placeholder="Search paths"
          value={f("q")}
          onChange={(v) => setFilter("q", v)}
        />
      )}

      <Select
        label="Agent"
        value={f("agent")}
        onChange={(v) => setFilter("agent", v)}
        options={[
          { value: "", label: "All agents" },
          ...agentNames.map((a) => ({ value: a, label: a })),
        ]}
      />

      {isSessions ? (
        <>
          <Select
            label="Session state"
            value={stateParam(f("state"))}
            onChange={(v) => setFilter("state", v)}
            options={[
              { value: "", label: "All states" },
              { value: "closed", label: "Closed" },
              { value: "in_progress", label: "In progress" },
            ]}
          />

          {(
            [
              ["retry", "Has retry"],
              ["loop", "Has loop"],
              ["conversion", "Reached conversion page"],
            ] as const
          ).map(([k, label]) => (
            <button
              key={k}
              className={`filter-chip ${f(k) ? "selected" : ""}`}
              onClick={() => setFilter(k, f(k) ? "" : "yes")}
            >
              {label}
            </button>
          ))}
        </>
      ) : (
        <>
          <Select
            label="HTTP status"
            value={statusParam(status)}
            onChange={(v) => setFilter("status", v)}
            options={[
              { value: "", label: "All status codes" },
              { value: "200", label: "200 · OK" },
              { value: "403", label: "403 · Forbidden" },
              { value: "429", label: "429 · Rate limited" },
              { value: "403,429", label: "Denied · 403 / 429" },
              { value: "4xx", label: "4xx · Client errors" },
              { value: "5xx", label: "5xx · Server errors" },
              { value: "4xx,5xx", label: "All errors · 4xx / 5xx" },
              ...(status && !knownStatus.includes(status)
                ? [{ value: status, label: status }]
                : []),
            ]}
          />

          <Select
            label="Source"
            value={f("source").toLowerCase()}
            onChange={(v) => setFilter("source", v)}
            options={[
              { value: "", label: "All sources" },
              { value: "paired", label: "Paired" },
              { value: "cdn", label: "CDN" },
              { value: "origin", label: "Origin" },
            ]}
          />
        </>
      )}

      {total !== undefined && (
        <span className="toolbar-end">
          {number(total)} {matching ? "matching " : ""}
          {noun}
          {total === 1 ? "" : "s"}
        </span>
      )}
    </div>
  );
}
