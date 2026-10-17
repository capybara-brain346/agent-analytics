import type { Href, OpenDetail } from "../shared";
import { Label } from "../shared";

export type DetailProps = {
  id: string;
  href: Href;
  open: OpenDetail;
  run?: number;
};
export function DetailSection({
  title,
  label,
  children,
}: {
  title: string;
  label?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="detail-section">
      <div className="detail-section-heading">
        <h3>{title}</h3>
        {label && <Label type={label} />}
      </div>
      {children}
    </section>
  );
}
export function Fields({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="detail-fields">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}
