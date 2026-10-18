import Link from "next/link";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { rangeOf } from "@/lib/api/filters";
import type { KeyNumberName, Overview as OverviewData } from "@/lib/api/types";
import { number, percent } from "@/lib/format";
import { Gap, type Href } from "../shared";

// Agent traffic is classes 1-4. A class filter in the URL replaces it.
export const agentClasses = (selected: string): Record<string, string> =>
  selected ? {} : { class: "1,2,3,4" };

// Label, link and wording for each key number. `bad`: a rise is bad news.
const keyNumbers: {
  key: KeyNumberName;
  title: string;
  path: string;
  filter: (selected: string) => Record<string, string>;
  bad?: boolean;
}[] = [
  {
    key: "total_requests",
    title: "Total requests",
    path: "/events",
    filter: () => ({}),
  },
  {
    key: "ai_or_automated_share",
    title: "AI and automated share",
    path: "/events",
    filter: agentClasses,
  },
  {
    key: "distinct_agents",
    title: "Distinct agents",
    path: "/agents",
    filter: () => ({}),
  },
  {
    key: "error_rate",
    title: "Error rate",
    path: "/events",
    filter: () => ({ status: "4xx,5xx" }),
    bad: true,
  },
  {
    key: "denial_rate",
    title: "Denial rate",
    path: "/events",
    filter: () => ({ status: "403,429" }),
    bad: true,
  },
];

export function MetricStrip({
  data,
  href,
  selected,
  range,
}: {
  data: OverviewData;
  href: Href;
  selected: string;
  range: string;
}) {
  const compare = rangeOf(range).compare.replace("previous", "prior");

  return (
    <div className="metrics-strip ov-metrics">
      {keyNumbers.map((m) => {
        const k = data.key_numbers[m.key];
        const text =
          k.value === null
            ? null
            : k.unit === "percent"
              ? percent(k.value)
              : number(k.value);
        const up = (k.change_pct ?? 0) >= 0;

        return (
          <Link
            key={m.key}
            href={href(m.path, m.filter(selected))}
            className="metric-cell ov-metric"
          >
            <div className="metric-label">
              {m.title}
              <ArrowUpRight size={12} />
            </div>

            <strong>{text ?? <Gap>Unknown</Gap>}</strong>

            <div className="metric-bottom">
              {k.change_pct !== null ? (
                <>
                  <span
                    className={
                      m.bad && up ? "change-negative" : "change-neutral"
                    }
                  >
                    {up ? (
                      <ArrowUpRight size={12} />
                    ) : (
                      <ArrowDownRight size={12} />
                    )}
                    {percent(Math.abs(k.change_pct))}
                  </span>
                  <span className="ov-note">vs. {compare}</span>
                </>
              ) : (
                <span className="ov-note">No prior window</span>
              )}
            </div>
          </Link>
        );
      })}
    </div>
  );
}
