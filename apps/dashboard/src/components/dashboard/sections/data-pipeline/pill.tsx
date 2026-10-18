import { statusLabel } from "./format";

const TONE: Record<string, string> = {
  success: "green",
  failed: "red",
  running: "green running",
  importing: "green running",
  new: "neutral",
  stale: "amber",
  none: "neutral",
};

/** Status pill: tint and 6px dot. Running and importing pulse, nothing else does. */
export function StatusPill({
  status,
  label,
}: {
  status: string;
  label?: string;
}) {
  return (
    <span className={`status ${TONE[status] ?? "neutral"}`}>
      <span className="status-dot" />
      {label ?? statusLabel(status)}
    </span>
  );
}

/** Tier word with its 7px square. */
export function Qualifier({
  tone,
  title,
  children,
}: {
  tone?: "pass" | "warn" | "fail";
  title?: string;
  children: React.ReactNode;
}) {
  return (
    <span className={`qualifier ${tone ?? ""}`} title={title}>
      <i />
      {children}
    </span>
  );
}
