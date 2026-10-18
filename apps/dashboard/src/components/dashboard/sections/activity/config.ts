import type { Verdict } from "@/lib/api/types";

export const PAGE_SIZE = 50;

export const SESSION_ID_CHARS = 8;

const sourceNames: Record<string, string> = {
  cdn: "CDN",
  origin: "Origin",
  paired: "Paired",
};

export const sourceLabel = (s: string) =>
  sourceNames[s.toLowerCase()] ??
  s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();

export type Tone = "green" | "amber" | "red" | "neutral";

// Old and short URL values -> what the API accepts.
export const statusParam = (v: string) =>
  v === "denied" ? "403,429" : v === "errors" ? "4xx,5xx" : v;

export const stateParam = (v: string) =>
  v.toLowerCase().replace(/\s+/g, "_") === "in_progress"
    ? "in_progress"
    : v.toLowerCase() === "closed"
      ? "closed"
      : "";

type Query = Record<string, string | number | boolean | undefined>;

export const clean = (q: Query): Query =>
  Object.fromEntries(
    Object.entries(q).filter(([, v]) => v !== "" && v !== undefined),
  );

const httpWords: Record<number, string> = {
  200: "OK",
  201: "Created",
  204: "No content",
  301: "Moved",
  302: "Redirect",
  304: "Not modified",
  400: "Bad request",
  401: "Unauthorized",
  403: "Forbidden",
  404: "Not found",
  429: "Rate limited",
  500: "Server error",
  502: "Bad gateway",
  503: "Unavailable",
};

const httpFallback = ["Success", "Redirect", "Client error", "Server error"];

export const httpWord = (code: number) =>
  httpWords[code] ?? httpFallback[Math.floor(code / 100) - 2] ?? "Response";

export const httpTone = (code: number): Tone =>
  code >= 500
    ? "red"
    : code >= 400
      ? "amber"
      : code >= 200 && code < 300
        ? "green"
        : "neutral";

export const verdictView: Record<Verdict, { word: string; tone: Tone }> = {
  VERIFIED: { word: "Verified", tone: "green" },
  SPOOFED: { word: "Spoofed", tone: "red" },
  CLAIMED: { word: "Unverified", tone: "amber" },
  UNVERIFIED: { word: "Unverified", tone: "amber" },
  UNKNOWN: { word: "Unknown", tone: "neutral" },
};

// Header help text. Each column that needs a definition gets one tooltip.
export const columnHelp = {
  status:
    "HTTP status the server returned. Observed in the log. It does not show whether the task was completed.",
  qualifier:
    "Traffic class assigned by the classifier. Inferred from the verdict, user agent and edge signals.",
  agent:
    "Agent name the request claims. The pill shows whether the registry check confirmed it.",
  confidence: "How strongly the evidence supports the traffic class.",
  requests: "Requests in the session. Opens the matching events.",
  sessionState:
    "In progress means a request arrived recently. Sessions group requests by client and time gap.",
};
