"use client";

import { useSearchParams } from "next/navigation";
import { ChevronRight, Info } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import type { Label as LabelType, RecommendationDetail } from "@/lib/api/types";
import { capitalize, number, windowCaption } from "@/lib/format";
import { ApiGate, Gap, LoadingState, Status } from "../shared";
import { DetailSection, Fields, DetailProps } from "./common";

const labelName = (l: LabelType) => capitalize(l);
const changeLabel = (c: string | null) =>
  c === "new"
    ? "New"
    : c === "open"
      ? "Still open"
      : c === "gone"
        ? "Gone"
        : "";
const MAX_LINKS = 50;

export function RecommendationDetailView({ id, href, open }: DetailProps) {
  const site = useSearchParams().get("site") ?? "";
  const state = useApi<RecommendationDetail>(`recommendations/${id}`, { site });
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={8} />}>
      {(r) => <Body r={r} open={open} href={href} />}
    </ApiGate>
  );
}

function Body({
  r,
  open,
}: {
  r: RecommendationDetail;
  open: DetailProps["open"];
  href: DetailProps["href"];
}) {
  const { evidence, priority } = r;
  const sessionIds = evidence.session_ids.slice(0, MAX_LINKS);
  const eventIds = evidence.event_ids.slice(0, MAX_LINKS);
  const runs = r.history.map((h) => h.run_id);
  const bundle = Object.entries(r.fact_bundle);
  return (
    <>
      <div className="detail-chips">
        {r.change && <Status value={changeLabel(r.change)} />}
        <span className="pattern-badge">{r.pattern_name}</span>
        <span className="muted">
          Run #{r.run.id} ·{" "}
          {windowCaption(r.run.window_start, r.run.window_end)}
        </span>
      </div>
      {r.change === "gone" && (
        <div className="detail-notice">
          <Info size={14} />
          <p>
            This pattern was absent in run #{r.run_id}. The evidence is from the
            last run that had it. Gone does not prove that the issue is fixed.
          </p>
        </div>
      )}
      <div className="target-path">
        <span>Recommended test</span>
        <code>{r.recommended_test ?? r.target}</code>
      </div>
      <DetailSection title="Why test this" label={labelName(r.reason.label)}>
        <p className="detail-why">
          {r.reason.text ?? <Gap>No text stored.</Gap>}
        </p>
      </DetailSection>
      <DetailSection
        title="Potential issue"
        label={labelName(r.potential_issue.label)}
      >
        <p>{r.potential_issue.text ?? <Gap>No text stored.</Gap>}</p>
      </DetailSection>
      <DetailSection
        title="Evidence to inspect"
        label={labelName(evidence.label)}
      >
        <p className="muted">
          Run #{r.run_id} has {number(evidence.sessions_count)} matching
          sessions and {number(evidence.events_count)} requests.
          {evidence.session_ids.length < evidence.sessions_count ||
          evidence.event_ids.length < evidence.events_count
            ? ` The API keeps ${number(evidence.session_ids.length)} session IDs and ${number(evidence.event_ids.length)} request IDs as references.`
            : ""}
        </p>
        <div className="detail-link-list">
          {sessionIds.map((sid) => (
            <button key={`s-${sid}`} onClick={() => open("session", sid)}>
              <code>{sid}</code>
              <span>Session</span>
              <ChevronRight size={14} />
            </button>
          ))}
          {eventIds.map((eid) => (
            <button key={`e-${eid}`} onClick={() => open("event", String(eid))}>
              <code>#{eid}</code>
              <span>Request</span>
              <ChevronRight size={14} />
            </button>
          ))}
        </div>
        {(evidence.session_ids.length > MAX_LINKS ||
          evidence.event_ids.length > MAX_LINKS) && (
          <p className="muted">Showing the first {MAX_LINKS} of each.</p>
        )}
        {!sessionIds.length && !eventIds.length && (
          <Gap>This recommendation stores no evidence references.</Gap>
        )}
      </DetailSection>
      <DetailSection
        title="Suggested validation"
        label={labelName(r.suggested_validation.label)}
      >
        <p>{r.suggested_validation.text ?? <Gap>No text stored.</Gap>}</p>
      </DetailSection>
      <DetailSection title="Priority" label="Inferred">
        <div className="priority-formula">
          <strong>{priority.score}</strong>
          <span>=</span>
          {(["impact", "frequency", "severity", "confidence"] as const).map(
            (k, i) => (
              <span key={k} style={{ display: "contents" }}>
                {i > 0 && <span>×</span>}
                <span>
                  {priority.factors[k].value}
                  <small>{capitalize(k)}</small>
                </span>
              </span>
            ),
          )}
        </div>
        <Fields
          items={(
            ["impact", "frequency", "severity", "confidence"] as const
          ).map((k) => [
            `${capitalize(k)} · ${priority.factors[k].value}`,
            priority.factors[k].why ?? <Gap>No reason stored.</Gap>,
          ])}
        />
        <p className="muted">
          <code>{priority.formula}</code> · {capitalize(r.confidence)}{" "}
          confidence
        </p>
      </DetailSection>
      <div className="outcome-panel">
        <h3>
          Suggested next step <Gap>{labelName(r.next_action.label)}</Gap>
        </h3>
        <p>{r.next_action.text ?? "No text stored."}</p>
      </div>
      <details className="fact-bundle">
        <summary>
          <ChevronRight size={13} />
          Inspect the fact bundle
        </summary>
        {bundle.length ? (
          <Fields
            items={bundle.map(([k, v]) => [
              k,
              typeof v === "string" || typeof v === "number" ? (
                String(v)
              ) : (
                <code key={k} style={{ whiteSpace: "pre-wrap" }}>
                  {JSON.stringify(v, null, 1)}
                </code>
              ),
            ])}
          />
        ) : (
          <Gap>No fact bundle stored.</Gap>
        )}
      </details>
      <DetailSection title="History">
        <p className="muted">
          First seen in run #{r.first_seen_run_id}
          {runs.length > 1
            ? ` · in runs ${runs.map((n) => `#${n}`).join(", ")}`
            : ""}
          . The stored evidence stays linked to its run.
        </p>
      </DetailSection>
      {r.related.length > 0 && (
        <DetailSection title="Related">
          <div className="detail-link-list">
            {r.related.map((x) => (
              <button
                key={x.id}
                onClick={() => open("recommendation", String(x.id))}
              >
                <code>{x.target}</code>
                <span>
                  {x.pattern_name} · priority {x.score}
                </span>
                <ChevronRight size={14} />
              </button>
            ))}
          </div>
        </DetailSection>
      )}
      <div className="detail-footer">
        <span>{r.text_source_note}</span>
        <span>
          Rule v{r.run.rule_version ?? "?"} · prompt{" "}
          {r.prompt_version ? `v${r.prompt_version}` : "none"}
          {r.model ? ` · ${r.model}` : ""}
        </span>
      </div>
    </>
  );
}
