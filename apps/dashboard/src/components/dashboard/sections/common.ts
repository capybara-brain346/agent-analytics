import type { Href, OpenDetail } from "../shared";

export type Filters = {
  get: (key: string) => string | null;
  toString: () => string;
};
export type Props = {
  href: Href;
  open: OpenDetail;
  filters: Filters;
  setFilter: (key: string, value: string) => void;
  reset: () => void;
};
export const option = (values: string[], all: string) => [
  { value: "", label: all },
  ...values.map((v) => ({ value: v, label: v })),
];
