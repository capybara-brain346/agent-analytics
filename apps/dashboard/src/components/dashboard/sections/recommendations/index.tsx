"use client";

import { useState } from "react";
import { ApiError, apiPost } from "@/lib/api/client";
import { scopeFromQuery } from "@/lib/api/filters";
import { useApi } from "@/lib/api/use-api";
import type {
  GenerateResult,
  Paged,
  RecommendationList,
  RunHeader,
} from "@/lib/api/types";
import { dateTimeUTC } from "@/lib/format";
import {
  ApiGate,
  Gap,
  LoadingState,
  NoData,
  Panel,
  Segmented,
  Select,
  TableFooter,
  Tip,
} from "../../shared";
import type { Props } from "../common";
import {
  GenerationNotice,
  RunFailed,
  RunHistory,
  RunStrip,
  type Generation,
} from "./run";
import { RecTable } from "./table";

const patterns = [
  ["P1", "Product discovery"],
  ["P2", "Blocked access"],
  ["P3", "Broken navigation"],
  ["P4", "Content discoverability"],
  ["P5", "Full-journey simulation"],
];

function List({
  data,
  open,
  filtered,
  reset,
  generate,
}: {
  data: RecommendationList;
  open: Props["open"];
  filtered: boolean;
  reset: () => void;
  generate: () => void;
}) {
  const { items, gone, run } = data;
  return (
    <>
      <Panel
        title="Journeys to test"
        label="Inferred"
        action={
          <Tip text="Recommendations suggest tests. They do not confirm the cause of an issue." />
        }
      >
        {items.length ? (
          <>
            <RecTable items={items} open={open} />
            <TableFooter
              count={items.length}
              noun="recommendations, by priority"
            />
          </>
        ) : filtered ? (
          <NoData
            title="No recommendations match these filters"
            action={
              <button className="text-link" onClick={reset}>
                Clear filters
              </button>
            }
          />
        ) : (
          <NoData
            title={
              data.empty_reason === "no_run"
                ? "No recommendation run yet"
                : "This run found no journeys to test"
            }
            action={
              <button className="text-link" onClick={generate}>
                {data.empty_reason === "no_run" ? "Generate now" : "Run again"}
              </button>
            }
          />
        )}
      </Panel>
      {gone.length > 0 && (
        <Panel
          title="Gone since the previous run"
          action={
            <Tip
              text={`Gone means the pattern was absent in run #${run?.id}. It does not prove that the issue is fixed.`}
            />
          }
        >
          <RecTable items={gone} open={open} />
        </Panel>
      )}
    </>
  );
}

function Provenance({ run }: { run: RunHeader }) {
  return (
    <div className="rec-provenance">
      <span>Run #{run.id}</span>
      <span>{run.window_size} window</span>
      <span>
        Rule {run.rule_version ? `v${run.rule_version}` : <Gap>version</Gap>}
      </span>
      <span>
        Prompt {run.prompt_version ? `v${run.prompt_version}` : "none"}
      </span>
      <span>Model {run.model ?? "none (template text)"}</span>
      <span>Created {dateTimeUTC(run.created_at)}</span>
    </div>
  );
}

export function Recommendations({ open, filters, setFilter, reset }: Props) {
  const { site } = scopeFromQuery(filters);
  const pattern = filters.get("pattern") || "",
    status = filters.get("status") || "",
    confidence = filters.get("confidence") || "";
  const runParam = filters.get("run") || "";
  // The API has no status "all" and no "gone" filter on the main list.
  const change =
    status === "New" ? "new" : status === "Still open" ? "open" : "";
  const list = useApi<RecommendationList>("recommendations", {
    site,
    run: /^\d+$/.test(runParam) ? runParam : undefined,
    pattern: pattern || undefined,
    confidence: confidence.toLowerCase() || undefined,
    change: change || undefined,
  });
  const runs = useApi<Paged<RunHeader>>("recommendations/runs", {
    site,
    limit: 50,
  });
  const [generation, setGeneration] = useState<Generation>({ state: "idle" });
  const running = generation.state === "running";

  async function generate() {
    setGeneration({ state: "running" });
    try {
      const result = await apiPost<GenerateResult>("recommendations/generate", {
        site,
      });
      setGeneration({ state: "done", run: result.run });
      if (runParam) setFilter("run", "");
      list.reload();
      runs.reload();
    } catch (error) {
      setGeneration({
        state: "error",
        error:
          error instanceof ApiError
            ? error
            : new ApiError(0, "client_error", String(error)),
      });
    }
  }

  const filtered = Boolean(pattern || change || confidence);
  const run = list.data?.run ?? null;
  return (
    <>
      <div className="filter-toolbar">
        <Segmented
          label="Recommendation status"
          value={status}
          onChange={(v) => setFilter("status", v)}
          options={[
            { value: "", label: "All" },
            { value: "New", label: "New" },
            { value: "Still open", label: "Still open" },
          ]}
        />
        <Select
          label="Pattern"
          value={pattern}
          onChange={(v) => setFilter("pattern", v)}
          options={[
            { value: "", label: "All patterns" },
            ...patterns.map(([value, label]) => ({ value, label })),
          ]}
        />
        <Select
          label="Confidence"
          value={confidence}
          onChange={(v) => setFilter("confidence", v)}
          options={[
            { value: "", label: "All confidence" },
            { value: "high", label: "High" },
            { value: "medium", label: "Medium" },
            { value: "low", label: "Low" },
          ]}
        />
        {runs.data && runs.data.items.length > 0 && (
          <Select
            label="Recommendation run"
            value={runParam}
            onChange={(v) => setFilter("run", v)}
            options={runs.data.items.map((r, i) => ({
              value: i === 0 ? "" : String(r.id),
              label: i === 0 ? `Latest run #${r.id}` : `Run #${r.id}`,
            }))}
          />
        )}
        <span className="toolbar-end">
          <button
            className="btn-primary"
            onClick={generate}
            disabled={running}
            aria-busy={running}
          >
            {running ? "Running…" : "Generate now"}
          </button>
        </span>
      </div>
      <GenerationNotice generation={generation} />
      {run && run.status !== "success" && <RunFailed run={run} />}
      {run && <RunStrip run={run} />}
      <ApiGate state={list} skeleton={<LoadingState rows={6} />}>
        {(data) => (
          <List
            data={data}
            open={open}
            filtered={filtered}
            reset={reset}
            generate={generate}
          />
        )}
      </ApiGate>
      <ApiGate state={runs} skeleton={<LoadingState rows={3} />}>
        {(data) =>
          data.items.length > 0 && <RunHistory runs={data} shownId={run?.id} />
        }
      </ApiGate>
      {run && <Provenance run={run} />}
    </>
  );
}
