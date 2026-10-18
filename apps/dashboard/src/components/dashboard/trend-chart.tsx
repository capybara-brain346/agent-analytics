"use client";

import Link from "next/link";
import { classOf } from "@/lib/classes";
import { dateUTC, number, timeUTC } from "@/lib/format";
import type { TrendPoint } from "@/lib/api/types";
import type { Href } from "./shared";

const step = { hour: 3_600_000, day: 86_400_000 };

/** One entry for every bucket of the window. A bucket with no request is a real zero. */
function fill(
  trend: TrendPoint[],
  start: string,
  end: string,
  bucket: "hour" | "day",
): TrendPoint[] {
  const size = step[bucket];
  const byTime = new Map(trend.map((p) => [new Date(p.bucket).getTime(), p]));
  const out: TrendPoint[] = [];
  const first = Math.floor(new Date(start).getTime() / size) * size;
  for (let t = first; t <= new Date(end).getTime(); t += size)
    out.push(
      byTime.get(t) ?? {
        bucket: new Date(t).toISOString(),
        total: 0,
        by_class: {},
      },
    );
  return out;
}

/** Requests over time, stacked by traffic class. Real buckets from GET /api/overview. */
export function TrendChart({
  href,
  trend,
  start,
  end,
  bucket,
}: {
  href: Href;
  trend: TrendPoint[];
  start: string;
  end: string;
  bucket: "hour" | "day";
}) {
  const points = fill(trend, start, end, bucket);
  const keys = ["1", "2", "3", "4", "5", "6", "unclassified"].filter((k) =>
    points.some((p) => p.by_class[k]),
  );
  const meta = (k: string) => classOf(k === "unclassified" ? 0 : Number(k));
  const label = (p: TrendPoint) =>
    bucket === "day" ? dateUTC(p.bucket) : timeUTC(p.bucket);
  const height = 184;
  const baseline = height - 22;
  const raw = Math.max(...points.map((p) => p.total), 1);
  // Three gridline steps of 1, 2, 2.5 or 5 × 10^n.
  const unit = 10 ** Math.floor(Math.log10(raw / 3));
  const tick =
    [1, 2, 2.5, 5, 10].map((m) => m * unit).find((t) => t * 3 >= raw) ||
    unit * 10;
  const top = tick * 3;
  const axis = (n: number) =>
    n >= 1000 ? `${+(n / 1000).toFixed(1)}k` : String(Math.round(n * 10) / 10);
  return (
    <div className="traffic-chart">
      {[false, true].map((mobile) => {
        const width = mobile ? 340 : 900;
        const slot = (width - 49) / points.length;
        const barWidth = Math.min(slot * 0.7, 32);
        const tickCount = Math.min(mobile ? 3 : 6, points.length - 1);
        return (
          <svg
            key={String(mobile)}
            className={mobile ? "mobile-chart" : "desktop-chart"}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            focusable="false"
            aria-label="Requests over time, grouped by traffic class"
          >
            {[0, 1, 2, 3].map((i) => {
              const y = 10 + (i * (baseline - 10)) / 3;
              return (
                <g key={i}>
                  <line
                    x1="40"
                    x2={width - 6}
                    y1={y}
                    y2={y}
                    className="chart-grid"
                  />
                  <text
                    x="31"
                    y={y + 4}
                    textAnchor="end"
                    className="chart-axis"
                    fontSize={12}
                  >
                    {axis((top * (3 - i)) / 3)}
                  </text>
                </g>
              );
            })}
            {points.map((p, i) => {
              let bottom = baseline;
              return (
                <g key={p.bucket}>
                  <title>{`${label(p)} UTC · ${number(p.total)} requests`}</title>
                  {keys.map((k) => {
                    const n = p.by_class[k] ?? 0;
                    if (!n) return null;
                    const h = (n / top) * (baseline - 10);
                    bottom -= h;
                    return (
                      <rect
                        key={k}
                        x={43 + i * slot + (slot - barWidth) / 2}
                        y={bottom}
                        width={barWidth}
                        height={h}
                        fill={meta(k).color}
                      >
                        <title>{`${meta(k).name} · ${label(p)} UTC · ${number(n)} requests`}</title>
                      </rect>
                    );
                  })}
                </g>
              );
            })}
            {Array.from({ length: tickCount + 1 }, (_, i) => {
              const at = Math.round((i * (points.length - 1)) / tickCount);
              return (
                <text
                  key={i}
                  x={43 + at * slot + slot / 2}
                  y={height - 4}
                  className="chart-axis"
                  fontSize={12}
                  textAnchor={
                    i === 0 ? "start" : i === tickCount ? "end" : "middle"
                  }
                >
                  {label(points[at])}
                </text>
              );
            })}
          </svg>
        );
      })}
      <div className="chart-legend">
        {keys.map((k) =>
          k === "unclassified" ? (
            <span key={k}>
              <i style={{ background: meta(k).color }} />
              {meta(k).short}
            </span>
          ) : (
            <Link key={k} href={href("/events", { class: k })}>
              <i style={{ background: meta(k).color }} />
              {meta(k).short}
            </Link>
          ),
        )}
      </div>
    </div>
  );
}
