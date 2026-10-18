import type { Params } from "./client";

// The global filters live in the URL: ?site=&range=&class=  (rule R8).
// This file maps them to API query parameters: site, from, to, class.

export const ranges: Record<
  string,
  { hours: number; label: string; compare: string; bucket: "hour" | "day" }
> = {
  "1h": {
    hours: 1,
    label: "Last 1 hour",
    compare: "previous hour",
    bucket: "hour",
  },
  "6h": {
    hours: 6,
    label: "Last 6 hours",
    compare: "previous 6 hours",
    bucket: "hour",
  },
  "24h": {
    hours: 24,
    label: "Last 24 hours",
    compare: "previous 24h",
    bucket: "hour",
  },
  "7d": {
    hours: 168,
    label: "Last 7 days",
    compare: "previous 7 days",
    bucket: "day",
  },
};
export const defaultRange = "24h";
export const rangeOf = (range: string) => ranges[range] ?? ranges[defaultRange];

export type Scope = {
  /** Site id from the URL. Empty: the API picks the only site. */
  site: string;
  /** A key of `ranges`. */
  range: string;
  /** Comma list of class numbers, for example "1,2,3,4". Empty: all classes. */
  classes: string;
};

export function scopeFromQuery(query: {
  get: (key: string) => string | null;
}): Scope {
  const range = query.get("range") ?? "";
  return {
    site: query.get("site") ?? "",
    range: range in ranges ? range : defaultRange,
    classes: query.get("class") ?? "",
  };
}

/** The API parameters site, from, to, class. `from` and `to` follow `now`, so call this at fetch time. */
export function scopeParams(scope: Scope, now = new Date()): Params {
  const to = now;
  const from = new Date(to.getTime() - rangeOf(scope.range).hours * 3_600_000);
  return {
    site: scope.site || undefined,
    from: from.toISOString(),
    to: to.toISOString(),
    class: scope.classes ? scope.classes.split(",") : undefined,
  };
}
