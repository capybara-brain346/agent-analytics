import type { PageRow } from "@/lib/api/types";
import { BLOCK_RATE_FAIL_PCT, ERROR_RATE_FAIL_PCT } from "./config";

export type Tone = "pass" | "warn" | "fail" | "neutral";

export type PageHealth = {
  label: string;
  pill: "green" | "amber" | "red" | "neutral";
};

/** One word for the row, taken from fields the API already returns. */
export function pageHealth(p: PageRow): PageHealth {
  if (p.agent_requests === 0) return { label: "Not reached", pill: "neutral" };
  if ((p.block_rate_pct ?? 0) >= BLOCK_RATE_FAIL_PCT)
    return { label: "Blocked", pill: "red" };
  if ((p.error_rate_pct ?? 0) >= ERROR_RATE_FAIL_PCT)
    return { label: "Errors", pill: "amber" };
  if (p.retries > 0) return { label: "Retries", pill: "amber" };
  return { label: "Healthy", pill: "green" };
}

export function rateTone(pct: number, failAt: number): Tone {
  if (pct >= failAt) return "fail";
  return pct > 0 ? "warn" : "neutral";
}

export const errorTone = (pct: number) => rateTone(pct, ERROR_RATE_FAIL_PCT);
export const blockTone = (pct: number) => rateTone(pct, BLOCK_RATE_FAIL_PCT);

export const plural = (n: number, one: string, many: string) =>
  n === 1 ? one : many;
