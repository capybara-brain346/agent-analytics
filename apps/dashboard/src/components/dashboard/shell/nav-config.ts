export type NavItem = {
  key: string;
  path: string;
  tab?: string;
  label: string;
};

export type NavGroup = { label: string; items: NavItem[] };

export const navGroups: NavGroup[] = [
  {
    label: "Monitor",
    items: [
      { key: "overview", path: "/overview", label: "Overview" },
      {
        key: "recommendations",
        path: "/recommendations",
        label: "Recommendations",
      },
    ],
  },
  {
    label: "Explore",
    items: [
      { key: "agents", path: "/agents", label: "Agents" },
      { key: "events", path: "/events", label: "Activity" },
      { key: "pages", path: "/pages", label: "Pages & journeys" },
    ],
  },
  {
    label: "Manage",
    items: [
      { key: "data", path: "/data", label: "Data & pipeline" },
    ],
  },
];

export const navItems = navGroups.flatMap((g) => g.items);

export const ranges = [
  { value: "1h", label: "1h" },
  { value: "6h", label: "6h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
];
