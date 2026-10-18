import { useState } from "react";
import Link from "next/link";
import type { ApiError } from "@/lib/api/client";
import type { Health } from "@/lib/api/types";
import { timeUTC } from "@/lib/format";
import type { Href } from "../../shared";
import { LIVE_WINDOW_MINUTES } from "./config";
import { ageParts, laneName, sourceName } from "./format";

type Lane = Health["lanes"][number];

/** live: healthy and recent. stale: healthy but old. late: the API reports it unhealthy. */
function laneState(lane: Lane, now: number) {
  if (!lane.healthy) return "late";
  if (!lane.last_success) return "stale";
  const minutes = (now - new Date(lane.last_success).getTime()) / 60000;
  return minutes <= LIVE_WINDOW_MINUTES ? "live" : "stale";
}

const STATE_WORD = { live: "Healthy", stale: "No recent run", late: "Late" };

function LaneCell({
  lane,
  now,
  showSite,
}: {
  lane: Lane;
  now: number;
  showSite: boolean;
}) {
  const state = laneState(lane, now);
  const [value, unit] = lane.last_success
    ? ageParts(lane.last_success, now)
    : ["—", ""];
  return (
    <div className="metric-cell lane-cell" data-state={state}>
      <div className="metric-label">
        <span className="lane-name">
          <i className="lane-dot" />
          {laneName(lane.lane)} lane
        </span>
        <span className="lane-state">{STATE_WORD[state]}</span>
      </div>
      <strong>{value}</strong>
      <div className="metric-bottom">
        {lane.last_success
          ? `${unit} since last complete run · ${timeUTC(lane.last_success)} UTC`
          : "No complete run yet"}
        {showSite && ` · ${lane.site_id}`}
      </div>
    </div>
  );
}

export function LaneStrip({
  href,
  tab,
  health,
  error,
  loading,
  lanes,
  alerts,
}: {
  href: Href;
  tab: string;
  health: Health | null;
  error: ApiError | null;
  loading: boolean;
  lanes: Health["lanes"];
  alerts: Health["alerts"];
}) {
  const [now] = useState(() => Date.now());

  if (error)
    return (
      <div className="metrics-strip lane-strip">
        <div className="metric-cell lane-cell" data-state="late">
          <div className="metric-label">
            <span className="lane-name">
              <i className="lane-dot" />
              Pipeline health
            </span>
            <span className="lane-state">Unknown</span>
          </div>
          <strong>—</strong>
          <div className="metric-bottom">{error.message}</div>
        </div>
      </div>
    );

  if (loading || !health)
    return (
      <div className="metrics-strip lane-strip">
        <div className="metric-cell lane-cell" data-state="idle">
          <div className="metric-label">
            <span className="lane-name">
              <i className="lane-dot" />
              Pipeline health
            </span>
          </div>
          <strong>—</strong>
          <div className="metric-bottom">Checking health</div>
        </div>
      </div>
    );

  const sources = [...new Set(alerts.map((a) => a.source).filter(Boolean))];
  const alertCell = (
    <>
      <div className="metric-label">
        <span className="lane-name">
          <i className="lane-dot" />
          Open alerts
        </span>
        <span className="lane-state">
          {alerts.length ? "Needs review" : "None"}
        </span>
      </div>
      <strong>{alerts.length}</strong>
      <div className="metric-bottom">
        {alerts.length
          ? `No new logs · ${sources.map((s) => sourceName(s as string)).join(", ") || alerts[0].site_id}`
          : "Nothing needs attention"}
      </div>
    </>
  );

  return (
    <div className="metrics-strip lane-strip">
      {lanes.map((l) => (
        <LaneCell
          key={`${l.site_id}-${l.lane}`}
          lane={l}
          now={now}
          showSite={new Set(lanes.map((x) => x.site_id)).size > 1}
        />
      ))}
      {alerts.length > 0 && tab !== "health" ? (
        <Link
          className="metric-cell lane-cell lane-link"
          data-state="stale"
          href={href("/data", { tab: "health" })}
          scroll={false}
        >
          {alertCell}
        </Link>
      ) : (
        <div
          className="metric-cell lane-cell"
          data-state={alerts.length ? "stale" : "idle"}
        >
          {alertCell}
        </div>
      )}
    </div>
  );
}
