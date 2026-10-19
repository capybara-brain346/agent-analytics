/** Minutes after a complete run during which a healthy lane still counts as live. */
export const LIVE_WINDOW_MINUTES = 60;

/** Rows requested for the import and pipeline run lists. */
export const RUN_LIST_LIMIT = 50;

/** Import files read to build the source table. */
export const SOURCE_FILE_LIMIT = 200;

export const TABS = [
  { id: "sources", name: "Sources" },
  { id: "imports", name: "Import runs" },
  { id: "runs", name: "Pipeline runs" },
  { id: "health", name: "Health & alerts" },
];

/** Status filter of the run lists. An empty value shows every row. */
export const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "done", label: "Complete" },
  { value: "active", label: "Running" },
  { value: "failed", label: "Failed" },
];
