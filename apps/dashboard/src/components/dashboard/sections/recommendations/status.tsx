import { capitalize } from "@/lib/format";

export const changeLabel = (c: string | null) =>
  c === "new"
    ? "New"
    : c === "open"
      ? "Still open"
      : c === "gone"
        ? "Gone"
        : "";

const changeTone = (c: string) => (c === "new" ? "green" : "neutral");

export function Pill({ tone, label }: { tone: string; label: string }) {
  return (
    <span className={`status ${tone}`}>
      <span className="status-dot" />
      {label}
    </span>
  );
}

export function ChangePill({ change }: { change: string | null }) {
  if (!change) return <span className="rec-none">–</span>;
  return <Pill tone={changeTone(change)} label={changeLabel(change)} />;
}

export function ConfidenceMark({ value }: { value: string }) {
  const tone =
    value === "high" ? "pass" : value === "medium" ? "warn" : "neutral";
  return (
    <span className={`qualifier ${tone}`}>
      <i />
      {capitalize(value)}
    </span>
  );
}
