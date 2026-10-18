import { ArrowLeft } from "lucide-react";
import type { RefObject } from "react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { DetailContent, detailTitle } from "../details";
import type { Href, OpenDetail } from "../shared";

export function DetailSheet({
  open,
  onClose,
  titleRef,
  backTo,
  onBack,
  type,
  id,
  site,
  href,
  openDetail,
}: {
  open: boolean;
  onClose: () => void;
  titleRef: RefObject<HTMLHeadingElement | null>;
  backTo: [string, string] | null;
  onBack: () => void;
  type: string;
  id: string;
  site: string;
  href: Href;
  openDetail: OpenDetail;
}) {
  return (
    <Sheet open={open} onOpenChange={(value) => !value && onClose()}>
      <SheetContent className="evidence-sheet" initialFocus={titleRef}>
        <SheetHeader className="evidence-sheet-header">
          {backTo && (
            <button className="sheet-back" onClick={onBack}>
              <ArrowLeft size={14} />
              Back to {detailTitle(...backTo)}
            </button>
          )}
          <SheetTitle ref={titleRef} tabIndex={-1}>
            {detailTitle(type, id)}
          </SheetTitle>
          <SheetDescription>
            {type === "legend"
              ? "How to read the evidence in this workspace"
              : `Evidence · ${site}`}
          </SheetDescription>
        </SheetHeader>
        <div className="sheet-body" data-scroll>
          <DetailContent type={type} id={id} href={href} open={openDetail} />
        </div>
      </SheetContent>
    </Sheet>
  );
}
