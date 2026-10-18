import Link from "next/link";
import { ArrowLeft, Sparkles, X } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import type { RecommendationDetail } from "@/lib/api/types";
import { number } from "@/lib/format";
import { ApiGate, Gap, LoadingState, Panel, TextLink } from "../../shared";
import type { Props } from "../common";

// The API cannot filter by recommendation. Show the evidence it names instead.
export function RecEvidence({
  id,
  isSessions,
  open,
  href,
  onRemove,
}: {
  id: string;
  isSessions: boolean;
  open: Props["open"];
  href: Props["href"];
  onRemove: () => void;
}) {
  const state = useApi<RecommendationDetail>(
    `recommendations/${encodeURIComponent(id)}`,
  );
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={2} />}>
      {(r) => {
        const ids = isSessions
          ? r.evidence.session_ids
          : r.evidence.event_ids.map(String);
        return (
          <>
            <div className="evidence-context" role="note">
              <Sparkles size={14} />
              <span>
                <span>
                  Evidence for <strong>{r.target}</strong>
                </span>
                <small>
                  {number(r.evidence.events_count)} requests ·{" "}
                  {number(r.evidence.sessions_count)} sessions ·{" "}
                  {r.pattern_name}
                </small>
              </span>
              <Link
                className="text-link"
                href={href(`/recommendations/${r.id}`)}
              >
                <ArrowLeft size={13} />
                Back to recommendation
              </Link>
              <button
                className="icon-button"
                aria-label="Remove recommendation filter"
                onClick={onRemove}
              >
                <X size={13} />
              </button>
            </div>
            <Panel
              title={isSessions ? "Evidence sessions" : "Evidence requests"}
              label="Observed"
            >
              {ids.length ? (
                <div className="signal-tags">
                  {ids.map((x) => (
                    <TextLink
                      key={x}
                      className="mono"
                      onClick={() => open(isSessions ? "session" : "event", x)}
                    >
                      {isSessions ? x : `#${x}`}
                    </TextLink>
                  ))}
                </div>
              ) : (
                <Gap>
                  This recommendation names no{" "}
                  {isSessions ? "sessions" : "requests"}.
                </Gap>
              )}
              <div className="meta-line">
                <Gap>
                  The list API cannot filter by recommendation, so the evidence
                  IDs are listed here instead of a table.
                </Gap>
              </div>
            </Panel>
          </>
        );
      }}
    </ApiGate>
  );
}
