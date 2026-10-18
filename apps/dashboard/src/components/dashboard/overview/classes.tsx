import Link from "next/link";
import type { ClassRow } from "@/lib/api/types";
import { classOf } from "@/lib/classes";
import { number, percent } from "@/lib/format";
import {
  ClassName,
  NumberLink,
  Panel,
  TextLink,
  Tip,
  type Href,
  type OpenDetail,
} from "../shared";

const confidences = ["high", "medium", "low"] as const;

export function ClassesPanel({
  rows,
  unclassified,
  href,
  open,
}: {
  rows: ClassRow[];
  unclassified: number;
  href: Href;
  open: OpenDetail;
}) {
  const link = (c: ClassRow) =>
    href("/events", { class: String(c.traffic_class) });

  return (
    <Panel
      className="ov-panel"
      title="Traffic by class"
      label="Inferred"
      action={
        <Tip text="Classes use verified identity, the user agent, and edge signals. Each count opens the requests behind it. The small counts split each class by classification confidence." />
      }
    >
      <div className="ov-dist" role="img" aria-label="Traffic share by class">
        {rows
          .filter((c) => c.requests > 0)
          .map((c) => (
            <Link
              key={c.traffic_class}
              href={link(c)}
              style={{
                width: `${c.share_pct}%`,
                background: classOf(c.traffic_class).color,
              }}
              aria-label={`${c.name} ${percent(c.share_pct)}`}
            />
          ))}
      </div>

      <div className="ov-class-rows">
        {rows.map((c) => (
          <div key={c.traffic_class} className="ov-class-row">
            <Link href={link(c)} className="ov-class-name">
              <ClassName id={c.traffic_class} full />
            </Link>

            <span className="ov-class-figure">
              <NumberLink value={c.requests} href={link(c)} />
            </span>

            <span className="ov-class-share">{percent(c.share_pct)}</span>

            <span className="ov-class-conf">
              {confidences.map((conf) => (
                <span key={conf}>
                  {conf[0].toUpperCase() + conf.slice(1)}{" "}
                  <NumberLink
                    value={c[conf]}
                    href={href("/events", {
                      class: String(c.traffic_class),
                      confidence: conf,
                    })}
                  />
                </span>
              ))}
            </span>
          </div>
        ))}
      </div>

      <div className="panel-footnote">
        <span>
          {unclassified > 0 && (
            <>{number(unclassified)} requests have no class yet. </>
          )}
          Class does not confirm identity.{" "}
          <TextLink onClick={() => open("legend", "labels")}>
            How classes work
          </TextLink>
        </span>
      </div>
    </Panel>
  );
}
