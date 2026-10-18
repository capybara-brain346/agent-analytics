"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { ChevronRight, Info } from "lucide-react";
import { useApi } from "@/lib/api/use-api";
import type { Label as LabelType, RecommendationDetail } from "@/lib/api/types";
import { capitalize, number, windowCaption } from "@/lib/format";
import { ApiGate, Gap, LoadingState } from "../shared";
import { ChangePill, ConfidenceMark } from "../sections/recommendations/status";
import { DetailSection, Fields, DetailProps } from "./common";

const labelName = (l: LabelType) => capitalize(l);
const MAX_LINKS = 50;
const PREVIEW_LINKS = 5;
const FACTORS = ["impact", "frequency", "severity", "confidence"] as const;

export function RecommendationDetailView({ id, href, open }: DetailProps) {
  const site = useSearchParams().get("site") ?? "";
  const state = useApi<RecommendationDetail>(`recommendations/${id}`, { site });
  return (
    <ApiGate state={state} skeleton={<LoadingState rows={8} />}>
      {(r) => <Body r={r} open={open} href={href} />}
    </ApiGate>
  );
}

function LinkRow({
  id,
  kind,
  onClick,
}: {
  id: string;
  kind: string;
  onClick: () => void;
}) {
  return (
    <button onClick={onClick}>
      <code>{id}</code>
      <span>{kind}</span>
      <ChevronRight size={14} />
    </button>
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
  const [showAll, setShowAll] = useState(false);
  const links = [
    ...sessionIds.map((sid) => ({
      key: `s-${sid}`,
      id: sid,
      kind: "Session",
      go: () => open("session", sid),
    })),
    ...eventIds.map((eid) => ({
      key: `e-${eid}`,
      id: `#${eid}`,
      kind: "Request",
      go: () => open("event", String(eid)),
    })),
  ];
  const shownLinks = showAll ? links : links.slice(0, PREVIEW_LINKS);
  const truncated =
    evidence.session_ids.length > MAX_LINKS ||
    evidence.event_ids.length > MAX_LINKS;
  return (
    <div className="rec-detail">
      <header className="rec-detail-head">
        <div className="rec-detail-pills">
          <ChangePill change={r.change} />
          <ConfidenceMark value={r.confidence} />
        </div>
        <h3>{r.recommended_test ?? r.target}</h3>
        <span className="rec-detail-meta">
          {r.pattern_name} · run #{r.run.id}
        </span>
      </header>
      {r.change === "gone" && (
        <div className="rec-detail-note">
          <Info size={14} />
          Absent in run #{r.run_id}. The evidence is from the last run that had
          it. Gone does not prove that the issue is fixed.
        </div>
      )}
      <Fields
        items={[
          ["Priority", <strong key="p">{priority.score}</strong>],
          ["Formula", <code key="f">{priority.formula}</code>],
          [
            "Evidence",
            `${number(evidence.sessions_count)} ${evidence.sessions_count === 1 ? "session" : "sessions"} · ${number(evidence.events_count)} ${evidence.events_count === 1 ? "request" : "requests"}`,
          ],
          ["Window", windowCaption(r.run.window_start, r.run.window_end)],
          [
            "History",
            `First seen in run #${r.first_seen_run_id}${
              runs.length > 1
                ? ` · runs ${runs.map((n) => `#${n}`).join(", ")}`
                : ""
            }`,
          ],
        ]}
      />
      <DetailSection title="Priority factors" label="Inferred">
        <dl className="rec-factors">
          {FACTORS.map((k) => (
            <div key={k}>
              <dt>{capitalize(k)}</dt>
              <dd className="rec-factor-value">{priority.factors[k].value}</dd>
              <dd className="rec-factor-why">
                {priority.factors[k].why ?? <Gap>No reason stored.</Gap>}
              </dd>
            </div>
          ))}
        </dl>
      </DetailSection>
      <DetailSection title="Why test this" label={labelName(r.reason.label)}>
        <p>{r.reason.text ?? <Gap>No text stored.</Gap>}</p>
      </DetailSection>
      <DetailSection
        title="Potential issue"
        label={labelName(r.potential_issue.label)}
      >
        <p>{r.potential_issue.text ?? <Gap>No text stored.</Gap>}</p>
      </DetailSection>
      <DetailSection
        title="Suggested validation"
        label={labelName(r.suggested_validation.label)}
      >
        <p>{r.suggested_validation.text ?? <Gap>No text stored.</Gap>}</p>
      </DetailSection>
      <DetailSection
        title="Evidence to inspect"
        label={labelName(evidence.label)}
      >
        {sessionIds.length || eventIds.length ? (
          <div className="rec-links">
            {shownLinks.map((l) => (
              <LinkRow key={l.key} id={l.id} kind={l.kind} onClick={l.go} />
            ))}
          </div>
        ) : (
          <Gap>This recommendation stores no evidence references.</Gap>
        )}
        {!showAll && links.length > PREVIEW_LINKS && (
          <button
            className="btn-standard rec-links-more"
            onClick={() => setShowAll(true)}
          >
            Show all {links.length}
          </button>
        )}
        {truncated && (
          <span className="rec-detail-meta">
            Showing the first {MAX_LINKS} of each.
          </span>
        )}
      </DetailSection>
      {r.related.length > 0 && (
        <DetailSection title="Related">
          <div className="rec-links">
            {r.related.map((x) => (
              <LinkRow
                key={x.id}
                id={x.target}
                kind={`${x.pattern_name} · ${x.score}`}
                onClick={() => open("recommendation", String(x.id))}
              />
            ))}
          </div>
        </DetailSection>
      )}
      <DetailSection
        title="Suggested next step"
        label={labelName(r.next_action.label)}
      >
        <div className="rec-next">
          {r.next_action.text ?? <Gap>No text stored.</Gap>}
        </div>
      </DetailSection>
      <details className="rec-bundle">
        <summary>
          <ChevronRight size={13} />
          Fact bundle
        </summary>
        {bundle.length ? (
          <Fields
            items={bundle.map(([k, v]) => [
              k,
              typeof v === "string" || typeof v === "number" ? (
                String(v)
              ) : (
                <code key={k} className="rec-bundle-json">
                  {JSON.stringify(v, null, 1)}
                </code>
              ),
            ])}
          />
        ) : (
          <Gap>No fact bundle stored.</Gap>
        )}
      </details>
      <footer className="rec-detail-foot">
        <span>{r.text_source_note}</span>
        <span>
          Rule v{r.run.rule_version ?? "?"} · prompt{" "}
          {r.prompt_version ? `v${r.prompt_version}` : "none"}
          {r.model ? ` · ${r.model}` : ""}
        </span>
      </footer>
    </div>
  );
}
