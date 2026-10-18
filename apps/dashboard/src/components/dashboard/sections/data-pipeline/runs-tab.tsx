import { useState } from "react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useApi } from "@/lib/api/use-api";
import type { Paged, PipelineRunOut } from "@/lib/api/types";
import { dateTimeUTC, number } from "@/lib/format";
import {
  ApiGate,
  LoadingState,
  NoData,
  Panel,
  Segmented,
  TableFooter,
  Tip,
} from "../../shared";
import type { Props } from "../common";
import { ClickRow, IdentityButton } from "./click-row";
import { RUN_LIST_LIMIT, STATUS_FILTERS } from "./config";
import { durationText, laneName, statusGroup, stepName } from "./format";
import { Qualifier, StatusPill } from "./pill";

const HELP =
  "The fast lane imports new files as they arrive. The slow lane runs the heavier steps. Open a run for its step counts.";

export function RunsTab({
  open,
  filters,
}: {
  open: Props["open"];
  filters: Props["filters"];
}) {
  const scope = scopeFromQuery(filters);
  const [filter, setFilter] = useState("");
  const state = useApi<Paged<PipelineRunOut>>("runs", {
    site: scope.site || undefined,
    limit: RUN_LIST_LIMIT,
    offset: 0,
  });

  return (
    <>
      <div className="filter-toolbar">
        <Segmented
          label="Run status"
          value={filter}
          onChange={setFilter}
          options={STATUS_FILTERS}
        />
      </div>
      <Panel title="Pipeline runs" action={<Tip text={HELP} />}>
        <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
          {(d) => {
            const items = d.items.filter(
              (r) => !filter || statusGroup(r.status) === filter,
            );
            if (!items.length)
              return (
                <NoData
                  title={d.items.length ? "No match" : "No pipeline runs"}
                >
                  {d.items.length
                    ? "No run has this status."
                    : "No run was recorded yet."}
                </NoData>
              );
            return (
              <>
                <div className="table-scroll">
                  <table className="ops-table" aria-label="Pipeline runs">
                    <thead>
                      <tr>
                        <th>Run</th>
                        <th data-col="status">Status</th>
                        <th>Duration</th>
                        <th data-col="qual">Failed step</th>
                        <th data-col="time">Started</th>
                        <th data-col="chev" aria-label="Open" />
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((r) => (
                        <ClickRow key={r.id} onOpen={() => open("run", r.id)}>
                          <td>
                            <IdentityButton
                              label={`Open run ${r.id.slice(0, 8)}`}
                            >
                              <strong className="mono-id">
                                {r.id.slice(0, 8)}
                              </strong>
                              <span className="table-subline">
                                {laneName(r.lane)} lane · {r.site}
                              </span>
                            </IdentityButton>
                          </td>
                          <td data-col="status">
                            <StatusPill status={r.status} />
                          </td>
                          <td className="mono-time">
                            {durationText(r.duration_seconds)}
                          </td>
                          <td data-col="qual">
                            {r.failed_step ? (
                              <Qualifier tone="fail">
                                {stepName(r.failed_step)}
                              </Qualifier>
                            ) : (
                              <span className="faint">—</span>
                            )}
                          </td>
                          <td className="mono-time" data-col="time">
                            {dateTimeUTC(r.started_at)}
                          </td>
                        </ClickRow>
                      ))}
                    </tbody>
                  </table>
                </div>
                <TableFooter
                  count={items.length}
                  total={number(d.page.total)}
                  noun="pipeline runs"
                />
              </>
            );
          }}
        </ApiGate>
      </Panel>
    </>
  );
}
