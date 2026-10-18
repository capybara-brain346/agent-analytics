import { useRouter } from "next/navigation";
import { useApi, useScopedApi } from "@/lib/api/use-api";
import { scopeFromQuery } from "@/lib/api/filters";
import type { Health, ImportList, Overview } from "@/lib/api/types";
import { dateTimeUTC, number } from "@/lib/format";
import { ApiGate, LoadingState, NoData, Panel, Tip } from "../../shared";
import type { Props } from "../common";
import { ClickRow, IdentityButton } from "./click-row";
import { SOURCE_FILE_LIMIT } from "./config";
import { alertSentence, sourceLabel } from "./format";
import { Qualifier, StatusPill } from "./pill";
import { SourcePanels } from "./source-panels";
import { sourceRows, sourceState } from "./source-rows";
import {
  UploadControls,
  UploadDropZone,
  UploadResult,
  useUpload,
} from "./upload";

const HELP = `Files and times come from the newest ${SOURCE_FILE_LIMIT} import files. The format and field map of each source are not in the API.`;

export function SourcesTab({
  href,
  filters,
  health,
}: {
  href: Props["href"];
  filters: Props["filters"];
  health: Health | null;
}) {
  const router = useRouter();
  const scope = scopeFromQuery(filters);
  const imports = useApi<ImportList>("imports", {
    site: scope.site || undefined,
    limit: SOURCE_FILE_LIMIT,
  });
  const overview = useScopedApi<Overview>("overview", scope);
  const upload = useUpload(
    scope.site,
    imports.data?.items[0]?.site_id,
    overview.data?.coverage.sources_configured ?? [],
    () => imports.reload(),
  );
  const coverage = overview.data?.coverage;
  const site = overview.data?.window.site ?? null;

  return (
    <UploadDropZone upload={upload}>
      <div className="filter-toolbar">
        <span className="toolbar-count">
          {imports.data
            ? `${number(imports.data.total)} import files received`
            : "Loading sources"}
        </span>
        <div className="toolbar-end">
          <UploadControls upload={upload} />
        </div>
      </div>
      <UploadResult upload={upload} />
      <Panel title="Data sources" action={<Tip text={HELP} />}>
        <ApiGate state={imports} skeleton={<LoadingState rows={3} />}>
          {(d) => {
            const rows = sourceRows(
              d.items,
              coverage && site
                ? { site, sources: coverage.sources_configured }
                : null,
            );
            if (!rows.length)
              return (
                <NoData title="No files received">
                  No import file exists for this site yet.
                </NoData>
              );
            return (
              <div className="table-scroll">
                <table className="ops-table" aria-label="Data sources">
                  <thead>
                    <tr>
                      <th>Site / source</th>
                      <th data-col="status">Status</th>
                      <th>Files</th>
                      <th data-col="qual">Note</th>
                      <th data-col="time">Last file</th>
                      <th data-col="time">Last event</th>
                      <th data-col="chev" aria-label="Open" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((r) => {
                      const state = sourceState(r, health);
                      return (
                        <ClickRow
                          key={`${r.site}-${r.source}`}
                          onOpen={() =>
                            router.push(href("/data", { tab: "imports" }))
                          }
                        >
                          <td>
                            <IdentityButton
                              label={`${r.site} ${sourceLabel(r.source)}, open import runs`}
                            >
                              <strong>{r.site}</strong>
                              <span className="table-subline">
                                {sourceLabel(r.source)}
                              </span>
                            </IdentityButton>
                          </td>
                          <td data-col="status">
                            <StatusPill
                              status={state.status}
                              label={state.label}
                            />
                          </td>
                          <td className="figure">
                            {r.files ? number(r.files) : "—"}
                          </td>
                          <td data-col="qual">
                            {state.alert ? (
                              <Qualifier
                                tone="warn"
                                title={state.alert.message}
                              >
                                {alertSentence(
                                  state.alert.kind,
                                  null,
                                  state.alert.message,
                                )}
                              </Qualifier>
                            ) : state.status === "failed" ? (
                              <Qualifier tone="fail">
                                Last import failed
                              </Qualifier>
                            ) : (
                              <span className="faint">—</span>
                            )}
                          </td>
                          <td className="mono-time" data-col="time">
                            {r.lastFile ? dateTimeUTC(r.lastFile) : "—"}
                          </td>
                          <td className="mono-time" data-col="time">
                            {r.lastEvent ? dateTimeUTC(r.lastEvent) : "—"}
                          </td>
                        </ClickRow>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          }}
        </ApiGate>
      </Panel>
      <SourcePanels href={href} overview={overview} />
    </UploadDropZone>
  );
}
