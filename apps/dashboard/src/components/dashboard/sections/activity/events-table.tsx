import { ChevronRight } from "lucide-react";
import type { EventRow } from "@/lib/api/types";
import { capitalize, dateTimeUTC, dateUTC, timeUTC } from "@/lib/format";
import { ClassName, Confidence, TextLink } from "../../shared";
import type { Props } from "../common";
import { Head, HttpPill, VerdictPill } from "./cells";
import { SESSION_ID_CHARS, columnHelp, sourceLabel } from "./config";

const stop = (e: React.SyntheticEvent) => e.stopPropagation();

export function EventsTable({
  rows,
  open,
}: {
  rows: EventRow[];
  open: Props["open"];
}) {
  return (
    <div className="table-scroll">
      <table className="activity-table events" aria-label="Events">
        <thead>
          <tr>
            <Head>Request</Head>
            <Head help={columnHelp.status}>Status</Head>
            <Head col="qualifier" help={columnHelp.qualifier}>
              Traffic class
            </Head>
            <Head col="agent" help={columnHelp.agent}>
              Agent
            </Head>
            <Head col="confidence" help={columnHelp.confidence}>
              Confidence
            </Head>
            <Head right>Time</Head>
            <Head col="chev" />
          </tr>
        </thead>

        <tbody>
          {rows.map((e) => (
            <tr key={e.id} onClick={() => open("event", String(e.id))}>
              <td className="identity">
                <button className="identity-main" title={e.path}>
                  {e.path}
                </button>
                <span className="table-subline">
                  {[
                    e.method ?? "—",
                    sourceLabel(e.source),
                    e.session_id
                      ? e.session_id.slice(0, SESSION_ID_CHARS)
                      : "no session",
                  ].join(" · ")}
                </span>
              </td>

              <td>
                <HttpPill code={e.status} />
              </td>

              <td data-col="qualifier">
                {e.traffic_class ? (
                  <ClassName id={e.traffic_class} />
                ) : (
                  <span className="muted">Unclassified</span>
                )}
              </td>

              <td data-col="agent">
                {e.claimed_agent ? (
                  <span className="agent-cell" onClick={stop}>
                    <TextLink onClick={() => open("agent", e.claimed_agent!)}>
                      {e.claimed_agent}
                    </TextLink>
                    <VerdictPill verdict={e.verdict} />
                  </span>
                ) : (
                  <span className="agent-cell">
                    <span className="muted">No agent name</span>
                  </span>
                )}
              </td>

              <td data-col="confidence">
                {e.confidence ? (
                  <Confidence value={capitalize(e.confidence)} />
                ) : (
                  <span className="muted">—</span>
                )}
              </td>

              <td
                className="time"
                data-right
                title={`${dateTimeUTC(e.ts)} UTC`}
              >
                <span className="time-date">{dateUTC(e.ts)}, </span>
                {timeUTC(e.ts)}
              </td>

              <td data-col="chev" className="chev">
                <ChevronRight size={14} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
