import type { ApiError } from "@/lib/api/client";
import type { Health } from "@/lib/api/types";
import { dateTimeUTC } from "@/lib/format";
import { ApiGate, LoadingState, NoData, Panel, Tip } from "../../shared";
import { alertLastFile, alertSentence, laneName } from "./format";
import { Qualifier, StatusPill } from "./pill";

const ALERT_HELP = "Cleared alerts are not in the API. Only open alerts show.";

export function HealthTab({
  state,
  lanes,
  alerts,
}: {
  state: { data: Health | null; error: ApiError | null; reload: () => void };
  lanes: Health["lanes"];
  alerts: Health["alerts"];
}) {
  return (
    <ApiGate
      state={{ ...state, loading: false }}
      skeleton={<LoadingState rows={3} />}
    >
      {() => (
        <>
          <Panel title="Alerts" action={<Tip text={ALERT_HELP} />}>
            {alerts.length === 0 ? (
              <NoData title="No open alerts" />
            ) : (
              <div className="table-scroll">
                <table className="ops-table" aria-label="Alerts">
                  <thead>
                    <tr>
                      <th>Alert</th>
                      <th data-col="site">Site</th>
                      <th>Raised</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((a) => {
                      const last = alertLastFile(a.message);
                      return (
                        <tr key={a.id} title={a.message}>
                          <td>
                            <Qualifier tone="warn">
                              <strong className="alert-sentence">
                                {alertSentence(a.kind, a.source, a.message)}
                              </strong>
                            </Qualifier>
                            <span className="table-subline alert-meta">
                              {a.kind}
                              {last ? ` · last file ${dateTimeUTC(last)}` : ""}
                            </span>
                          </td>
                          <td data-col="site" className="mono-time">
                            {a.site_id}
                          </td>
                          <td className="mono-time">
                            {dateTimeUTC(a.raised_at)}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
          <Panel title="Lanes">
            {lanes.length === 0 ? (
              <NoData title="No lane reported">
                The API reported no lane for this site.
              </NoData>
            ) : (
              <div className="table-scroll">
                <table className="ops-table" aria-label="Lanes">
                  <thead>
                    <tr>
                      <th>Lane</th>
                      <th data-col="status">Status</th>
                      <th>Last complete run</th>
                    </tr>
                  </thead>
                  <tbody>
                    {lanes.map((l) => (
                      <tr key={`${l.site_id}-${l.lane}`}>
                        <td>
                          <strong className="lane-title">
                            {laneName(l.lane)} lane
                          </strong>
                          <span className="table-subline">{l.site_id}</span>
                        </td>
                        <td data-col="status">
                          <StatusPill
                            status={l.healthy ? "success" : "failed"}
                            label={l.healthy ? "Healthy" : "Late"}
                          />
                        </td>
                        <td className="mono-time">
                          {l.last_success
                            ? dateTimeUTC(l.last_success)
                            : "No complete run yet"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>
        </>
      )}
    </ApiGate>
  );
}
