import type { Health, ImportFile } from "@/lib/api/types";

export type SourceRow = {
  site: string;
  source: string;
  files: number;
  lastFile: string | null;
  lastEvent: string | null;
  lastStatus: string | null;
};

/** One row per site and source, from the import files and the configured sources. */
export function sourceRows(
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

export type SourceState = {
  label: string;
  status: string;
  alert: Health["alerts"][number] | undefined;
};

/** Receiving, Stale or Failed, from the open alert and the status of the last file. */
export function sourceState(r: SourceRow, health: Health | null): SourceState {
  const alert = health?.alerts.find(
    (a) => a.site_id === r.site && a.source === r.source,
  );
  if (r.lastStatus === "failed")
    return { label: "Failed", status: "failed", alert };
  if (alert) return { label: "Stale", status: "stale", alert };
  if (!r.lastFile) return { label: "No files", status: "none", alert };
  return { label: "Receiving", status: "success", alert };
}
