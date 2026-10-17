// Traffic classes (docs/dashboard.md §4.3). Names and colours are fixed design data.
// Counts always come from the API.
export const classMeta = [
  {
    id: 1,
    name: "Verified search crawler",
    short: "Search crawlers",
    color: "#8c9eff",
  },
  { id: 2, name: "Known AI crawler", short: "AI crawlers", color: "#aa8bea" },
  {
    id: 3,
    name: "Other identifiable bot",
    short: "Other bots",
    color: "#d6b773",
  },
  {
    id: 4,
    name: "Browser automation / agent-like",
    short: "Browser automation",
    color: "#70bfc7",
  },
  {
    id: 5,
    name: "Ordinary browser",
    short: "Ordinary browsers",
    color: "#70b49c",
  },
  { id: 6, name: "Unknown", short: "Unknown", color: "#72727e" },
];
export const unclassified = {
  id: 0,
  name: "Unclassified",
  short: "Unclassified",
  color: "#4a4a55",
};
export const classOf = (id: number) =>
  classMeta.find((c) => c.id === id) ?? unclassified;
