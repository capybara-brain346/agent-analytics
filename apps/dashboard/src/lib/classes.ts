// Traffic classes (docs/dashboard.md §4.3). Names and colours are fixed design data.
// Counts always come from the API.
// Stacked-bar palette: separated by lightness so segments stay distinguishable on white.
// Search ink, AI jade, other bots warn gold, automation deep jade, then three greys.
export const classMeta = [
  {
    id: 1,
    name: "Verified search crawler",
    short: "Search crawlers",
    color: "#3b434e",
  },
  { id: 2, name: "Known AI crawler", short: "AI crawlers", color: "#0ba96c" },
  {
    id: 3,
    name: "Other identifiable bot",
    short: "Other bots",
    color: "#cf8b2e",
  },
  {
    id: 4,
    name: "Browser automation / agent-like",
    short: "Browser automation",
    color: "#078054",
  },
  {
    id: 5,
    name: "Ordinary browser",
    short: "Ordinary browsers",
    color: "#a2a8b0",
  },
  { id: 6, name: "Unknown", short: "Unknown", color: "#c9cdd3" },
];
export const unclassified = {
  id: 0,
  name: "Unclassified",
  short: "Unclassified",
  color: "#e1e3e7",
};
export const classOf = (id: number) =>
  classMeta.find((c) => c.id === id) ?? unclassified;
