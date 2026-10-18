import type { Verdict } from "@/lib/api/types";
import { Tip } from "../../shared";
import { httpTone, httpWord, verdictView, type Tone } from "./config";

export function Pill({
  tone,
  children,
}: {
  tone: Tone;
  children: React.ReactNode;
}) {
  return (
    <span className={`status ${tone}`}>
      <span className="status-dot" />
      {children}
    </span>
  );
}

export function HttpPill({ code }: { code: number | null }) {
  if (code === null) return <Pill tone="neutral">Unknown</Pill>;

  return (
    <Pill tone={httpTone(code)}>
      <span className="http-num">{code}</span>
      <span className="http-word">{httpWord(code)}</span>
    </Pill>
  );
}

export function VerdictPill({ verdict }: { verdict: Verdict | null }) {
  const view = verdictView[verdict ?? "UNKNOWN"];

  return <Pill tone={view.tone}>{view.word}</Pill>;
}

export function Head({
  children,
  help,
  col,
  right,
}: {
  children?: React.ReactNode;
  help?: string;
  col?: string;
  right?: boolean;
}) {
  return (
    <th data-col={col} data-right={right ? "" : undefined}>
      {children}
      {help && <Tip text={help} />}
    </th>
  );
}
