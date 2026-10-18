"use client";

import Link from "next/link";
import { rangeOf } from "@/lib/api/filters";
import type { ApiState } from "@/lib/api/use-api";
import type { Overview as OverviewData } from "@/lib/api/types";
import { dateTimeUTC } from "@/lib/format";
import {
  ApiGate,
  LoadingState,
  NoData,
  Panel,
  Tip,
  type Href,
  type OpenDetail,
} from "../shared";
import { TrendChart } from "../trend-chart";
import { ClassesPanel } from "./classes";
import { CoveragePanel } from "./coverage";
import { MetricStrip } from "./metrics";
import { RecommendationsPanel } from "./recommendations";
import { TopPagesPanel } from "./top-pages";

function OverviewSkeleton() {
  return (
    <>
      <Panel title="Key numbers">
        <LoadingState label="Loading key numbers" rows={2} />
      </Panel>
      <Panel title="Recommended next tests">
        <LoadingState label="Loading recommendations" rows={3} />
      </Panel>
      <Panel title="Request volume">
        <LoadingState label="Loading traffic" rows={5} />
      </Panel>
    </>
  );
}

export function Overview({
  href,
  open,
  selected,
  range,
  state,
}: {
  href: Href;
  open: OpenDetail;
  selected: string;
  range: string;
  state: ApiState<OverviewData>;
}) {
  return (
    <ApiGate state={state} skeleton={<OverviewSkeleton />}>
      {(data) => (
        <OverviewBody
          data={data}
          href={href}
          open={open}
          selected={selected}
          range={range}
        />
      )}
    </ApiGate>
  );
}

function OverviewBody({
  data,
  href,
  open,
  selected,
  range,
}: {
  data: OverviewData;
  href: Href;
  open: OpenDetail;
  selected: string;
  range: string;
}) {
  if (data.empty)
    return (
      <NoData
        title="No data for this site in this time range"
        action={
          <Link className="text-link" href={href("/data")}>
            {data.freshness.last_import_at
              ? `Last import ${dateTimeUTC(data.freshness.last_import_at)} UTC · View data sources`
              : "No import yet · View data sources"}
          </Link>
        }
      >
        Try a longer time range, or check that logs arrive.
      </NoData>
    );

  const bucket = rangeOf(range).bucket;

  return (
    <>
      <MetricStrip data={data} href={href} selected={selected} range={range} />

      <RecommendationsPanel
        items={data.top_recommendations}
        href={href}
        open={open}
      />

      <div className="two-column ov-grid">
        <div className="ov-main">
          <Panel
            className="ov-panel"
            title="Request volume"
            label="Observed"
            action={
              <span className="panel-note">
                Requests per {bucket}
                <Tip text="Each bar is one UTC hour or day. Colours split the bar by traffic class." />
              </span>
            }
          >
            <TrendChart
              href={href}
              trend={data.trend}
              start={data.window.start}
              end={data.window.end}
              bucket={bucket}
            />
          </Panel>

          <TopPagesPanel
            pages={data.top_pages}
            href={href}
            open={open}
            selected={selected}
          />
        </div>

        <div className="ov-side">
          <ClassesPanel
            rows={data.traffic_by_class}
            unclassified={data.unclassified_requests}
            href={href}
            open={open}
          />

          <CoveragePanel
            coverage={data.coverage}
            freshness={data.freshness}
            href={href}
          />
        </div>
      </div>
    </>
  );
}
