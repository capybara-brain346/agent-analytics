import { ChevronLeft, ChevronRight } from "lucide-react";
import { number } from "@/lib/format";
import { PAGE_SIZE } from "./config";

export function PagerFooter({
  page,
  shown,
  noun,
  onPage,
}: {
  page: { offset: number; total: number; next_offset: number | null };
  shown: number;
  noun: string;
  onPage: (offset: number) => void;
}) {
  const from = shown ? page.offset + 1 : 0;

  return (
    <div className="table-footer">
      <span>
        Showing {number(from)}–{number(page.offset + shown)} of{" "}
        {number(page.total)} {noun}
        {page.total === 1 ? "" : "s"}
      </span>

      <span className="pager">
        <button
          className="pager-button"
          aria-label="Previous page"
          disabled={page.offset === 0}
          onClick={() => onPage(Math.max(0, page.offset - PAGE_SIZE))}
        >
          <ChevronLeft size={14} />
        </button>

        <button
          className="pager-button"
          aria-label="Next page"
          disabled={page.next_offset === null}
          onClick={() => page.next_offset !== null && onPage(page.next_offset)}
        >
          <ChevronRight size={14} />
        </button>
      </span>
    </div>
  );
}
