"use client";

import { CircleAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/api/use-api";
import type { ImportList } from "@/lib/api/types";
import { dateTimeUTC, number } from "@/lib/format";
import { ApiGate, LoadingState, NoData } from "../shared";
import { StatusPill, sourceLabel } from "../sections/data-pipeline";
import { DetailSection, DetailProps } from "./common";

// The API has no endpoint for one import file. The detail reads the list and
// picks the file. A file older than the newest 200 is not found.
export function ImportDetail({ id }: DetailProps) {
  const site = useSearchParams().get("site") ?? "";
  const state = useApi<ImportList>("imports", {
    site: site || undefined,
    limit: 200,
  });

  return (
    <ApiGate state={state} skeleton={<LoadingState rows={5} />}>
      {(d) => {
        const r = d.items.find((f) => f.id === id);
        if (!r)
          return (
            <NoData title="Import file not found">
              The newest 200 import files do not include this ID.
            </NoData>
          );

        const facts: [string, string][] = [
          ["File ID", r.id],
          ["Received", dateTimeUTC(r.received_at)],
          [
            "Import finished",
            r.finished_at ? dateTimeUTC(r.finished_at) : "Not finished",
          ],
          ["Size", `${number(r.size_bytes)} bytes`],
          [
            "Event time range",
            r.min_ts && r.max_ts
              ? `${dateTimeUTC(r.min_ts)} – ${dateTimeUTC(r.max_ts)}`
              : "—",
          ],
          [
            "Cleanup date",
            r.delete_on
              ? dateTimeUTC(r.delete_on)
              : r.status === "failed"
                ? "Kept until a complete import"
                : "—",
          ],
        ];

        return (
          <>
            <div className="ops-head">
              <StatusPill status={r.status} />
              <span>
                {sourceLabel(r.source)} · {r.site_id} · {r.entry} · {r.priority}
              </span>
            </div>
            <div className="ops-figures">
              <div>
                <span>Imported</span>
                <strong>{number(r.lines_imported)}</strong>
                <small>of {number(r.lines_total)} lines</small>
              </div>
              <div>
                <span>Rejected</span>
                <strong className={r.lines_rejected ? "warn" : ""}>
                  {number(r.lines_rejected)}
                </strong>
                <small>Line numbers are not in the API</small>
              </div>
              <div>
                <span>Duplicates</span>
                <strong>{number(r.lines_duplicate)}</strong>
                <small>Skipped</small>
              </div>
            </div>
            {r.error && (
              <div className="error-notice">
                <CircleAlert size={16} />
                <div>
                  <strong>File could not be imported</strong>
                  <p>{r.error}</p>
                </div>
              </div>
            )}
            {r.overlap_warning && (
              <div className="ops-warning">
                <i />
                <p>{r.overlap_warning.message}</p>
              </div>
            )}
            <DetailSection title="Import file">
              <dl className="ops-facts">
                {facts.map(([label, value]) => (
                  <div key={label}>
                    <dt>{label}</dt>
                    <dd className="mono">{value}</dd>
                  </div>
                ))}
              </dl>
            </DetailSection>
            <p className="ops-note">
              Raw rejected text is not stored. To add a file, use Upload log
              file on the Sources tab.
            </p>
          </>
        );
      }}
    </ApiGate>
  );
}
