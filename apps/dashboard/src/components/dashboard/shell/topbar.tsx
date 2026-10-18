import Link from "next/link";
import { CircleHelp, Menu } from "lucide-react";
import type { Freshness } from "@/lib/api/types";
import type { Href } from "../shared";

const stateChip: Record<
  Freshness["state"],
  { tone: "ok" | "warn" | "fail"; label: string }
> = {
  ok: { tone: "ok", label: "Live" },
  updating: { tone: "warn", label: "Updating" },
  no_runs: { tone: "warn", label: "No runs yet" },
  alert_no_data: { tone: "warn", label: "No recent data" },
  alert_failing: { tone: "fail", label: "Alert failing" },
  last_run_failed: { tone: "fail", label: "Last run failed" },
};

export function TopBar({
  title,
  href,
  freshness,
  failed,
  onMenu,
  onLabelGuide,
}: {
  title: string;
  href: Href;
  freshness?: Freshness;
  failed: boolean;
  onMenu: () => void;
  onLabelGuide: () => void;
}) {
  const chip = freshness
    ? stateChip[freshness.state]
    : failed
      ? { tone: "fail" as const, label: "Data unavailable" }
      : { tone: "idle" as const, label: "Checking" };
  const attention = freshness && freshness.state !== "ok";
  return (
    <header className="topbar">
      <button
        className="topbar-menu"
        aria-label="Open navigation"
        onClick={onMenu}
      >
        <Menu size={18} />
      </button>
      <div className="crumbs">
        <span className="crumb-parent">Agent Analytics</span>
        <span className="crumb-sep">/</span>
        <h1 className="crumb-current">{title}</h1>
      </div>
      <Link
        href={href("/data", attention ? { tab: "health" } : {})}
        className={`state-chip ${chip.tone}`}
        title={freshness?.text}
      >
        <span className="state-dot" />
        {chip.label}
      </Link>
      <div className="topbar-right">
        <button
          className="btn-standard"
          aria-label="Label guide"
          onClick={onLabelGuide}
        >
          <CircleHelp size={15} />
          <span>Label guide</span>
        </button>
      </div>
    </header>
  );
}
