"use client";

import { ArrowRight } from "lucide-react";
import { scopeFromQuery } from "@/lib/api/filters";
import { useScopedApi } from "@/lib/api/use-api";
import type { JourneyOut } from "@/lib/api/types";
import { capitalize, number } from "@/lib/format";
import {
  ApiGate,
  Label,
  LoadingState,
  NoData,
  NumberLink,
  Panel,
  TextLink,
} from "../../shared";
import type { Props } from "../common";
import { JOURNEY_DROP_WARN_RATIO } from "./config";
import { plural, type Tone } from "./health";

type TabProps = Pick<Props, "href" | "open" | "filters">;

const sum = (j: JourneyOut, key: "reached" | "stopped_at" | "retry_or_loop") =>
  j.steps.map((_, i) => j.by_class.reduce((s, c) => s + (c[key][i] ?? 0), 0));

/** How much of the step before this one kept going. */
function keepTone(prev: number, now: number): Tone {
  if (prev === 0) return "neutral";
  if (now === 0) return "fail";
  return now / prev < JOURNEY_DROP_WARN_RATIO ? "warn" : "pass";
}

export function JourneysTab({ href, open, filters }: TabProps) {
  const state = useScopedApi<JourneyOut[]>("journeys", scopeFromQuery(filters));

  return (
    <>
      <ApiGate state={state} skeleton={<LoadingState rows={6} />}>
        {(list) =>
          list.length ? (
            <div className="journey-list">
              {list.map((j) => (
                <JourneyBlock
                  key={j.journey_id}
                  j={j}
                  href={href}
                  open={open}
                />
              ))}
            </div>
          ) : (
            <NoData title="No journeys configured">
              Define journeys in the site config to see how far agents reach.
            </NoData>
          )
        }
      </ApiGate>
      <p className="pages-hint">
        Reached means a session requested the page. It does not show task
        completion.
      </p>
    </>
  );
}

function JourneyBlock({
  j,
  href,
  open,
}: {
  j: JourneyOut;
  href: Props["href"];
  open: Props["open"];
}) {
  const reached = sum(j, "reached");
  const stopped = sum(j, "stopped_at");
  const retries = sum(j, "retry_or_loop");
  const entry = reached[0] ?? 0;
  const retryText = retries.some((n) => n > 0)
    ? retries
        .map((n, i) => (n ? `step ${i + 1}: ${number(n)}` : null))
        .filter(Boolean)
        .join(" · ")
    : "none";

  return (
    <Panel
      title={j.journey_id}
      label={capitalize(j.by_class[0]?.label ?? "observed")}
      action={
        <>
          <span className={`qualifier ${j.critical ? "warn" : "neutral"}`}>
            <i />
            {j.critical ? "Critical" : "Standard"}
          </span>
          <TextLink onClick={() => open("journey", j.journey_id)}>
            View evidence
            <ArrowRight size={13} />
          </TextLink>
        </>
      }
    >
      <ol className="journey-steps">
        {j.steps.map((path, i) => {
          const share = entry ? (reached[i] / entry) * 100 : 0;
          const tone = i === 0 ? "pass" : keepTone(reached[i - 1], reached[i]);
          const lost = i === 0 ? 0 : reached[i - 1] - reached[i];
          const sessionsHref = href("/sessions", {
            journey: j.journey_id,
            reached: String(i + 1),
          });

          return (
            <li key={path} className="journey-step">
              <span className="step-index">{i + 1}</span>
              <span className="step-id">
                <code className="step-path">{path}</code>
                <span className="step-sub">
                  {stopped[i] > 0
                    ? `${number(stopped[i])} ${i === j.steps.length - 1 ? "ended" : "stopped"} here`
                    : "None stopped here"}
                  {retries[i] > 0 &&
                    ` · ${number(retries[i])} ${plural(retries[i], "retry", "retries")}`}
                </span>
              </span>
              <span
                className="step-bar"
                role="img"
                aria-label={`${share.toFixed(0)}% of entry sessions reached step ${i + 1}`}
              >
                <i className={tone} style={{ width: `${share}%` }} />
              </span>
              <span className="step-figure">
                <NumberLink value={reached[i]} href={sessionsHref} />
              </span>
              <span className="step-drop">
                {i === 0 ? (
                  <span className="step-note">Entry</span>
                ) : (
                  <span className={`qualifier ${tone}`}>
                    <i />
                    {lost > 0
                      ? `−${number(lost)} · ${Math.round((lost / reached[i - 1]) * 100)}%`
                      : "No drop"}
                  </span>
                )}
              </span>
            </li>
          );
        })}
      </ol>
      {j.by_class.length ? (
        <div className="table-scroll journey-classes">
          <table aria-label="Journeys">
            <thead>
              <tr>
                <th>Class</th>
                <th>Sessions</th>
                {j.steps.slice(1).map((s, i) => (
                  <th key={s} title={`Sessions that reached ${s}`}>
                    Step {i + 2}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {j.by_class.map((c) => (
                <tr key={c.traffic_class}>
                  <td>{c.class_name}</td>
                  <td>
                    <NumberLink
                      value={c.sessions}
                      href={href("/sessions", {
                        journey: j.journey_id,
                        reached: "1",
                        class: String(c.traffic_class),
                      })}
                    />
                  </td>
                  {c.reached.slice(1).map((n, i) => (
                    <td key={i}>
                      <NumberLink
                        value={n}
                        href={href("/sessions", {
                          journey: j.journey_id,
                          reached: String(i + 2),
                          class: String(c.traffic_class),
                        })}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="panel-footnote">
          No sessions reached the first step in this window.
        </p>
      )}
      <div className="panel-footnote journey-foot">
        <span>Retries or loops by step: {retryText}</span>
        <span className="journey-outcome">
          Task outcome <Label type="Unknown" />
        </span>
      </div>
    </Panel>
  );
}
