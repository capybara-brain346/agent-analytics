import type { PageView } from "@/lib/api/types";

/** Segmented filter on the Pages tab. */
export const PAGE_PRESETS: { value: "" | PageView; label: string }[] = [
  { value: "", label: "All pages" },
  { value: "agent_heavy", label: "Agent-heavy" },
  { value: "errors", label: "Errors" },
  { value: "blocks", label: "Blocks" },
  { value: "retries", label: "Retries" },
  { value: "never_reached", label: "Key pages never reached" },
];

/** A rate at or above this value is a failure mark. Any rate above zero is a warning mark. */
export const BLOCK_RATE_FAIL_PCT = 10;
export const ERROR_RATE_FAIL_PCT = 10;

export const UNKNOWN_TITLE = "Unknown: no requests in this window";

/** Journey step bars: a step that keeps less than this share of the step before it is a warning. */
export const JOURNEY_DROP_WARN_RATIO = 0.5;
