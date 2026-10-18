// Sample log files: <site>__<source>__<YYYYMMDDTHHMMZ>[__<label>].log[.gz]
// (samples/logs/README.md). The CLI reads the same rule
// (apps/api/src/services/importer/log_names.py). The API checks site and source.
const LOG_NAME =
  /^([A-Za-z0-9-]+(?:_[A-Za-z0-9-]+)*)__([a-z]+)__(\d{8}T\d{4}Z)(?:__([A-Za-z0-9._-]+?))?\.log(?:\.gz)?$/;

export type LogName = {
  site: string;
  source: string;
  /** ISO time from the name, for example 2026-10-01T00:00:00Z. */
  start: string;
  label: string | null;
};

/** Null: the name does not follow the rule. */
export function parseLogName(name: string): LogName | null {
  const m = LOG_NAME.exec(name);
  if (!m) return null;
  const t = m[3];
  const start = `${t.slice(0, 4)}-${t.slice(4, 6)}-${t.slice(6, 8)}T${t.slice(9, 11)}:${t.slice(11, 13)}:00Z`;
  return { site: m[1], source: m[2], start, label: m[4] ?? null };
}
