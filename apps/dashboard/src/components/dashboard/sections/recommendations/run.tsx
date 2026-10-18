import { CircleAlert, Info } from "lucide-react";
import type { ApiError } from "@/lib/api/client";
import type { Paged, RunHeader } from "@/lib/api/types";
import { capitalize, dateTimeUTC, windowCaption } from "@/lib/format";
import { ErrorState, Panel } from "../../shared";
import { Pill } from "./status";

export type Generation =
  | { state: "idle" }
  | { state: "running" }
  | { state: "done"; run: RunHeader | null }
  | { state: "error"; error: ApiError };

export function RunStrip({ run }: { run: RunHeader }) {
  const { counts } = run;
  const cells: [string, number, string][] = [
    ["Recommendations", counts.total, `Run #${run.id}`],
    ["New", counts.new, "Not in the previous run"],
    ["Still open", counts.open, "Seen again"],
    [
      "Gone",
      counts.gone,
      run.compared_with_run_id === null
        ? "No earlier run to compare"
        : `Absent since run #${run.compared_with_run_id}`,
    ],
  ];
  return (
    <div className="metrics-strip rec-strip">
      {cells.map(([label, value, note]) => (
        <div className="metric-cell" key={label}>
          <span className="metric-label">{label}</span>
          <strong>{value}</strong>
          <div className="metric-bottom">{note}</div>
        </div>
      ))}
    </div>
  );
}

export function GenerationNotice({ generation }: { generation: Generation }) {
  if (generation.state === "running")
    return (
      <div className="rec-notice" role="status">
        <Info size={14} />A run is active. The previous list stays visible until
        it ends.
      </div>
    );
  if (generation.state === "done")
    return (
      <div className="rec-notice" role="status">
        <Info size={14} />
        {generation.run
          ? `Run #${generation.run.id} completed. The list shows the new run.`
          : "The run completed."}
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

export function RunFailed({ run }: { run: RunHeader }) {
  return (
    <div className="rec-notice fail" role="alert">
      <CircleAlert size={14} />
      <span>
        Run #{run.id} did not complete.{" "}
        {run.error ?? "This run did not finish."} <code>{run.status}</code>
      </span>
    </div>
  );
}

const runTone = (s: string) =>
  s === "success" ? "green" : s === "failed" ? "red" : "amber";

export function RunHistory({
  runs,
  shownId,
}: {
  runs: Paged<RunHeader>;
  shownId: number | undefined;
}) {
  return (
    <Panel title="Run history">
      <div className="table-scroll">
        <table className="rec-history" aria-label="Run history">
          <thead>
            <tr>
              <th>Run</th>
              <th data-col="status">Status</th>
              <th>New</th>
              <th data-col="confidence">Still open</th>
              <th data-col="evidence">Gone</th>
              <th data-col="window">Created</th>
            </tr>
          </thead>
          <tbody>
            {runs.items.map((r, i) => (
              <tr key={r.id}>
                <td>
                  <span className="rec-name">
                    #{r.id}
                    {i === 0 && <span className="page-tag">Latest</span>}
                    {r.id === shownId && (
                      <span className="page-tag">Shown</span>
                    )}
                  </span>
                  <span className="table-subline">
                    {windowCaption(r.window_start, r.window_end)} ·{" "}
                    {r.rule_version ? `v${r.rule_version}` : "version unknown"}
                  </span>
                </td>
                <td data-col="status">
                  <span title={r.error ?? undefined}>
                    <Pill
                      tone={runTone(r.status)}
                      label={capitalize(r.status)}
                    />
                  </span>
                </td>
                <td className="rec-figure-sm">{r.counts.new}</td>
                <td data-col="confidence" className="rec-figure-sm">
                  {r.counts.open}
                </td>
                <td data-col="evidence" className="rec-figure-sm">
                  {r.counts.gone}
                </td>
                <td data-col="window" className="rec-time">
                  {dateTimeUTC(r.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
