import Link from "next/link";
import type { ApiState } from "@/lib/api/use-api";
import type { Overview } from "@/lib/api/types";
import { capitalize } from "@/lib/format";
import { sourceName } from "./format";
import { ApiGate, Gap, LoadingState, Panel, Tip } from "../../shared";
import type { Props } from "../common";
import { Qualifier } from "./pill";

const GAP_HELP = "Gaps listed by the API for the current window.";

export function SourcePanels({
  href,
  overview,
}: {
  href: Props["href"];
  overview: ApiState<Overview>;
}) {
  return (
    <div className="two-column equal-columns">
      <Panel
        title="Source coverage"
        action={
          <Link
            className="text-link"
            href={href("/events", { source: "Paired" })}
          >
            Paired requests →
          </Link>
        }
      >
        <ApiGate state={overview} skeleton={<LoadingState rows={2} />}>
          {({ coverage }) => (
            <div className="coverage">
              <div className="coverage-figure">
                {coverage.paired_share_pct === null ? (
                  <Gap>Pairing is not measured: no paired source present.</Gap>
                ) : (
                  <>
                    <strong>{coverage.paired_share_pct.toFixed(1)}%</strong>
                    <span>Origin requests paired with a CDN request</span>
                  </>
                )}
              </div>
              <ul className="square-rows">
                {coverage.sources_configured.map((s) => {
                  const present = coverage.sources_present.includes(s);
                  return (
                    <li key={s}>
                      <Qualifier tone={present ? "pass" : "warn"}>
                        {sourceName(s)}
                      </Qualifier>
                      <span>
                        {present
                          ? "Present in the window"
                          : "Not in the window"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            </div>
          )}
        </ApiGate>
      </Panel>
      <Panel title="Current data gaps" action={<Tip text={GAP_HELP} />}>
        <ApiGate state={overview} skeleton={<LoadingState rows={2} />}>
          {({ coverage }) => {
            const count = coverage.cannot_see.length + coverage.partial.length;
            if (!count)
              return <div className="empty-state">No data gaps reported.</div>;
            return (
              <ul className="square-rows gaps">
                {coverage.cannot_see.map((g) => (
                  <li key={`c-${g}`}>
                    <Qualifier>{capitalize(g)}</Qualifier>
                    <span>Cannot see</span>
                  </li>
                ))}
                {coverage.partial.map((g) => (
                  <li key={`p-${g}`}>
                    <Qualifier tone="warn">{capitalize(g)}</Qualifier>
                    <span>Partial</span>
                  </li>
                ))}
              </ul>
            );
          }}
        </ApiGate>
      </Panel>
    </div>
  );
}
