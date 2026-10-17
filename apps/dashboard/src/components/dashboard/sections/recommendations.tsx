"use client";

import { useState } from "react";
import { ChevronRight, Filter, Info, Sparkles } from "lucide-react";
import { ApiError, apiPost } from "@/lib/api/client";
import { scopeFromQuery } from "@/lib/api/filters";
import { useApi } from "@/lib/api/use-api";
import type {
  GenerateResult,
  Paged,
  RecommendationItem,
  RecommendationList,
  RunHeader,
} from "@/lib/api/types";
import { capitalize, dateTimeUTC, number, windowCaption } from "@/lib/format";
import {
  ApiGate,
  Confidence,
  ErrorState,
  Gap,
  Label,
  LoadingState,
  NoData,
  Panel,
  Select,
  Status,
  TextLink,
  Tip,
} from "../shared";
import { Props } from "./common";

const patterns = [
  ["P1", "Product discovery"],
  ["P2", "Blocked access"],
  ["P3", "Broken navigation"],
  ["P4", "Content discoverability"],
  ["P5", "Full-journey simulation"],
];
const changeLabel = (c: string | null) =>
  c === "new"
    ? "New"
    : c === "open"
      ? "Still open"
      : c === "gone"
        ? "Gone"
        : "";

type Generation =
  | { state: "idle" }
  | { state: "running" }
  | { state: "done"; run: RunHeader | null }
  | { state: "error"; error: ApiError };

function RunSummary({
  run,
  runs,
  selected,
  generation,
  onGenerate,
  setFilter,
}: {
  run: RunHeader | null;
  runs: Paged<RunHeader> | null;
  selected: string;
  generation: Generation;
  onGenerate: () => void;
  setFilter: Props["setFilter"];
}) {
  const running = generation.state === "running";
  return (
    <div className="run-summary">
      <span className="run-icon">
        <Sparkles size={16} />
      </span>
      <div>
        {run ? (
          <>
            <strong>Recommendation run #{run.id}</strong>
            <span>
              {windowCaption(run.window_start, run.window_end)} ·{" "}
              {run.window_size} window · created {dateTimeUTC(run.created_at)}
            </span>
          </>
        ) : (
          <strong>No recommendation run yet</strong>
        )}
      </div>
      {run && (
        <div className="run-changes">
          <Status value={`${run.counts.new} new`} />
          <span>{run.counts.open} still open</span>
          <span>{run.counts.gone} gone</span>
          {run.compared_with_run_id === null ? (
            <span className="muted">No earlier run to compare</span>
          ) : (
            <span className="muted">vs run #{run.compared_with_run_id}</span>
          )}
        </div>
      )}
      {runs && runs.items.length > 0 && (
        <Select
          label="Recommendation run"
          value={selected}
          onChange={(v) => setFilter("run", v)}
          options={runs.items.map((r, i) => ({
            value: i === 0 ? "" : String(r.id),
            label: i === 0 ? `Latest run #${r.id}` : `Run #${r.id}`,
          }))}
        />
      )}
      <button
        className="button primary"
        onClick={onGenerate}
        disabled={running}
        aria-busy={running}
      >
        {running ? "Running…" : "Generate recommendations now"}
      </button>
    </div>
  );
}

function GenerationNotice({ generation }: { generation: Generation }) {
  if (generation.state === "running")
    return (
      <div className="detail-notice" role="status">
        <Info size={14} />
        <p>
          A pipeline run is active. The previous list stays visible until it
          ends.
        </p>
      </div>
    );
  if (generation.state === "done")
    return (
      <div className="detail-notice" role="status">
        <Info size={14} />
        <p>
          {generation.run
            ? `Run #${generation.run.id} completed. The list shows the new run.`
            : "The run completed."}
        </p>
      </div>
    );
  if (generation.state === "error") {
    const { error } = generation;
    return (
      <ErrorState
        error={error}
        title={
          error.code === "lock_taken"
            ? "Another run is active"
            : "Could not generate recommendations"
        }
      />
    );
  }
  return null;
}

function Evidence({ r, open }: { r: RecommendationItem; open: Props["open"] }) {
  return (
    <>
      <TextLink onClick={() => open("recommendation", String(r.id))}>
        {number(r.sessions_count)} sessions
      </TextLink>
      <div className="table-subline">
        <TextLink onClick={() => open("recommendation", String(r.id))}>
          {number(r.events_count)} events
        </TextLink>
      </div>
    </>
  );
}

function List({
  data,
  open,
  filtered,
  reset,
}: {
  data: RecommendationList;
  open: Props["open"];
  filtered: boolean;
  reset: () => void;
}) {
  const { items, gone, run } = data;
  return (
    <>
      <Panel
        title="Journeys to test"
        label="Inferred"
        action={
          <Tip text="Priority = Impact × Frequency × Severity × Confidence. Open a recommendation to inspect each factor." />
        }
      >
        {items.length ? (
          <>
            <div className="recommendation-cards">
              {items.map((r, i) => (
                <button
                  key={r.id}
                  className="recommendation-row"
                  onClick={() => open("recommendation", String(r.id))}
                >
                  <span className={`rank rank-${i}`}>{r.rank ?? i + 1}</span>
                  <span className="rec-main">
                    <span className="rec-title">
                      {r.recommended_test ?? r.target}
                    </span>
                    <span className="rec-meta">
                      {r.pattern_name}
                      <span>·</span>
                      {changeLabel(r.change)}
                      <span>·</span>
                      {capitalize(r.confidence)} confidence
                    </span>
                  </span>
                  <span className="priority-score">
                    <strong>{r.priority.score}</strong>
                    <span>priority</span>
                  </span>
                  <ChevronRight className="row-chevron" size={15} />
                </button>
              ))}
            </div>
            <div className="table-scroll recommendations-table-wrap">
              <table className="recommendations-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Recommended test</th>
                    <th aria-sort="descending">Priority ↓</th>
                    <th>Confidence</th>
                    <th>
                      Evidence <Label />
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((r, i) => (
                    <tr key={r.id}>
                      <td className="muted">{r.rank ?? i + 1}</td>
                      <td>
                        <TextLink
                          className="rec-table-title"
                          onClick={() => open("recommendation", String(r.id))}
                        >
                          {r.recommended_test ?? r.target}
                        </TextLink>
                        <div className="table-subline">
                          {r.pattern_name}
                          {r.change && <Status value={changeLabel(r.change)} />}
                        </div>
                      </td>
                      <td>
                        <span className="score-button">{r.priority.score}</span>
                        <div className="table-subline">
                          <code>{r.priority.formula}</code>
                        </div>
                      </td>
                      <td>
                        <Confidence value={capitalize(r.confidence)} />
                      </td>
                      <td>
                        <Evidence r={r} open={open} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
        ) : data.empty_reason === "no_run" ? (
          <NoData title="No recommendation run yet">
            Use “Generate recommendations now” to create the first run.
          </NoData>
        ) : (
          <NoData title="This run found no journeys to test">
            The rules found no pattern with enough evidence in the window.
          </NoData>
        )}
        <div className="panel-footnote">
          <Info size={13} />
          Recommendations suggest tests. They do not confirm the cause of an
          issue.
        </div>
      </Panel>
      {gone.length > 0 && (
        <details className="disclosure-panel">
          <summary>
            <ChevronRight size={14} />
            <span>Gone since the previous run</span>
            <span className="count-chip">{gone.length}</span>
          </summary>
          <div className="disclosure-body">
            {gone.map((r) => (
              <div className="gone-item" key={r.id}>
                <TextLink onClick={() => open("recommendation", String(r.id))}>
                  {r.recommended_test ?? r.target}
                </TextLink>
                <Status value="Gone" />
                <span className="muted">
                  {r.pattern_name} · the pattern was absent in run #{run?.id}.
                </span>
              </div>
            ))}
            <p className="muted">
              Gone means the pattern was absent in this window. It does not
              prove that the issue is fixed.
            </p>
          </div>
        </details>
      )}
    </>
  );
}

function RunHistory({
  runs,
  shownId,
}: {
  runs: Paged<RunHeader>;
  shownId: number | undefined;
}) {
  return (
    <Panel
      title="Run history"
      action={<span className="muted">Saved snapshots</span>}
    >
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Run</th>
              <th>Window</th>
              <th>Created</th>
              <th>Status</th>
              <th>New</th>
              <th>Still open</th>
              <th>Gone</th>
              <th>Rule version</th>
            </tr>
          </thead>
          <tbody>
            {runs.items.map((r, i) => (
              <tr key={r.id}>
                <td>
                  #{r.id}
                  {i === 0 && <span className="page-tag">Latest</span>}
                  {r.id === shownId && <span className="page-tag">Shown</span>}
                </td>
                <td>{windowCaption(r.window_start, r.window_end)}</td>
                <td>{dateTimeUTC(r.created_at)}</td>
                <td>
                  {r.status === "success" ? (
                    capitalize(r.status)
                  ) : (
                    <span title={r.error ?? undefined}>
                      {capitalize(r.status)}
                    </span>
                  )}
                </td>
                <td>{r.counts.new}</td>
                <td>{r.counts.open}</td>
                <td>{r.counts.gone}</td>
                <td>
                  {r.rule_version ? <code>v{r.rule_version}</code> : "Unknown"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
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
  return (
    <>
      <RunSummary
        run={list.data?.run ?? null}
        runs={runs.data}
        selected={runParam}
        generation={generation}
        onGenerate={generate}
        setFilter={setFilter}
      />
      <GenerationNotice generation={generation} />
      {list.data?.run?.status && list.data.run.status !== "success" && (
        <ErrorState
          error={{
            code: list.data.run.status,
            message: list.data.run.error ?? "This run did not finish.",
          }}
          title={`Run #${list.data.run.id} did not complete`}
        />
      )}
      <div className="filter-toolbar">
        <Filter size={14} />
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
          label="Recommendation status"
          value={status}
          onChange={(v) => setFilter("status", v)}
          options={[
            { value: "", label: "All statuses" },
            { value: "New", label: "New" },
            { value: "Still open", label: "Still open" },
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
        <span className="toolbar-end">
          {list.data
            ? `${list.data.items.length} recommendations · sorted by priority`
            : "Loading"}
        </span>
      </div>
      <ApiGate state={list} skeleton={<LoadingState rows={6} />}>
        {(data) => (
          <List data={data} open={open} filtered={filtered} reset={reset} />
        )}
      </ApiGate>
      <ApiGate state={runs} skeleton={<LoadingState rows={3} />}>
        {(data) => <RunHistory runs={data} shownId={list.data?.run?.id} />}
      </ApiGate>
      {list.data?.run && (
        <div className="meta-line">
          <span>
            Rule{" "}
            {list.data.run.rule_version ? (
              `v${list.data.run.rule_version}`
            ) : (
              <Gap>version</Gap>
            )}
          </span>
          <span>
            Prompt{" "}
            {list.data.run.prompt_version
              ? `v${list.data.run.prompt_version}`
              : "none"}
          </span>
          <span>Model {list.data.run.model ?? "none (template text)"}</span>
          <span>Created {dateTimeUTC(list.data.run.created_at)}</span>
        </div>
      )}
    </>
  );
}
