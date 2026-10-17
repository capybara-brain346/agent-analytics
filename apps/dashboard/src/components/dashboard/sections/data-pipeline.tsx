"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Check,
  CircleAlert,
  FileText,
  Info,
  LockKeyhole,
  Upload,
} from "lucide-react";
import { ApiError, apiHealth, apiPost } from "@/lib/api/client";
import { scopeFromQuery } from "@/lib/api/filters";
import { useApi, useQuery, useScopedApi } from "@/lib/api/use-api";
import type {
  Health,
  ImportFile,
  ImportList,
  Overview,
  Paged,
  PipelineRunOut,
  IngestAccepted,
} from "@/lib/api/types";
import { dateTimeUTC, number, timeUTC } from "@/lib/format";
import {
  ApiGate,
  ErrorState,
  Gap,
  LoadingState,
  NoData,
  Panel,
  Status,
  TableFooter,
  TextLink,
} from "../shared";
import { Props } from "./common";

/** Status words of the API, as the Status badge knows them. */
export function statusLabel(status: string) {
  switch (status) {
    case "success":
      return "Complete";
    case "failed":
      return "Failed";
    case "running":
    case "importing":
      return "In progress";
    case "new":
      return "New";
    default:
      return status.charAt(0).toUpperCase() + status.slice(1);
  }
}

export const laneName = (lane: string) => (lane === "fast" ? "Fast" : "Slow");

export function durationText(seconds: number | null) {
  if (seconds === null) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 120) return `${seconds.toFixed(1)} s`;
  return `${Math.round(seconds / 60)} min`;
}

/** Counts of one pipeline step, "files 3 · lines_total 40". Values that are not numbers are left out. */
export function countsText(value: unknown) {
  if (!value || typeof value !== "object") return "—";
  const parts = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => typeof v === "number")
    .map(([k, v]) => `${k.replaceAll("_", " ")} ${number(v as number)}`);
  return parts.length ? parts.join(" · ") : "—";
}

const tabs = [
  { id: "sources", name: "Sources" },
  { id: "imports", name: "Import runs" },
  { id: "runs", name: "Pipeline runs" },
  { id: "health", name: "Health & alerts" },
  { id: "settings", name: "Settings" },
];

export function DataPipeline({ href, open, filters }: Props) {
  const tab = filters.get("tab") || "sources";
  const scope = scopeFromQuery(filters);
  const health = useQuery<Health>("health", (signal) => apiHealth(signal));
  const lanes = (health.data?.lanes ?? []).filter(
    (l) => !scope.site || l.site_id === scope.site,
  );
  const alerts = (health.data?.alerts ?? []).filter(
    (a) => !scope.site || a.site_id === scope.site,
  );
  const alertText = `${alerts.length} open alert${alerts.length === 1 ? "" : "s"}`;
  const alertSite = alerts[0] ? ` · ${alerts[0].site_id}` : "";
  return (
    <>
      <div className="health-strip">
        {health.error && (
          <span className="amber-text">
            <CircleAlert size={12} />
            Health unknown · {health.error.message}
          </span>
        )}
        {health.data === null && !health.error && (
          <span className="muted">Checking health</span>
        )}
        {lanes.map((l) => (
          <span key={`${l.site_id}-${l.lane}`}>
            <i className="live-dot" />
            <strong>
              {laneName(l.lane)} lane {l.healthy ? "healthy" : "late"}
            </strong>
            <span>
              {l.site_id} ·{" "}
              {l.last_success
                ? `Last complete ${timeUTC(l.last_success)}`
                : "No complete run yet"}
            </span>
          </span>
        ))}
        {health.data &&
          alerts.length > 0 &&
          (tab === "health" ? (
            <span className="amber-text">
              <CircleAlert size={12} />
              {alertText}
              {alertSite}
            </span>
          ) : (
            <Link
              className="amber-text"
              href={href("/data", { tab: "health" })}
            >
              <CircleAlert size={12} />
              {alertText}
              {alertSite}
            </Link>
          ))}
      </div>
      <div className="page-tabs">
        {tabs.map((t) => (
          <Link
            key={t.id}
            className={tab === t.id ? "active" : ""}
            aria-current={tab === t.id ? "page" : undefined}
            href={href("/data", { tab: t.id })}
            scroll={false}
          >
            {t.name}
          </Link>
        ))}
      </div>
      {tab === "sources" && (
        <SourcesTab href={href} filters={filters} health={health.data} />
      )}
      {tab === "imports" && <ImportsTab open={open} filters={filters} />}
      {tab === "runs" && <RunsTab open={open} filters={filters} />}
      {tab === "health" && (
        <HealthTab state={health} lanes={lanes} alerts={alerts} />
      )}
      {tab === "settings" && <SettingsTab filters={filters} />}
    </>
  );
}

// ---- sources

type SourceRow = {
  site: string;
  source: string;
  files: number;
  lastFile: string | null;
  lastEvent: string | null;
  lastStatus: string | null;
};

function sourceRows(
  files: ImportFile[],
  configured: { site: string; sources: string[] } | null,
): SourceRow[] {
  const map = new Map<string, SourceRow>();
  const row = (site: string, source: string) => {
    const key = `${site}|${source}`;
    let r = map.get(key);
    if (!r) {
      r = {
        site,
        source,
        files: 0,
        lastFile: null,
        lastEvent: null,
        lastStatus: null,
      };
      map.set(key, r);
    }
    return r;
  };
  for (const f of files) {
    const r = row(f.site_id, f.source);
    r.files += 1;
    if (!r.lastFile || f.received_at > r.lastFile) {
      r.lastFile = f.received_at;
      r.lastStatus = f.status;
    }
    if (f.max_ts && (!r.lastEvent || f.max_ts > r.lastEvent))
      r.lastEvent = f.max_ts;
  }
  if (configured) for (const s of configured.sources) row(configured.site, s);
  return [...map.values()].sort((a, b) =>
    `${a.site}${a.source}`.localeCompare(`${b.site}${b.source}`),
  );
}

function SourcesTab({
  href,
  filters,
  health,
}: {
  href: Props["href"];
  filters: Props["filters"];
  health: Health | null;
}) {
  const scope = scopeFromQuery(filters);
  const imports = useApi<ImportList>("imports", {
    site: scope.site || undefined,
    limit: 200,
  });
  const overview = useScopedApi<Overview>("overview", scope);
  const upload = useUpload(
    scope.site,
    imports.data?.items[0]?.site_id,
    overview.data?.coverage.sources_configured ?? [],
    () => imports.reload(),
  );
  const coverage = overview.data?.coverage;
  const site = overview.data?.window.site ?? null;
  return (
    <>
      <Panel
        title="Data sources"
        label="Observed"
        action={<UploadButton upload={upload} />}
      >
        <UploadResult upload={upload} />
        <ApiGate state={imports} skeleton={<LoadingState rows={3} />}>
          {(d) => {
            const rows = sourceRows(
              d.items,
              coverage && site
                ? { site, sources: coverage.sources_configured }
                : null,
            );
            if (!rows.length)
              return (
                <NoData title="No files received">
                  No import file exists for this site yet.
                </NoData>
              );
            return (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Site / source</th>
                      <th>Last file</th>
                      <th>Last event</th>
                      <th>Files</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const alert = health?.alerts.find(
                        (a) => a.site_id === r.site && a.source === r.source,
                      );
                      return (
                        <tr key={`${r.site}-${r.source}`}>
                          <td>
                            <strong>{r.site}</strong>
                            <div className="table-subline">
                              {r.source.toUpperCase() === "CDN"
                                ? "CDN log"
                                : r.source === "origin"
                                  ? "Origin log"
                                  : r.source}
                            </div>
                          </td>
                          <td className="mono">
                            {r.lastFile ? dateTimeUTC(r.lastFile) : "—"}
                          </td>
                          <td className="mono">
                            {r.lastEvent ? dateTimeUTC(r.lastEvent) : "—"}
                          </td>
                          <td>{r.files ? number(r.files) : "—"}</td>
                          <td>
                            {alert ? (
                              <span className="amber-text">
                                <CircleAlert size={12} />
                                {alert.message}
                              </span>
                            ) : r.lastStatus ? (
                              <Status value={statusLabel(r.lastStatus)} />
                            ) : (
                              <Gap>No file yet</Gap>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          }}
        </ApiGate>
        <p className="muted table-note">
          Format and field map of each source are not in the API. They are files
          in <code>apps/api/config/</code>. Files and events show the last 200
          import files.
        </p>
      </Panel>
      <div className="two-column equal-columns">
        <Panel title="Source coverage" label="Observed">
          <ApiGate state={overview} skeleton={<LoadingState rows={2} />}>
            {(o) => (
              <div className="coverage-summary">
                {o.coverage.paired_share_pct === null ? (
                  <Gap>Pairing is not measured: no paired source present.</Gap>
                ) : (
                  <strong>
                    {o.coverage.paired_share_pct.toFixed(1)}%{" "}
                    <span>origin requests paired</span>
                  </strong>
                )}
                <p>
                  Sources configured: {o.coverage.sources_configured.join(", ")}
                  . Sources present in the window:{" "}
                  {o.coverage.sources_present.join(", ") || "none"}.
                </p>
                <Link
                  className="text-link"
                  href={href("/events", { source: "Paired" })}
                >
                  Inspect paired requests
                  <ArrowRight size={13} />
                </Link>
              </div>
            )}
          </ApiGate>
        </Panel>
        <Panel title="Current data gaps" label="Unknown">
          <ApiGate state={overview} skeleton={<LoadingState rows={2} />}>
            {(o) => (
              <div className="gap-list">
                {o.coverage.cannot_see.map((g) => (
                  <div key={g}>
                    <Info size={15} />
                    <span>
                      <strong>Cannot see: {g}</strong>
                    </span>
                  </div>
                ))}
                {o.coverage.partial.map((g) => (
                  <div key={g}>
                    <CircleAlert size={15} />
                    <span>
                      <strong>Partial: {g}</strong>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </ApiGate>
        </Panel>
      </div>
    </>
  );
}

// ---- upload (POST /api/imports/upload)

type UploadState = {
  site: string;
  sources: string[];
  source: string;
  setSource: (s: string) => void;
  busy: boolean;
  result: IngestAccepted | null;
  error: ApiError | null;
  send: (file: File) => void;
};

function useUpload(
  scopeSite: string,
  fallbackSite: string | undefined,
  sources: string[],
  done: () => void,
): UploadState {
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<IngestAccepted | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const site = scopeSite || fallbackSite || "";
  const chosen = sources.includes(source) ? source : (sources[0] ?? "");
  const send = (file: File) => {
    setBusy(true);
    setResult(null);
    setError(null);
    apiPost<IngestAccepted>(
      "imports/upload",
      { site, source: chosen },
      file,
    ).then(
      (r) => {
        setResult(r);
        setBusy(false);
        done();
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
  return {
    site,
    sources,
    source: chosen,
    setSource,
    busy,
    result,
    error,
    send,
  };
}

function UploadButton({ upload }: { upload: UploadState }) {
  const input = useRef<HTMLInputElement>(null);
  const disabled = upload.busy || !upload.site || !upload.source;
  return (
    <span className="upload-action">
      {upload.sources.length > 1 && (
        <select
          aria-label="Source of the file"
          value={upload.source}
          onChange={(e) => upload.setSource(e.target.value)}
          disabled={upload.busy}
        >
          {upload.sources.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      )}
      <input
        ref={input}
        type="file"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (file) upload.send(file);
        }}
      />
      <button
        type="button"
        className="text-link"
        disabled={disabled}
        title={
          upload.site
            ? `Upload a log file for ${upload.site} (${upload.source})`
            : "Select a site first"
        }
        onClick={() => input.current?.click()}
      >
        <Upload size={13} />
        {upload.busy ? "Uploading…" : "Upload log file"}
      </button>
    </span>
  );
}

function UploadResult({ upload }: { upload: UploadState }) {
  if (upload.busy)
    return (
      <div className="notice compact-notice" role="status">
        <Info size={14} />
        <span>
          Uploading to {upload.site} ({upload.source})…
        </span>
      </div>
    );
  if (upload.error)
    return <ErrorState error={upload.error} title="Upload failed" />;
  if (upload.result)
    return (
      <div className="notice compact-notice" role="status">
        <Check size={14} />
        <span>
          {upload.result.duplicate
            ? "This file is already stored. It was not added again."
            : "File accepted. It shows as new until the import runs."}{" "}
          File ID <code>{upload.result.file_id}</code>
        </span>
      </div>
    );
  return null;
}

// ---- import runs

function ImportsTab({
  open,
  filters,
}: {
  open: Props["open"];
  filters: Props["filters"];
}) {
  const scope = scopeFromQuery(filters);
  const state = useApi<ImportList>("imports", {
    site: scope.site || undefined,
    limit: 50,
    offset: 0,
  });
  return (
    <Panel title="Import runs" label="Observed">
      <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
        {(d) =>
          d.items.length === 0 ? (
            <NoData title="No import files">No file was received yet.</NoData>
          ) : (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>File</th>
                      <th>Site / source</th>
                      <th>Received</th>
                      <th>Status</th>
                      <th>Lines</th>
                      <th>Imported</th>
                      <th>Rejected</th>
                      <th>Duplicates</th>
                      <th>Cleanup</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((r) => (
                      <tr key={r.id}>
                        <td>
                          <TextLink
                            className="mono"
                            onClick={() => open("import", r.id)}
                          >
                            {r.id.slice(0, 8)}
                          </TextLink>
                        </td>
                        <td>
                          {r.site_id} · {r.source}
                        </td>
                        <td className="mono">{dateTimeUTC(r.received_at)}</td>
                        <td>
                          <Status value={statusLabel(r.status)} />
                          {r.overlap_warning && (
                            <span
                              className="amber-text"
                              title={r.overlap_warning.message}
                            >
                              {" "}
                              <CircleAlert size={12} />
                            </span>
                          )}
                        </td>
                        <td>{number(r.lines_total)}</td>
                        <td>{number(r.lines_imported)}</td>
                        <td
                          className={r.lines_rejected ? "amber-text" : "muted"}
                        >
                          {number(r.lines_rejected)}
                        </td>
                        <td className="muted">{number(r.lines_duplicate)}</td>
                        <td className="mono muted">
                          {r.delete_on ? dateTimeUTC(r.delete_on) : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <TableFooter
                count={d.items.length}
                total={number(d.total)}
                noun="import runs"
              />
            </>
          )
        }
      </ApiGate>
    </Panel>
  );
}

// ---- pipeline runs

function RunsTab({
  open,
  filters,
}: {
  open: Props["open"];
  filters: Props["filters"];
}) {
  const scope = scopeFromQuery(filters);
  const state = useApi<Paged<PipelineRunOut>>("runs", {
    site: scope.site || undefined,
    limit: 50,
    offset: 0,
  });
  return (
    <Panel title="Pipeline runs" label="Observed">
      <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
        {(d) =>
          d.items.length === 0 ? (
            <NoData title="No pipeline runs">No run was recorded yet.</NoData>
          ) : (
            <>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Run</th>
                      <th>Lane</th>
                      <th>Started</th>
                      <th>Duration</th>
                      <th>Status</th>
                      <th>Failed step</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.items.map((r) => (
                      <tr key={r.id}>
                        <td>
                          <TextLink
                            className="mono"
                            onClick={() => open("run", r.id)}
                          >
                            {r.id.slice(0, 8)}
                          </TextLink>
                        </td>
                        <td>{laneName(r.lane)}</td>
                        <td className="mono">{dateTimeUTC(r.started_at)}</td>
                        <td className="mono">
                          {durationText(r.duration_seconds)}
                        </td>
                        <td>
                          <Status value={statusLabel(r.status)} />
                        </td>
                        <td className={r.failed_step ? "negative" : "muted"}>
                          {r.failed_step ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <TableFooter
                count={d.items.length}
                total={number(d.page.total)}
                noun="pipeline runs"
              />
            </>
          )
        }
      </ApiGate>
    </Panel>
  );
}

// ---- health

function HealthTab({
  state,
  lanes,
  alerts,
}: {
  state: { data: Health | null; error: ApiError | null; reload: () => void };
  lanes: Health["lanes"];
  alerts: Health["alerts"];
}) {
  return (
    <ApiGate
      state={{ ...state, loading: false }}
      skeleton={<LoadingState rows={3} />}
    >
      {() => (
        <>
          <Panel title="Health" label="Observed">
            {lanes.length === 0 ? (
              <NoData title="No lane reported">
                The API reported no lane for this site.
              </NoData>
            ) : (
              <div className="health-rows">
                {lanes.map((l) => (
                  <div key={`${l.site_id}-${l.lane}`}>
                    {l.healthy ? (
                      <Check size={16} />
                    ) : (
                      <CircleAlert size={16} />
                    )}
                    <strong>
                      {laneName(l.lane)} lane · {l.site_id}
                    </strong>
                    <span>
                      {l.last_success
                        ? `Last complete · ${dateTimeUTC(l.last_success)}`
                        : "No complete run yet"}
                    </span>
                    <Status value={l.healthy ? "Healthy" : "Late"} />
                  </div>
                ))}
              </div>
            )}
          </Panel>
          <Panel
            title="Alerts"
            action={
              <span className={alerts.length ? "amber-text" : "muted"}>
                {alerts.length} open
              </span>
            }
          >
            {alerts.length === 0 ? (
              <NoData title="No open alerts" />
            ) : (
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Raised</th>
                      <th>Alert</th>
                      <th>Site</th>
                      <th>State</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((a) => (
                      <tr key={a.id}>
                        <td className="mono">{dateTimeUTC(a.raised_at)}</td>
                        <td>
                          <span className="amber-text">{a.message}</span>
                          <div className="table-subline">
                            {a.kind}
                            {a.source ? ` · ${a.source}` : ""}
                          </div>
                        </td>
                        <td>{a.site_id}</td>
                        <td>
                          <Status value="Open" />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            <p className="muted table-note">
              <Gap>
                Cleared alerts are not in the API. Only open alerts show.
              </Gap>
            </p>
          </Panel>
        </>
      )}
    </ApiGate>
  );
}

// ---- settings

function SettingsTab({ filters }: { filters: Props["filters"] }) {
  const scope = scopeFromQuery(filters);
  const overview = useScopedApi<Overview>("overview", scope);
  return (
    <>
      <div className="notice compact-notice">
        <LockKeyhole size={14} />
        <span>
          Configuration is read-only. To change it, edit the files and deploy.
        </span>
      </div>
      <Panel title="Site configuration" label="Unknown">
        <div className="empty-state" role="status">
          <FileText size={24} />
          <h3>The API does not expose configuration</h3>
          <p>
            Key pages, conversion pages, journeys, access policy, thresholds,
            identity registry and CDN field maps live in files under{" "}
            <code>apps/api/config/</code> (<code>sites/</code>,{" "}
            <code>cdn/</code>, <code>registry/</code>). The dashboard cannot
            show their values or versions until an endpoint exists.
          </p>
        </div>
      </Panel>
      <Panel title="Known from the API" label="Observed">
        <ApiGate state={overview} skeleton={<LoadingState rows={2} />}>
          {(o) => (
            <dl className="config-list">
              <div>
                <dt>Site</dt>
                <dd>{o.window.site}</dd>
              </div>
              <div>
                <dt>Sources configured</dt>
                <dd>{o.coverage.sources_configured.join(", ") || "—"}</dd>
              </div>
            </dl>
          )}
        </ApiGate>
      </Panel>
    </>
  );
}
