"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { JourneyOut } from "@/lib/api/types";
import { number } from "@/lib/format";
import { ApiGate, Label, LoadingState, NumberLink } from "../shared";
import { DetailSection, Fields, DetailProps } from "./common";

export function JourneyDetail({ id, href }: DetailProps) {
  const state = useScopedApi<JourneyOut>(
    `journeys/${encodeURIComponent(id)}`,
    scopeFromQuery(useSearchParams()),
  );
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={5} />}>
      {(j) => {
        const sessions = (extra: Record<string, string>) =>
          href("/sessions", { journey: j.journey_id, ...extra });
        const totals = j.steps.map((_, i) =>
          j.by_class.reduce((s, c) => s + (c.reached[i] ?? 0), 0),
        );
        const retries = j.steps.map((_, i) =>
          j.by_class.reduce((s, c) => s + (c.retry_or_loop[i] ?? 0), 0),
        );
        return (
          <>
            <div className="detail-chips">
              <span className="page-tag">
                {j.critical ? "Critical journey" : "Standard journey"}
              </span>
            </div>
            <DetailSection title="Journey steps" label="Observed">
              <div className="journey-detail-steps">
                {j.steps.map((p, i) => (
                  <div key={p}>
                    <span className="sequence-number">{i + 1}</span>
                    <code>{p}</code>
                    {totals[i] > 0 ? (
                      <Link href={sessions({ reached: String(i + 1) })}>
                        {number(totals[i])} reached
                        <ArrowUpRight size={12} />
                      </Link>
                    ) : (
                      <span className="count-static">0 reached</span>
                    )}
                  </div>
                ))}
              </div>
            </DetailSection>
            <DetailSection title="Reached by traffic class" label="Observed">
              <div className="detail-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Class</th>
                      {j.steps.map((_, i) => (
                        <th key={i}>Step {i + 1}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {j.by_class.map((c) => (
                      <tr key={c.traffic_class}>
                        <td>{c.class_name}</td>
                        {c.reached.map((n, k) => (
                          <td key={k}>
                            <NumberLink
                              value={n}
                              href={sessions({
                                class: String(c.traffic_class),
                                reached: String(k + 1),
                              })}
                            />
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DetailSection>
            <DetailSection title="Stopped at step" label="Observed">
              <div className="detail-table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Class</th>
                      {j.steps.map((_, i) => (
                        <th key={i}>Step {i + 1}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {j.by_class.map((c) => (
                      <tr key={c.traffic_class}>
                        <td>{c.class_name}</td>
                        {c.stopped_at.map((n, k) => (
                          <td key={k}>{number(n)}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </DetailSection>
            <Fields
              items={[
                [
                  "Retries / loops by step",
                  retries.some((n) => n > 0)
                    ? retries
                        .map((n, i) => (n ? `step ${i + 1}: ${n}` : null))
                        .filter(Boolean)
                        .join(" · ")
                    : "None",
                ],
                ["Session grouping", "Same client + time gap · inferred"],
              ]}
            />
            <div className="outcome-panel">
              <Label type="Unknown" />
              <h3>Reaching a page does not prove completion</h3>
              <p>
                {j.outcome.text ??
                  "Logs cannot show task completion. A simulation is needed to inspect the task outcome."}
              </p>
            </div>
          </>
        );
      }}
    </ApiGate>
  );
}
