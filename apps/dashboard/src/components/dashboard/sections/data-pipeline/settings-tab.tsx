import { useScopedApi } from "@/lib/api/use-api";
import { scopeFromQuery } from "@/lib/api/filters";
import type { Overview } from "@/lib/api/types";
import { ApiGate, LoadingState, Panel, Tip } from "../../shared";
import type { Props } from "../common";
import { CONFIG_PATH } from "./config";
import { sourceName } from "./format";
import { StatusPill } from "./pill";

const HELP =
  "Key pages, conversion pages, journeys, access policy, thresholds, identity registry and CDN field maps are not exposed by the API. To change them, edit the files and deploy.";

export function SettingsTab({ filters }: { filters: Props["filters"] }) {
  const scope = scopeFromQuery(filters);
  const overview = useScopedApi<Overview>("overview", scope);

  return (
    <Panel
      title="Site configuration"
      action={
        <>
          <StatusPill status="none" label="Read-only" />
          <Tip text={HELP} />
        </>
      }
    >
      <ApiGate state={overview} skeleton={<LoadingState rows={2} />}>
        {(o) => (
          <>
            <dl className="facts-grid">
              <div>
                <dt>Site</dt>
                <dd className="mono">{o.window.site}</dd>
              </div>
              <div>
                <dt>Sources configured</dt>
                <dd className="mono">
                  {o.coverage.sources_configured.map(sourceName).join(", ") ||
                    "—"}
                </dd>
              </div>
              <div>
                <dt>Configuration files</dt>
                <dd className="mono">{CONFIG_PATH}</dd>
              </div>
              <div>
                <dt>Changes</dt>
                <dd>Edit the files and deploy</dd>
              </div>
            </dl>
            <p className="panel-footnote">
              The API shows the site and its sources. It does not show other
              settings or their versions.
            </p>
          </>
        )}
      </ApiGate>
    </Panel>
  );
}
