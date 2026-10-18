"use client";

import { useState } from "react";
import { Check, CircleAlert, Trash2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { ApiError, apiDelete } from "@/lib/api/client";
import { invalidate, useApi } from "@/lib/api/use-api";
import type { ImportDeleted, ImportFile, ImportList } from "@/lib/api/types";
import { dateTimeUTC, number } from "@/lib/format";
import { ApiGate, ErrorState, LoadingState, NoData } from "../shared";
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
  const [deleted, setDeleted] = useState<ImportDeleted | null>(null);

  if (deleted) return <DeletedNotice result={deleted} />;

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
              files on the Sources tab.
            </p>
            <DeleteImport file={r} onDeleted={setDeleted} />
          </>
        );
      }}
    </ApiGate>
  );
}

/** DELETE /api/imports/{id}, after a confirm step. */
function DeleteImport({
  file,
  onDeleted,
}: {
  file: ImportFile;
  onDeleted: (r: ImportDeleted) => void;
}) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const remove = () => {
    setBusy(true);
    setError(null);
    apiDelete<ImportDeleted>(`imports/${file.id}`).then(
      (r) => {
        invalidate("imports");
        onDeleted(r);
      },
      (e: unknown) => {
        setError(
          e instanceof ApiError
            ? e
            : new ApiError(0, "client_error", String(e)),
        );
        setBusy(false);
      },
    );
  };

  if (file.status === "importing")
    return (
      <p className="ops-note">
        The file is importing. You can delete it when the import ends.
      </p>
    );

  if (!confirm)
    return (
      <div className="import-delete">
        <button
          type="button"
          className="btn-standard danger"
          onClick={() => setConfirm(true)}
        >
          <Trash2 size={14} />
          Delete import
        </button>
      </div>
    );

  return (
    <DetailSection title="Delete this import">
      <div className="import-delete-confirm">
        <p>
          This removes the {number(file.lines_imported)} events of this file
          and the file record. The sessions, pages and agents of{" "}
          <strong>{file.site_id}</strong> are built again on the next pipeline
          run. A paired {file.source === "cdn" ? "origin" : "CDN"} file is read
          again, so its own lines stay. You can upload the same file again
          later.
        </p>
        {error && <ErrorState error={error} title="Delete failed" />}
        <div className="import-delete-actions">
          <button
            type="button"
            className="btn-standard danger"
            disabled={busy}
            onClick={remove}
          >
            <Trash2 size={14} />
            {busy ? "Deleting…" : "Delete import"}
          </button>
          <button
            type="button"
            className="btn-standard"
            disabled={busy}
            onClick={() => setConfirm(false)}
          >
            Cancel
          </button>
        </div>
      </div>
    </DetailSection>
  );
}

function DeletedNotice({ result }: { result: ImportDeleted }) {
  const partners = result.files_reimported.length;

  return (
    <div className="notice" role="status">
      <Check size={14} />
      <div>
        <strong>Import deleted</strong>
        <p>
          {number(result.events_deleted)} events removed from{" "}
          {result.site_id}. The views are built again on the next pipeline
          run.
          {partners > 0 &&
            ` ${partners} paired ${partners === 1 ? "file is" : "files are"} read again.`}
        </p>
      </div>
    </div>
  );
}
