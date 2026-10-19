import { Globe2 } from "lucide-react";
import { ClassFilter, Segmented, Select } from "../shared";
import { ranges } from "./nav-config";

export function FilterBar({
  site,
  sites,
  range,
  classes,
  caption,
  setFilter,
}: {
  site: string;
  sites: string[];
  range: string;
  classes: string;
  caption: string;
  setFilter: (key: string, value: string) => void;
}) {
  return (
    <div className="filterbar">
      <div className="filter-group">
        <Select
          label="Site"
          value={site}
          onChange={(v) => setFilter("site", v)}
          icon={<Globe2 size={14} />}
          options={
            sites.length
              ? sites.map((s) => ({ value: s, label: s }))
              : [{ value: site, label: site || "Loading…" }]
          }
        />
        <Segmented
          label="Time range"
          value={range}
          onChange={(v) => setFilter("range", v)}
          options={ranges}
        />
        <ClassFilter value={classes} onChange={(v) => setFilter("class", v)} />
      </div>
      <span className="window-caption">{caption}</span>
    </div>
  );
}
