"use client";

import type { Href, OpenDetail } from "../shared";
import { AgentDetail } from "./agent";
import { EventDetail } from "./event";
import { ImportDetail } from "./import";
import { JourneyDetail } from "./journey";
import { LegendDetail } from "./legend";
import { PageDetail } from "./page";
import { RecommendationDetailView } from "./recommendation";
import { RunDetail } from "./run";
import { SessionDetail } from "./session";

export function detailTitle(type: string, id: string) {
  switch (type) {
    case "recommendation":
      return `Recommendation #${id}`;
    case "agent":
      return id;
    case "session":
      return `Session ${id}`;
    case "event":
      return `Request ${id}`;
    case "page":
      return id;
    case "journey":
      return `Journey ${id}`;
    case "run":
      return `Pipeline run ${id}`;
    case "import":
      return "Import details";
    default:
      return "Understand the evidence";
  }
}
export function DetailContent({
  type,
  id,
  href,
  open,
}: {
  type: string;
  id: string;
  href: Href;
  open: OpenDetail;
}) {
  switch (type) {
    case "recommendation":
      return <RecommendationDetailView id={id} href={href} open={open} />;
    case "agent":
      return <AgentDetail id={id} href={href} open={open} />;
    case "session":
      return <SessionDetail id={id} href={href} open={open} />;
    case "event":
      return <EventDetail id={id} href={href} open={open} />;
    case "page":
      return <PageDetail id={id} href={href} open={open} />;
    case "journey":
      return <JourneyDetail id={id} href={href} open={open} />;
    case "import":
      return <ImportDetail id={id} href={href} open={open} />;
    case "run":
      return <RunDetail id={id} href={href} open={open} />;
    default:
      return <LegendDetail href={href} />;
  }
}
