import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { RecommendationBrief } from "@/lib/api/types";
import { capitalize } from "@/lib/format";
import {
  Confidence,
  NoData,
  Panel,
  Status,
  type Href,
  type OpenDetail,
} from "../shared";

export function RecommendationsPanel({
  items,
  href,
  open,
}: {
  items: RecommendationBrief[];
  href: Href;
  open: OpenDetail;
}) {
  return (
    <Panel
      title="Recommended next tests"
      className="ov-panel ov-recs"
      action={
        <Link href={href("/recommendations")}>All recommendations →</Link>
      }
    >
      {items.length ? (
        <div className="ov-rec-list">
          {items.map((r, i) => (
            <button
              key={r.id}
              className="ov-rec"
              onClick={() => open("recommendation", String(r.id))}
            >
              <span className="ov-rec-rank">{r.rank ?? i + 1}</span>

              <span className="ov-rec-main">
                <span className="ov-rec-target">{r.target}</span>
                <span className="ov-rec-meta">
                  {r.pattern_name}
                  {r.change === "new" && <Status value="New" />}
                  {r.change === "open" && <span>Still open</span>}
                </span>
              </span>

              <span className="ov-rec-score">
                <strong>{r.score}</strong>
                <span>priority</span>
              </span>

              <span className="ov-rec-conf">
                <Confidence value={capitalize(r.confidence)} />
              </span>

              <ChevronRight className="ov-chevron" size={15} />
            </button>
          ))}
        </div>
      ) : (
        <NoData
          title="No open recommendations"
          action={
            <Link className="text-link" href={href("/recommendations")}>
              Open recommendations
            </Link>
          }
        />
      )}
    </Panel>
  );
}
