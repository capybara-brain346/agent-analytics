import { number } from "@/lib/format";

/** Status words of the API, in the words the console shows. */
export function statusLabel(status: string) {
  switch (status) {
    case "success":
      return "Complete";
    case "failed":
      return "Failed";
    case "running":
      return "Running";
    case "importing":
      return "Importing";
    case "new":
      return "Queued";
    default:
      return status.charAt(0).toUpperCase() + status.slice(1);
  }
}

/** Filter group of one API status, see STATUS_FILTERS. */
export function statusGroup(status: string) {
  if (status === "success") return "done";
  if (status === "failed") return "failed";
  return "active";
}

export const laneName = (lane: string) => (lane === "fast" ? "Fast" : "Slow");

export function durationText(seconds: number | null) {
  if (seconds === null) return "—";
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`;
  if (seconds < 120) return `${seconds.toFixed(1)} s`;
  return `${Math.round(seconds / 60)} min`;
}

/** Non-zero counters of one pipeline step as [label, value]. Values that are not numbers are left out. */
export function countEntries(value: unknown): [string, string][] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => typeof v === "number" && v !== 0)
    .map(([k, v]) => [sentence(k), number(v as number)]);
}

function sentence(key: string) {
  const text = key.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const stepName = (step: string) => {
  const text = step.replaceAll("_", " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
};

/** Human name of a raw source value, "cdn" becomes "CDN". */
export function sourceName(source: string) {
  if (source.toLowerCase() === "cdn") return "CDN";
  if (source.toLowerCase() === "origin") return "Origin";
  return source;
}

export function sourceLabel(source: string) {
  if (source.toUpperCase() === "CDN") return "CDN log";
  if (source === "origin") return "Origin log";
  return source;
}

/** Short sentence for an alert row. The full text stays in the tooltip. */
export function alertSentence(
  kind: string,
  source: string | null,
  message: string,
) {
  const where = source ? ` from ${sourceName(source)}` : "";
  if (kind === "no_data") {
    const minutes = /for (\d+) minutes/.exec(message)?.[1];
    return `No new logs${where}${minutes ? ` for ${minutes} min` : ""}`;
  }
  const text = kind.replaceAll("_", " ");
  return `${text.charAt(0).toUpperCase()}${text.slice(1)}${where}`;
}

/** The time a message names, "last file at 2026-10-17T12:34:01+00:00". */
export const alertLastFile = (message: string) =>
  /last file at (\S+?)\)/.exec(message)?.[1] ?? null;

/** Whole minutes or hours since an ISO time, split into figure and unit. */
export function ageParts(iso: string, now: number): [string, string] {
  const minutes = Math.max(
    0,
    Math.round((now - new Date(iso).getTime()) / 60000),
  );
  if (minutes < 120)
    return [String(minutes), minutes === 1 ? "minute" : "minutes"];
  const hours = Math.round(minutes / 60);
  if (hours < 48) return [String(hours), "hours"];
  return [String(Math.round(hours / 24)), "days"];
}
