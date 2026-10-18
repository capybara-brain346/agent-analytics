import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { SessionRow } from "@/lib/api/types";
import {
  capitalize,
  dateTimeUTC,
  dateUTC,
  timeUTC,
  number,
} from "@/lib/format";
import { ClassName, Confidence } from "../../shared";
import type { Props } from "../common";
import { Head, Pill } from "./cells";
import { SESSION_ID_CHARS, columnHelp } from "./config";

const stop = (e: React.SyntheticEvent) => e.stopPropagation();

export function SessionsTable({
  rows,
  open,
  href,
}: {
  rows: SessionRow[];
  open: Props["open"];
  href: Props["href"];
}) {
  return (
    <div className="table-scroll">
      <table className="activity-table" aria-label="Sessions">
        <thead>
          <tr>
            <Head>Session</Head>
            <Head help={columnHelp.sessionState}>State</Head>
            <Head right help={columnHelp.requests}>
              Requests
            </Head>
            <Head col="qualifier" help={columnHelp.qualifier}>
              Traffic class
            </Head>
            <Head col="confidence" help={columnHelp.confidence}>
              Confidence
            </Head>
            <Head right>Started</Head>
            <Head col="chev" />
          </tr>
        </thead>

        <tbody>
          {rows.map((s) => (
            <tr
              key={s.session_id}
              onClick={() => open("session", s.session_id)}
            >
              <td className="identity">
                <button className="identity-main" title={s.session_id}>
                  {s.session_id.slice(0, SESSION_ID_CHARS)}
                </button>
                <span className="table-subline">
                  {[
                    s.agent ?? "No agent name",
                    `${number(s.distinct_pages)} ${s.distinct_pages === 1 ? "page" : "pages"}`,
                    s.has_retry && "retry",
                    s.has_loop && "loop",
                    s.reached_conversion && "conversion",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
              </td>

              <td>
                <Pill tone={s.in_progress ? "green" : "neutral"}>
                  {s.in_progress ? "In progress" : "Closed"}
                </Pill>
              </td>

              <td className="figure" data-right>
                <Link
                  className="number-link"
                  href={href("/events", { session: s.session_id })}
                  onClick={stop}
                >
                  {number(s.requests)}
                </Link>
              </td>

              <td data-col="qualifier">
                {s.traffic_class ? (
                  <ClassName id={s.traffic_class} />
                ) : (
                  <span className="muted">Unclassified</span>
                )}
              </td>

              <td data-col="confidence">
                {s.confidence ? (
                  <Confidence value={capitalize(s.confidence)} />
                ) : (
                  <span className="muted">—</span>
                )}
              </td>

              <td
                className="time"
                data-right
                title={`${dateTimeUTC(s.started)} UTC`}
              >
                <span className="time-date">{dateUTC(s.started)}, </span>
                {timeUTC(s.started)}
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
