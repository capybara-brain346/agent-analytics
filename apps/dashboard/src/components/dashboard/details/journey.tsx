"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowUpRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { JourneyOut } from "@/lib/api/types";
import { number } from "@/lib/format";
import { ApiGate, Label, LoadingState, NumberLink } from "../shared";
import { JOURNEY_DROP_WARN_RATIO } from "../sections/pages-journeys/config";
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
              <span className={`qualifier ${j.critical ? "warn" : ""}`}>
                <i />
                {j.critical ? "Critical journey" : "Standard journey"}
              </span>
            </div>
            <DetailSection title="Journey steps" label="Observed">
              <ol className="dj-steps">
                {j.steps.map((p, i) => {
                  const share = totals[0] ? (totals[i] / totals[0]) * 100 : 0;
                  const prev = totals[i - 1] ?? 0;
                  const tone =
                    i === 0 || prev === 0
                      ? "pass"
                      : totals[i] === 0
                        ? "fail"
                        : totals[i] / prev < JOURNEY_DROP_WARN_RATIO
                          ? "warn"
                          : "pass";

                  return (
                    <li key={p}>
                      <span className="step-index">{i + 1}</span>
                      <code className="dj-path">{p}</code>
                      <span className="step-bar" aria-hidden="true">
                        <i className={tone} style={{ width: `${share}%` }} />
                      </span>
                      {totals[i] > 0 ? (
                        <Link
                          className="dj-count"
                          href={sessions({ reached: String(i + 1) })}
                        >
                          {number(totals[i])}
                          <ArrowUpRight size={12} />
                        </Link>
                      ) : (
                        <span className="dj-count count-static">0</span>
                      )}
                    </li>
                  );
                })}
              </ol>
            </DetailSection>
            <DetailSection title="Reached by traffic class" label="Observed">
              <div className="dp-table">
                <table aria-label="Reached by traffic class">
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
              <div className="dp-table">
                <table aria-label="Stopped at step">
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
            <div className="dp-foot">
              <p>
                <Label type="Unknown" />
                {j.outcome.text ??
                  "Reaching a page does not prove completion. A simulation is needed to inspect the task outcome."}
              </p>
            </div>
          </>
        );
      }}
    </ApiGate>
  );
}
