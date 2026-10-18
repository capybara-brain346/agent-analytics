"use client";

import Link from "next/link";
import type { Props } from "../common";
import { JourneysTab } from "./journeys-tab";
import { PagesTab } from "./pages-tab";

export function PagesJourneys({
  href,
  open,
  filters,
  setFilter,
  reset,
  isJourneys,
}: Props & { isJourneys: boolean }) {
  return (
    <>
      <div className="page-tabs" role="navigation" aria-label="Views">
        <Link
          className={!isJourneys ? "active" : ""}
          aria-current={!isJourneys ? "page" : undefined}
          href={href("/pages")}
        >
          Pages
        </Link>
        <Link
          className={isJourneys ? "active" : ""}
          aria-current={isJourneys ? "page" : undefined}
          href={href("/journeys")}
        >
          Journeys
        </Link>
      </div>
      {isJourneys ? (
        <JourneysTab href={href} open={open} filters={filters} />
      ) : (
        <PagesTab
          href={href}
          open={open}
          filters={filters}
          setFilter={setFilter}
          reset={reset}
        />
      )}
    </>
  );
}
