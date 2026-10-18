import Link from "next/link";
import type { Overview as OverviewData } from "@/lib/api/types";
import { capitalize, dateTimeUTC, percent } from "@/lib/format";
import { Gap, Panel } from "../shared";
import type { Href } from "../shared";

const sourceName: Record<string, string> = {
  cdn: "CDN logs",
  origin: "Origin logs",
};

export function CoveragePanel({
  coverage,
  freshness,
  href,
}: {
  coverage: OverviewData["coverage"];
  freshness: OverviewData["freshness"];
  href: Href;
}) {
  return (
    <Panel title="What the data can show" className="ov-panel">
      <dl className="ov-facts">
        {coverage.sources_configured.map((source) => {
          const present =
            coverage.sources_present.includes(source) ||
            coverage.sources_present.includes("paired");

          return (
            <div key={source}>
              <dt>{sourceName[source] ?? source}</dt>
              <dd>
                <span className={`qualifier ${present ? "pass" : "warn"}`}>
                  <i />
                  {present ? "Present" : "No data"}
                </span>
              </dd>
            </div>
          );
        })}

        <div>
          <dt>Paired CDN and origin</dt>
          <dd>
            {coverage.paired_share_pct === null ? (
              <Gap>Unknown</Gap>
            ) : (
              percent(coverage.paired_share_pct, 0)
            )}
          </dd>
        </div>

        <div>
          <dt>Unknown class</dt>
          <dd>
            {coverage.unknown_share_pct === null ? (
              <Gap>No requests</Gap>
            ) : (
              <Link
                href={href("/events", { class: "6" })}
                className="ov-fact-link"
              >
                {percent(coverage.unknown_share_pct)}
              </Link>
            )}
          </dd>
        </div>

        <div>
          <dt>
            {coverage.cannot_see.length
              ? capitalize(coverage.cannot_see.join(", "))
              : "Known blind spots"}
          </dt>
          <dd>
            <span className="qualifier">
              <i />
              {coverage.cannot_see.length ? "Not in logs" : "None"}
            </span>
          </dd>
        </div>

        {coverage.partial.map((text) => (
          <div key={text}>
            <dt>{capitalize(text)}</dt>
            <dd>
              <span className="qualifier">
                <i />
                Partial
              </span>
            </dd>
          </div>
        ))}

        {freshness.state !== "ok" && (
          <div>
            <dt>Log delivery</dt>
            <dd>
              <span className="qualifier warn">
                <i />
                {freshness.last_import_at
                  ? `Last file ${dateTimeUTC(freshness.last_import_at)}`
                  : "No files"}
              </span>
            </dd>
          </div>
        )}
      </dl>
    </Panel>
  );
}
