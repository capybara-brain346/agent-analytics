"use client";

import { Check, CircleAlert } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import { useSearchParams } from "next/navigation";
import type { PipelineRunOut } from "@/lib/api/types";
import { dateTimeUTC } from "@/lib/format";
import { ApiGate, Gap, LoadingState, Status } from "../shared";
import {
  countsText,
  durationText,
  laneName,
  statusLabel,
} from "../sections/data-pipeline";
import { DetailSection, Fields, DetailProps } from "./common";

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
            <div className="detail-chips">
              <Status value={statusLabel(r.status)} />
              <span>
                {laneName(r.lane)} lane · {r.site}
              </span>
            </div>
            <DetailSection title="Run summary" label="Observed">
              <Fields
                items={[
                  ["Run ID", <code key="id">{r.id}</code>],
                  ["Started", dateTimeUTC(r.started_at)],
                  [
                    "Finished",
                    r.finished_at ? dateTimeUTC(r.finished_at) : "Not finished",
                  ],
                  ["Duration", durationText(r.duration_seconds)],
                ]}
              />
            </DetailSection>
            <DetailSection title="Run steps" label="Observed">
              {steps.length === 0 ? (
                <Gap>The run recorded no step counts.</Gap>
              ) : (
                <div className="pipeline-steps">
                  {steps.map((step) => {
                    const bad = failed && step === r.failed_step;
                    return (
                      <div key={step}>
                        <span
                          className={`pipeline-check ${bad ? "failed" : ""}`}
                        >
                          {bad ? (
                            <CircleAlert size={14} />
                          ) : (
                            <Check size={14} />
                          )}
                        </span>
                        <strong>{step.replaceAll("_", " ")}</strong>
                        <span className="muted">
                          {countsText(r.counts[step])}
                        </span>
                        <Status value={bad ? "Failed" : "Complete"} />
                      </div>
                    );
                  })}
                </div>
              )}
              <p className="muted">
                <Gap>Time for each step is not in the API.</Gap>
              </p>
            </DetailSection>
            {failed && (
              <div className="error-notice">
                <CircleAlert size={16} />
                <div>
                  <strong>
                    Stopped at{" "}
                    {r.failed_step?.replaceAll("_", " ") ?? "an unknown step"}
                  </strong>
                  <p>{r.error ?? "The run recorded no error text."}</p>
                </div>
              </div>
            )}
          </>
        );
      }}
    </ApiGate>
  );
}
