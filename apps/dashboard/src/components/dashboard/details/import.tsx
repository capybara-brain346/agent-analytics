"use client";

import { CircleAlert, Info } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/api/use-api";
import type { ImportList } from "@/lib/api/types";
import { dateTimeUTC, number } from "@/lib/format";
import { ApiGate, Gap, LoadingState, NoData, Status } from "../shared";
import { statusLabel } from "../sections/data-pipeline";
import { DetailSection, Fields, DetailProps } from "./common";

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
        return (
          <>
            <div className="detail-chips">
              <Status value={statusLabel(r.status)} />
              <span>
                {r.source} · {r.site_id} · {r.entry} · {r.priority}
              </span>
            </div>
            <DetailSection title="Import file" label="Observed">
              <Fields
                items={[
                  ["File ID", <code key="id">{r.id}</code>],
                  ["Received", dateTimeUTC(r.received_at)],
                  [
                    "Import time",
                    r.finished_at ? dateTimeUTC(r.finished_at) : "Not finished",
                  ],
                  ["Size", `${number(r.size_bytes)} bytes`],
                  ["Lines", number(r.lines_total)],
                  ["Imported", number(r.lines_imported)],
                  ["Rejected", number(r.lines_rejected)],
                  ["Duplicates skipped", number(r.lines_duplicate)],
                  [
                    "Event time range",
                    r.min_ts && r.max_ts
                      ? `${dateTimeUTC(r.min_ts)} to ${dateTimeUTC(r.max_ts)}`
                      : "—",
                  ],
                  [
                    "Cleanup date",
                    r.delete_on
                      ? dateTimeUTC(r.delete_on)
                      : r.status === "failed"
                        ? "Retained until a complete import"
                        : "—",
                  ],
                ]}
              />
            </DetailSection>
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
              <div className="detail-notice">
                <Info size={14} />
                <p>{r.overlap_warning.message}</p>
              </div>
            )}
            <DetailSection title="Rejected lines" label="Observed">
              {r.lines_rejected ? (
                <Fields items={[["Rejected lines", number(r.rejects_count)]]} />
              ) : (
                <Fields items={[["Rejected lines", "None"]]} />
              )}
              <p className="muted">
                <Gap>
                  Line numbers and reasons are not in the API. Raw rejected text
                  is not stored.
                </Gap>
              </p>
            </DetailSection>
            <DetailSection title="Actions">
              <p className="muted">
                <Gap>
                  Force import again has no API endpoint. To add a file, use
                  Upload log file on the Sources tab.
                </Gap>
              </p>
            </DetailSection>
          </>
        );
      }}
    </ApiGate>
  );
}
