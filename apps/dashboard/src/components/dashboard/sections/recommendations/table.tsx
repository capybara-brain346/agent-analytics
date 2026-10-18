import { ChevronRight } from "lucide-react";
import type { RecommendationItem } from "@/lib/api/types";
import { number } from "@/lib/format";
import { Tip } from "../../shared";
import type { Props } from "../common";
import { ChangePill, ConfidenceMark, changeLabel } from "./status";

export function RecTable({
  items,
  open,
}: {
  items: RecommendationItem[];
  open: Props["open"];
}) {
  return (
    <div className="table-scroll">
      <table className="rec-table" aria-label="Recommendations">
        <thead>
          <tr>
            <th>Recommended test</th>
            <th data-col="status">Status</th>
            <th aria-sort="descending">
              Priority ↓
              <Tip text="Priority = Impact × Frequency × Severity × Confidence. Open a recommendation to inspect each factor." />
            </th>
            <th data-col="confidence">Confidence</th>
            <th data-col="evidence">Sessions</th>
            <th data-col="chevron" aria-label="Open" />
          </tr>
        </thead>
        <tbody>
          {items.map((r, i) => (
            <tr key={r.id} onClick={() => open("recommendation", String(r.id))}>
              <td>
                <button className="rec-identity">
                  <span className="rec-name">
                    {r.recommended_test ?? r.target}
                  </span>
                  <span className="table-subline">
                    #{r.rank ?? i + 1} · {r.pattern_name} ·{" "}
                    {number(r.events_count)}{" "}
                    {r.events_count === 1 ? "event" : "events"}
                    {r.change && (
                      <span className="rec-change-inline">
                        {" "}
                        · {changeLabel(r.change)}
                      </span>
                    )}
                  </span>
                </button>
              </td>
              <td data-col="status">
                <ChangePill change={r.change} />
              </td>
              <td>
                <span className="rec-figure">{r.priority.score}</span>
              </td>
              <td data-col="confidence">
                <ConfidenceMark value={r.confidence} />
              </td>
              <td data-col="evidence" className="rec-sessions">
                {number(r.sessions_count)}
              </td>
              <td data-col="chevron">
                <ChevronRight size={15} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
