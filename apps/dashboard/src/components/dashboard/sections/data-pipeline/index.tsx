"use client";

import Link from "next/link";
import { apiHealth } from "@/lib/api/client";
import { scopeFromQuery } from "@/lib/api/filters";
import { useQuery } from "@/lib/api/use-api";
import type { Health } from "@/lib/api/types";
import { Props } from "../common";
import { TABS } from "./config";
import { HealthTab } from "./health-tab";
import { ImportsTab } from "./imports-tab";
import { LaneStrip } from "./lane-strip";
import { RunsTab } from "./runs-tab";
import { SettingsTab } from "./settings-tab";
import { SourcesTab } from "./sources-tab";

export {
  countEntries,
  durationText,
  laneName,
  sourceLabel,
  statusLabel,
  stepName,
} from "./format";
export { Qualifier, StatusPill } from "./pill";

export function DataPipeline({ href, open, filters }: Props) {
  const tab = filters.get("tab") || "sources";
  const scope = scopeFromQuery(filters);
  const health = useQuery<Health>("health", (signal) => apiHealth(signal));
  const lanes = (health.data?.lanes ?? []).filter(
    (l) => !scope.site || l.site_id === scope.site,
  );
  const alerts = (health.data?.alerts ?? []).filter(
    (a) => !scope.site || a.site_id === scope.site,
  );

  return (
    <>
      <LaneStrip
        href={href}
        tab={tab}
        health={health.data}
        error={health.error}
        loading={health.data === null && !health.error}
        lanes={lanes}
        alerts={alerts}
      />
      <div className="page-tabs" role="navigation" aria-label="Data views">
        {TABS.map((t) => (
          <Link
            key={t.id}
            className={tab === t.id ? "active" : ""}
            aria-current={tab === t.id ? "page" : undefined}
            href={href("/data", { tab: t.id })}
            scroll={false}
          >
            {t.name}
          </Link>
        ))}
      </div>
      {tab === "sources" && (
        <SourcesTab href={href} filters={filters} health={health.data} />
      )}
      {tab === "imports" && <ImportsTab open={open} filters={filters} />}
      {tab === "runs" && <RunsTab open={open} filters={filters} />}
      {tab === "health" && (
        <HealthTab state={health} lanes={lanes} alerts={alerts} />
      )}
      {tab === "settings" && <SettingsTab filters={filters} />}
    </>
  );
}
