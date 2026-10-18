import type { ReactNode } from "react";

const WIDE_AT = 30;

export const Dash = ({ why = "Not recorded" }: { why?: string }) => (
  <span className="fact-empty" title={why}>
    —
  </span>
);

const isWide = (value: ReactNode) =>
  typeof value === "string" && value.length > WIDE_AT;

// Facts grid: two cells per row. Long text spans both cells.
// A filler cell closes a half-empty row so the row seam spans the full width.
export function Facts({ items }: { items: [string, ReactNode][] }) {
  const cells: ReactNode[] = [];
  let col = 0;

  items.forEach(([label, value], i) => {
    const wide = isWide(value);

    if (wide && col === 1) {
      cells.push(<div key={`pad-${i}`} className="fact" aria-hidden />);
      col = 0;
    }

    cells.push(
      <div key={label} className="fact" data-wide={wide ? "" : undefined}>
        <dt>{label}</dt>
        <dd>{value}</dd>
      </div>,
    );
    col = wide ? 0 : (col + 1) % 2;
  });

  if (col === 1) cells.push(<div key="pad-end" className="fact" aria-hidden />);

  return <dl className="facts">{cells}</dl>;
}

export function Note({
  label,
  children,
}: {
  label?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="detail-note">
      {label}
      <p>{children}</p>
    </div>
  );
}
