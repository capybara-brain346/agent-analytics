import Link from "next/link";
import type { Overview as OverviewData } from "@/lib/api/types";
import {
  NoData,
  NumberLink,
  Panel,
  Tip,
  type Href,
  type OpenDetail,
} from "../shared";
import { agentClasses } from "./metrics";

export function TopPagesPanel({
  pages,
  href,
  open,
  selected,
}: {
  pages: OverviewData["top_pages"];
  href: Href;
  open: OpenDetail;
  selected: string;
}) {
  const agentOnly = agentClasses(selected);
  const agentTrafficSelected =
    !selected || selected.split(",").some((c) => Number(c) <= 4);

  return (
    <Panel
      className="ov-panel"
      title="Top pages by agent traffic"
      label="Observed"
      action={<Link href={href("/pages")}>All pages →</Link>}
    >
      {pages.length ? (
        <div className="table-scroll">
          <table className="ov-pages" aria-label="Top pages">
            <thead>
              <tr>
                <th>Page path</th>
                <th aria-sort="descending">
                  Agent requests <span className="sort-arrow">↓</span>
                  <Tip text="Requests from traffic classes 1–4." />
                </th>
                <th data-col="errors">
                  Errors
                  <Tip text="Status 400 and above. HTTP status does not prove task completion." />
                </th>
                <th data-col="denied">
                  Denied
                  <Tip text="Status 403 and 429." />
                </th>
              </tr>
            </thead>
            <tbody>
              {pages.map((p) => (
                <tr
                  key={p.path}
                  className="ov-page-row"
                  onClick={() => open("page", p.path)}
                >
                  <td>
                    <button
                      className="ov-path"
                      onClick={(e) => {
                        e.stopPropagation();
                        open("page", p.path);
                      }}
                    >
                      {p.path}
                    </button>
                  </td>
                  <td onClick={(e) => e.stopPropagation()}>
                    <span className="ov-figure">
                      <NumberLink
                        value={p.agent_requests}
                        href={href("/events", { path: p.path, ...agentOnly })}
                      />
                    </span>
                  </td>
                  <td data-col="errors" onClick={(e) => e.stopPropagation()}>
                    <NumberLink
                      value={p.errors}
                      href={href("/events", {
                        path: p.path,
                        status: "4xx,5xx",
                        ...agentOnly,
                      })}
                    />
                  </td>
                  <td data-col="denied" onClick={(e) => e.stopPropagation()}>
                    <span className={p.blocks > 0 ? "ov-denied" : undefined}>
                      {p.blocks > 0 && <i />}
                      <NumberLink
                        value={p.blocks}
                        href={href("/events", {
                          path: p.path,
                          status: "403,429",
                          ...agentOnly,
                        })}
                      />
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <NoData title="No agent requests to pages">
          {agentTrafficSelected
            ? "No class 1–4 request arrived in this window."
            : "The selected classes are outside classes 1–4."}
        </NoData>
      )}
    </Panel>
  );
}
