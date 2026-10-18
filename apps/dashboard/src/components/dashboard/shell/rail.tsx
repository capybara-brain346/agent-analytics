import Link from "next/link";
import { dateTimeUTC } from "@/lib/format";
import type { Freshness } from "@/lib/api/types";
import type { Href } from "../shared";
import { navGroups } from "./nav-config";

export function Rail({
  href,
  active,
  site,
  freshness,
  onNavigate,
}: {
  href: Href;
  active: string;
  site: string;
  freshness?: Freshness;
  onNavigate?: () => void;
}) {
  return (
    <>
      <Link href={href("/overview")} className="rail-head" onClick={onNavigate}>
        <span className="rail-mark" aria-hidden>
          A
        </span>
        <span className="rail-title">
          <strong>Agent Analytics</strong>
          <small>{site || "Agent traffic"}</small>
        </span>
      </Link>
      <nav className="rail-nav" data-scroll aria-label="Main navigation">
        {navGroups.map((group) => (
          <div key={group.label} className="nav-group">
            <div className="nav-caption">{group.label}</div>
            {group.items.map((item) => (
              <Link
                key={item.key}
                className={`nav-item ${active === item.key ? "active" : ""}`}
                href={href(item.path, item.tab ? { tab: item.tab } : {})}
                onClick={onNavigate}
                aria-current={active === item.key ? "page" : undefined}
              >
                <span className="nav-dot" />
                <span>{item.label}</span>
              </Link>
            ))}
          </div>
        ))}
      </nav>
      <div className="rail-foot">
        <span>Data up to</span>
        <span className="mono">
          {freshness?.data_up_to
            ? `${dateTimeUTC(freshness.data_up_to)} UTC`
            : "–"}
        </span>
      </div>
    </>
  );
}
