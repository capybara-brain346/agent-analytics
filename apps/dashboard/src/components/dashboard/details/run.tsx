"use client";

import { CircleAlert } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import { useSearchParams } from "next/navigation";
import type { PipelineRunOut } from "@/lib/api/types";
import { dateTimeUTC } from "@/lib/format";
import { ApiGate, Gap, LoadingState } from "../shared";
import {
  StatusPill,
  countEntries,
  durationText,
  laneName,
  stepName,
} from "../sections/data-pipeline";
import { DetailSection, DetailProps } from "./common";

function StepCounters({ value }: { value: unknown }) {
  const entries = countEntries(value);

  if (!entries.length)
    return <span className="step-empty">All counters 0</span>;

  return (
    <dl className="step-counters">
      {entries.map(([label, count]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{count}</dd>
        </div>
      ))}
    </dl>
  );
}

export function RunDetail({ id }: DetailProps) {
  const site = useSearchParams().get("site") ?? "";
  const state = useApi<PipelineRunOut>(`runs/${encodeURIComponent(id)}`, {
    site: site || undefined,
  });

  return (
    <ApiGate state={state} skeleton={<LoadingState rows={5} />}>
      {(r) => {
        const failed = r.status === "failed";
        const steps = Object.keys(r.counts);
        if (r.failed_step && !steps.includes(r.failed_step))
          steps.push(r.failed_step);

        return (
          <>
            <div className="ops-head">
              <StatusPill status={r.status} />
              <span>
                {laneName(r.lane)} lane · {r.site}
              </span>
            </div>
            <div className="ops-figures">
              <div>
                <span>Duration</span>
                <strong>{durationText(r.duration_seconds)}</strong>
              </div>
              <div>
                <span>Steps recorded</span>
                <strong>{steps.length}</strong>
              </div>
            </div>
            {failed && (
              <div className="error-notice">
                <CircleAlert size={16} />
                <div>
                  <strong>
                    Stopped at{" "}
                    {r.failed_step
                      ? stepName(r.failed_step).toLowerCase()
                      : "an unknown step"}
                  </strong>
                  <p>{r.error ?? "The run recorded no error text."}</p>
                </div>
              </div>
            )}
            <DetailSection title="Run steps">
              {steps.length === 0 ? (
                <Gap>The run recorded no step counts.</Gap>
              ) : (
                <ol className="step-timeline">
                  {steps.map((step) => {
                    const bad = failed && step === r.failed_step;
                    return (
                      <li key={step} className={bad ? "failed" : ""}>
                        <i />
                        <div>
                          <strong>{stepName(step)}</strong>
                          <StepCounters value={r.counts[step]} />
                        </div>
                        <em>{bad ? "Failed" : "Complete"}</em>
                      </li>
                    );
                  })}
                </ol>
              )}
              <p className="ops-note">Time for each step is not in the API.</p>
            </DetailSection>
            <DetailSection title="Run summary">
              <dl className="ops-facts">
                <div>
                  <dt>Run ID</dt>
                  <dd className="mono">{r.id}</dd>
                </div>
                <div>
                  <dt>Started</dt>
                  <dd className="mono">{dateTimeUTC(r.started_at)}</dd>
                </div>
                <div>
                  <dt>Finished</dt>
                  <dd className="mono">
                    {r.finished_at
                      ? dateTimeUTC(r.finished_at)
                      : "Not finished"}
                  </dd>
                </div>
              </dl>
            </DetailSection>
          </>
        );
      }}
    </ApiGate>
  );
}
