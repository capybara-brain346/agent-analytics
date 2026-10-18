import { ChevronRight } from "lucide-react";

/** A table row that opens something. The identity button gives keyboard users the same action. */
export function ClickRow({
  onOpen,
  children,
}: {
  onOpen: () => void;
  children: React.ReactNode;
}) {
  return (
    <tr className="row-click" onClick={onOpen}>
      {children}
      <td data-col="chev" aria-hidden>
        <ChevronRight size={15} />
      </td>
    </tr>
  );
}

export function IdentityButton({
  children,
  label,
}: {
  children: React.ReactNode;
  label: string;
}) {
  return (
    <button type="button" className="row-identity" aria-label={label}>
      {children}
    </button>
  );
}
