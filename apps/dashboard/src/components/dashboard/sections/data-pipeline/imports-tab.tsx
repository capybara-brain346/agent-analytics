import { useState } from "react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useApi } from "@/lib/api/use-api";
import type { ImportList } from "@/lib/api/types";
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
import { sourceLabel, statusGroup } from "./format";
import { Qualifier, StatusPill } from "./pill";

const HELP =
  "Imported counts lines stored. A file that overlaps an earlier import, or has rejected lines, shows a note.";

export function ImportsTab({
  open,
  filters,
}: {
  open: Props["open"];
  filters: Props["filters"];
}) {
  const scope = scopeFromQuery(filters);
  const [filter, setFilter] = useState("");
  const state = useApi<ImportList>("imports", {
    site: scope.site || undefined,
    limit: RUN_LIST_LIMIT,
    offset: 0,
  });

  return (
    <>
      <div className="filter-toolbar">
        <Segmented
          label="Import status"
          value={filter}
          onChange={setFilter}
          options={STATUS_FILTERS}
        />
      </div>
      <Panel title="Import runs" action={<Tip text={HELP} />}>
        <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
          {(d) => {
            const items = d.items.filter(
              (r) => !filter || statusGroup(r.status) === filter,
            );
            if (!items.length)
              return (
                <NoData title={d.items.length ? "No match" : "No import files"}>
                  {d.items.length
                    ? "No file has this status."
                    : "No file was received yet."}
                </NoData>
              );
            return (
              <>
                <div className="table-scroll">
                  <table className="ops-table" aria-label="Import runs">
                    <thead>
                      <tr>
                        <th>File</th>
                        <th data-col="status">Status</th>
                        <th>Imported</th>
                        <th data-col="qual">Note</th>
                        <th data-col="time">Received</th>
                        <th data-col="chev" aria-label="Open" />
                      </tr>
                    </thead>
                    <tbody>
                      {items.map((r) => (
                        <ClickRow
                          key={r.id}
                          onOpen={() => open("import", r.id)}
                        >
                          <td>
                            <IdentityButton
                              label={`Open import ${r.id.slice(0, 8)}`}
                            >
                              <strong className="mono-id">
                                {r.id.slice(0, 8)}
                              </strong>
                              <span className="table-subline">
                                {r.site_id} · {sourceLabel(r.source)}
                              </span>
                            </IdentityButton>
                          </td>
                          <td data-col="status">
                            <StatusPill status={r.status} />
                          </td>
                          <td className="figure">
                            {number(r.lines_imported)}
                            <small>of {number(r.lines_total)}</small>
                          </td>
                          <td data-col="qual">
                            {r.lines_rejected ? (
                              <Qualifier
                                tone="warn"
                                title={r.overlap_warning?.message}
                              >
                                {number(r.lines_rejected)} rejected
                              </Qualifier>
                            ) : r.overlap_warning ? (
                              <Qualifier
                                tone="warn"
                                title={r.overlap_warning.message}
                              >
                                Overlaps an earlier file
                              </Qualifier>
                            ) : (
                              <span className="faint">—</span>
                            )}
                          </td>
                          <td className="mono-time" data-col="time">
                            {dateTimeUTC(r.received_at)}
                          </td>
                        </ClickRow>
                      ))}
                    </tbody>
                  </table>
                </div>
                <TableFooter
                  count={items.length}
                  total={number(d.total)}
                  noun="import runs"
                />
              </>
            );
          }}
        </ApiGate>
      </Panel>
    </>
  );
}
