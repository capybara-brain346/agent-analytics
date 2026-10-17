"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  Check,
  ChevronRight,
  CircleAlert,
  Info,
  ShieldCheck,
} from "lucide-react";
import {
  agents,
  classes,
  events,
  imports,
  journeys,
  number,
  pages,
  recommendations,
  runs,
  sessions,
  type Recommendation,
} from "@/lib/mock-data";
import {
  ClassName,
  Confidence,
  CountLink,
  Href,
  Label,
  NumberLink,
  OpenDetail,
  Status,
  TextLink,
} from "./shared";

export function detailTitle(type: string, id: string) {
  switch (type) {
    case "recommendation":
      return (
        recommendations.find((r) => r.id === id)?.title || "Recommendation"
      );
    case "agent":
      return agents.find((a) => a.id === id)?.name || "Agent detail";
    case "session":
      return `Session ${id}`;
    case "event":
      return `Request ${id}`;
    case "page":
      return pages.find((p) => p.id === id)?.path || "Page detail";
    case "journey":
      return journeys.find((j) => j.id === id)?.name || "Journey detail";
    case "run":
      return `Pipeline run ${id}`;
    case "import":
      return "Import details";
    default:
      return "Understand the evidence";
  }
}
function DetailSection({
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
function Fields({ items }: { items: [string, React.ReactNode][] }) {
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
export function DetailContent({
  type,
  id,
  href,
  open,
  run = 14,
}: {
  type: string;
  id: string;
  href: Href;
  open: OpenDetail;
  run?: number;
}) {
  if (type === "recommendation") {
    const r = recommendations.find((r) => r.id === id);
    if (!r) return <p>There is no sample record for this ID.</p>;
    return <RecommendationDetail r={r} href={href} open={open} run={run} />;
  }
  if (type === "agent") {
    const a = agents.find((a) => a.id === id);
    if (!a) return <p>There is no sample agent for this ID.</p>;
    const verified = a.verdict === "VERIFIED";
    return (
      <>
        <div className="detail-chips">
          <Status value={a.verdict} />
          <ClassName id={a.classId} full />
          <Confidence value={a.confidence} />
        </div>
        {!verified && (
          <div className="detail-notice">
            <Info size={14} />
            {a.verdict === "CLAIMED" || a.verdict === "UNVERIFIED"
              ? `Claims to be ${a.name}, unverified.`
              : "The exact client identity is unknown."}
          </div>
        )}
        <DetailSection title="Activity" label="Observed">
          <div className="detail-metrics">
            <Link href={href("/events", { agent: a.id })}>
              <strong>{number(a.requests)}</strong>requests
            </Link>
            <Link href={href("/sessions", { agent: a.id })}>
              <strong>{number(a.sessions)}</strong>sessions
            </Link>
            <div>
              <strong>{a.pages}</strong>distinct pages
            </div>
          </div>
          <Fields
            items={[
              ["Vendor", a.vendor],
              ["First seen", `${a.first}, 2026`],
              ["Last seen", `Oct 16, ${a.last}`],
              ["Common paths", <code key="paths">{a.paths}</code>],
            ]}
          />
        </DetailSection>
        <DetailSection title="Why this class" label="Inferred">
          <Fields
            items={[
              ["Class", <ClassName key="class" id={a.classId} full />],
              [
                "Rule",
                <code key="rule">
                  {a.classId === 1
                    ? "C1 · verified search crawler"
                    : a.classId === 2
                      ? "C2 · registry AI crawler"
                      : a.classId === 4
                        ? "C4 · headless or edge bot signal"
                        : a.classId === 5
                          ? "C5 · browser + human edge signal"
                          : a.classId === 6
                            ? "C6 · insufficient evidence"
                            : "C3 · identifiable bot"}
                </code>,
              ],
              ["Identity input", a.verdict],
              [
                "UA input",
                a.classId < 4
                  ? `${a.name}/1.0`
                  : a.classId === 4
                    ? "HeadlessChrome/130.0"
                    : "Chrome/130.0",
              ],
              [
                "Edge signal",
                a.classId === 5 ? "Human" : a.classId === 6 ? "None" : "Bot",
              ],
              ["Versions", "Rule v3 · registry v12"],
            ]}
          />
        </DetailSection>
        <DetailSection title="Verdict history" label="Observed">
          <div className="history-item">
            <div>
              <span className="timeline-dot" />
              <strong>Oct 16, 14:00</strong>
              <Status value={a.verdict} />
            </div>
            <p>
              {verified
                ? "Source IP matched the sample registry snapshot."
                : "The available sample evidence does not verify this identity."}
            </p>
            <Link
              className="text-link"
              href={href("/events", { agent: a.id, verdict: a.verdict })}
            >
              Inspect requests with this verdict
              <ArrowUpRight size={12} />
            </Link>
          </div>
          {verified && (
            <div className="history-item">
              <div>
                <span className="timeline-dot" />
                <strong>Oct 15, 09:12</strong>
                <Status value="VERIFIED" />
              </div>
              <p>
                IP matched the previous sample snapshot. This historical verdict
                is retained.
              </p>
            </div>
          )}
        </DetailSection>
        <DetailSection title="Client keys" label="Observed">
          <Fields
            items={[
              ["User agent", `${a.name}/1.0 (sample)`],
              ["Client IP", "192.0.2.24 · documentation address"],
              [
                "Shared IP",
                a.id === "chatgpt-user"
                  ? "Yes · session confidence is Low"
                  : "No shared-IP flag in this sample",
              ],
            ]}
          />
        </DetailSection>
        <DetailSection title="Sample sessions">
          <div className="detail-link-list">
            {sessions
              .filter((s) => s.agentId === a.id)
              .map((s) => (
                <button key={s.id} onClick={() => open("session", s.id)}>
                  <code>{s.id}</code>
                  <span>{s.requests} requests</span>
                  <ChevronRight size={14} />
                </button>
              ))}
            {!sessions.some((s) => s.agentId === a.id) && (
              <p className="muted">
                No individual session is included for this agent in the sample.
              </p>
            )}
          </div>
        </DetailSection>
      </>
    );
  }
  if (type === "session") {
    const s = sessions.find((s) => s.id === id);
    if (!s) return <p>There is no sample session for this ID.</p>;
    const reason =
      s.confidence === "Low" && s.agentId === "chatgpt-user"
        ? "Agent client with a shared IP; requests may include multiple agents."
        : s.confidence === "High"
          ? "Verified identity; no shared-IP flag."
          : "Identity or grouping has limited evidence.";
    const a = agents.find((a) => a.id === s.agentId)!,
      steps = events.filter((e) => e.sessionId === s.id);
    return (
      <>
        <div className="detail-chips">
          <button className="text-link" onClick={() => open("agent", a.id)}>
            {a.name}
            <ArrowUpRight size={12} />
          </button>
          <ClassName id={a.classId} />
          <Status value={s.state} />
        </div>
        <DetailSection title="Session summary" label="Observed">
          <div className="detail-metrics">
            <Link href={href("/events", { session: s.id })}>
              <strong>{s.requests}</strong>requests
            </Link>
            <div>
              <strong>{s.pageCount}</strong>distinct pages
            </div>
            <div>
              <strong>{s.reached}</strong>steps reached
            </div>
          </div>
          <Fields
            items={[
              ["Started", `Oct 16, 2026 · ${s.started}`],
              [
                "Last seen",
                `${s.last}${s.state === "In progress" ? " · can still grow" : ""}`,
              ],
              [
                "Confidence",
                <Confidence key="confidence" value={s.confidence} />,
              ],
              ["Confidence reason", reason],
              [
                "Signals",
                `${s.retry ? "Retry detected" : "No retry"} · ${s.loop ? "Loop detected" : "No loop"}`,
              ],
            ]}
          />
        </DetailSection>
        <div className="detail-notice">
          <Label type="Inferred" />
          <p>
            These requests likely form one visit. They share a client key and
            have gaps of less than {a.id === "chatgpt-user" ? "2" : "30"}{" "}
            minutes.
          </p>
        </div>
        <DetailSection title="Request sequence" label="Observed">
          <div className="request-sequence">
            {steps.map((e, i) => (
              <button key={e.id} onClick={() => open("event", e.id)}>
                <span className="sequence-number">{i + 1}</span>
                <span className="sequence-main">
                  <code>{e.path}</code>
                  <small>
                    {e.time} · {i ? "+2 s" : "First request"}
                    {e.status === 403
                      ? " · Denied"
                      : e.status === 429
                        ? " · Rate limited"
                        : ""}
                    {steps.slice(0, i).some((p) => p.path === e.path)
                      ? " · Repeat of an earlier path"
                      : ""}
                  </small>
                </span>
                <span
                  className={`http-code ${e.status >= 400 ? "error" : "ok"}`}
                >
                  {e.status}
                </span>
                <ChevronRight size={12} />
              </button>
            ))}
          </div>
        </DetailSection>
        <div className="outcome-panel">
          <Label type="Unknown" />
          <h3>Task outcome is unknown</h3>
          <p>
            Request logs show pages reached and response codes. They cannot show
            whether the task was completed.
          </p>
        </div>
        <DetailSection title="Evidence gaps" label="Unknown">
          <ul className="plain-list">
            <li>Page content, clicks, and form input are not recorded.</li>
            {a.id === "chatgpt-user" && (
              <li>A shared IP may contain more than one agent.</li>
            )}
            <li>Session grouping is an inference from request timing.</li>
          </ul>
        </DetailSection>
      </>
    );
  }
  if (type === "event") {
    const e = events.find((e) => e.id === id);
    if (!e) return <p>There is no sample request for this ID.</p>;
    const a = agents.find((a) => a.id === e.agentId)!,
      s = sessions.find((s) => s.id === e.sessionId)!,
      siblings = events.filter((x) => x.sessionId === s.id),
      file = imports.find(
        (r) => r.source === (e.source === "Origin" ? "Origin" : "CDN"),
      )!,
      at = siblings.findIndex((x) => x.id === e.id);
    return (
      <>
        <div className="request-heading">
          <span className="method">GET</span>
          <code>{e.path}</code>
          <span className={`http-code ${e.status >= 400 ? "error" : "ok"}`}>
            {e.status}
          </span>
        </div>
        <DetailSection title="Request" label="Observed">
          <Fields
            items={[
              ["Time", `Oct 16, 2026 · ${e.time} UTC`],
              ["Host", "example.com"],
              [
                "Response",
                `${e.status} ${e.status === 403 ? "Forbidden" : e.status === 429 ? "Too Many Requests" : "OK"}`,
              ],
              ["Response time", `${e.duration} ms`],
              ["Bytes", e.bytes],
              ["Referrer", e.step === 1 ? "None" : "https://example.com/cards"],
              ["User agent", `${a.name}/1.0 (sample)`],
              ["Client IP", "192.0.2.24 · documentation address"],
            ]}
          />
        </DetailSection>
        <DetailSection title="Source" label="Observed">
          <Fields
            items={[
              ["Record type", e.source],
              [
                "CDN / origin status",
                e.source === "Paired"
                  ? `${e.status} / ${e.status}`
                  : e.source === "CDN"
                    ? `${e.status} / not reached`
                    : `Unknown / ${e.status}`,
              ],
              [
                "Import run",
                <TextLink key="import" onClick={() => open("import", file.id)}>
                  {file.id}
                </TextLink>,
              ],
              [
                "File / line",
                `${file.file.replace("bank-", "example-")} · line ${1240 + e.step}`,
              ],
            ]}
          />
        </DetailSection>
        <DetailSection title="Identity & classification" label="Inferred">
          <Fields
            items={[
              [
                "Identity",
                a.verdict === "VERIFIED"
                  ? a.name
                  : `Claims to be ${a.name}, unverified`,
              ],
              ["Verdict", <Status key="verdict" value={a.verdict} />],
              [
                "Method",
                a.verdict === "VERIFIED"
                  ? "IP list · matched sample snapshot"
                  : "User agent claim · no verified IP match",
              ],
              ["Class", <ClassName key="class" id={a.classId} full />],
              ["Confidence", a.confidence],
              ["Rule / registry", "v3 / v12 · checked Oct 16 at 14:00"],
              [
                "Verdict row",
                <TextLink key="verdictrow" onClick={() => open("agent", a.id)}>
                  #204 · view agent history
                  <ArrowUpRight size={12} />
                </TextLink>,
              ],
            ]}
          />
        </DetailSection>
        <DetailSection title="Session">
          <button
            className="detail-related-link"
            onClick={() => open("session", s.id)}
          >
            <span>
              <code>{s.id}</code>
              <small>
                Request {e.step} of {s.requests} · {a.name}
              </small>
            </span>
            <ArrowRight size={16} />
          </button>
          <div className="sibling-nav">
            <button
              disabled={at === 0}
              onClick={() => open("event", siblings[at - 1].id)}
            >
              <ArrowLeft size={13} />
              Previous request
            </button>
            <button
              disabled={at === siblings.length - 1}
              onClick={() => open("event", siblings[at + 1].id)}
            >
              Next request
              <ArrowRight size={13} />
            </button>
          </div>
        </DetailSection>
        <div className="detail-notice">
          <Info size={14} />
          <p>
            {e.status === 200
              ? "HTTP 200 confirms the response code. It does not prove that the task was completed."
              : "This status is observed. Its effect on the agent’s task is unknown."}
          </p>
        </div>
      </>
    );
  }
  if (type === "page") {
    const p = pages.find((p) => p.id === id);
    if (!p) return <p>There is no sample page for this ID.</p>;
    return (
      <>
        <div className="detail-chips">
          {p.tag && <span className="page-tag">{p.tag}</span>}
          <span className="muted">
            <Check size={12} />
            In sitemap
          </span>
          <Status value="Allowed by policy" />
        </div>
        <DetailSection title="Page traffic" label="Observed">
          <div className="detail-metrics">
            <CountLink href={href("/events", { path: p.path })}>
              <strong>{number(p.requests)}</strong>agent requests
            </CountLink>
            <CountLink href={href("/sessions", { path: p.path })}>
              <strong>{number(p.sessions)}</strong>sessions
            </CountLink>
            <CountLink
              href={href("/events", { path: p.path, status: "denied" })}
            >
              <strong>{p.blocks}%</strong>denial rate
            </CountLink>
          </div>
        </DetailSection>
        <DetailSection title="Response by traffic class" label="Observed">
          <div className="detail-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Class</th>
                  <th>Requests</th>
                  <th>Typical status</th>
                </tr>
              </thead>
              <tbody>
                {classes.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <ClassName id={c.id} />
                    </td>
                    <td>
                      <NumberLink
                        value={Math.round((p.requests * c.share) / 100)}
                        href={href("/events", {
                          path: p.path,
                          class: String(c.id),
                        })}
                      />
                    </td>
                    <td>
                      <span
                        className={`http-code ${p.blocks > 10 && c.id === 2 ? "error" : "ok"}`}
                      >
                        {p.blocks > 10 && c.id === 2 ? 403 : 200}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DetailSection>
        <DetailSection title="Page signals" label="Observed">
          <Fields
            items={[
              ["Errors", `${p.errors.toFixed(1)}%`],
              ["Denied requests", `${p.blocks.toFixed(1)}% · HTTP 403 / 429`],
              ["Retries", p.retries],
              ["Median response size", p.bytes],
              ["Access policy", "Allowed · robots.txt snapshot Oct 16"],
            ]}
          />
        </DetailSection>
        <DetailSection title="Related recommendations">
          <div className="detail-link-list">
            {recommendations
              .filter((r) => r.target.split(" → ").includes(p.path))
              .map((r) => (
                <button key={r.id} onClick={() => open("recommendation", r.id)}>
                  <span>{r.title}</span>
                  <ChevronRight size={13} />
                </button>
              ))}
            {!recommendations.some((r) =>
              r.target.split(" → ").includes(p.path),
            ) && (
              <p className="muted">
                No open sample recommendation for this page.
              </p>
            )}
          </div>
        </DetailSection>
        <Link
          className="detail-related-link"
          href={href("/sessions", { path: p.path })}
        >
          Inspect sessions on this page
          <ArrowRight size={16} />
        </Link>
        <div className="outcome-panel">
          <Label type="Unknown" />
          <p>
            Page content and task completion cannot be measured from request
            logs.
          </p>
        </div>
      </>
    );
  }
  if (type === "journey") {
    const j = journeys.find((j) => j.id === id);
    if (!j) return <p>No sample journey for this ID.</p>;
    return (
      <>
        <div className="detail-chips">
          <span className="page-tag">
            {j.critical ? "Critical journey" : "Standard journey"}
          </span>
          <Label />
        </div>
        <p className="detail-lead">{j.description}.</p>
        <DetailSection title="Journey steps" label="Observed">
          <div className="journey-detail-steps">
            {j.steps.map((p, i) => (
              <div key={p}>
                <span className="sequence-number">{i + 1}</span>
                <code>{p}</code>
                <CountLink
                  href={href("/sessions", {
                    journey: j.id,
                    reached: String(i + 1),
                  })}
                >
                  {number(j.counts[i])} reached
                  <ArrowUpRight size={12} />
                </CountLink>
              </div>
            ))}
          </div>
        </DetailSection>
        <DetailSection title="Reached by traffic class" label="Observed">
          <div className="detail-table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Class</th>
                  {j.steps.map((_, i) => (
                    <th key={i}>Step {i + 1}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {classes.slice(0, 4).map((c, i) => (
                  <tr key={c.id}>
                    <td>
                      <ClassName id={c.id} />
                    </td>
                    {j.counts.map((count, k) => (
                      <td key={k}>
                        <NumberLink
                          value={Math.round(count * [0.24, 0.48, 0.08, 0.2][i])}
                          href={href("/sessions", {
                            journey: j.id,
                            class: String(c.id),
                            reached: String(k + 1),
                          })}
                        />
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </DetailSection>
        <Fields
          items={[
            ["Retries / loops", `${j.retry} sessions`],
            ["Main retry step", j.steps[1]],
            ["Session grouping", "Same client + time gap · inferred"],
          ]}
        />
        <div className="outcome-panel">
          <Label type="Unknown" />
          <h3>Reaching a page does not prove completion</h3>
          <p>
            A simulation is needed to inspect the task outcome, content, and
            form steps.
          </p>
        </div>
      </>
    );
  }
  if (type === "import") {
    const r = imports.find((r) => r.id === id);
    if (!r) return <p>There is no sample import for this ID.</p>;
    return (
      <>
        <div className="detail-chips">
          <Status value={r.status} />
          <span>{r.source} · example.com</span>
        </div>
        <DetailSection title="Import file" label="Observed">
          <Fields
            items={[
              [
                "File",
                <code key="file">{r.file.replace("bank-", "example-")}</code>,
              ],
              ["Received", `Oct 16, ${r.received}`],
              ["Lines", number(r.lines)],
              ["Imported", number(r.imported)],
              ["Rejected", r.rejected],
              ["Duplicates skipped", r.duplicates],
              [
                "Cleanup date",
                r.status === "Failed"
                  ? "Retained until a complete import"
                  : "Oct 23, 2026",
              ],
            ]}
          />
        </DetailSection>
        {r.status === "Failed" ? (
          <div className="error-notice">
            <CircleAlert size={16} />
            <div>
              <strong>File could not be read</strong>
              <p>Sample error: invalid file header. The file is retained.</p>
            </div>
          </div>
        ) : (
          <DetailSection title="Rejected lines" label="Observed">
            <Fields
              items={
                r.rejected
                  ? [
                      ["Line 2,410", "Invalid timestamp"],
                      ["Line 3,092", "Missing request path"],
                    ]
                  : [["Rejected lines", "None"]]
              }
            />
            <p className="muted">
              Only line numbers and reasons are stored. Raw rejected text is not
              shown.
            </p>
          </DetailSection>
        )}
        <div className="detail-notice">
          <Info size={14} />
          <p>Import actions are unavailable in this read-only sample.</p>
        </div>
      </>
    );
  }
  if (type === "run") {
    const r = runs.find((r) => r.id === id);
    if (!r) return <p>There is no sample pipeline run for this ID.</p>;
    const failed = r.status === "Failed";
    return (
      <>
        <div className="detail-chips">
          <Status value={r.status} />
          <span>{r.lane} lane</span>
        </div>
        <DetailSection title="Run summary" label="Observed">
          <Fields
            items={[
              ["Run ID", r.id],
              ["Started", `Oct 16, 2026 · ${r.started}`],
              ["Duration", r.duration],
              ["Processed", r.count],
            ]}
          />
        </DetailSection>
        <DetailSection title="Run steps" label="Observed">
          <div className="pipeline-steps">
            {(r.lane === "Fast"
              ? ["Import", "Pair", "Verify", "Classify", "Build views"]
              : [
                  "Find patterns",
                  "Score candidates",
                  "Build fact bundles",
                  "Write template text",
                  "Save recommendations",
                ]
            ).map((step, i) => (
              <div key={step}>
                <span
                  className={`pipeline-check ${failed && i === 2 ? "failed" : ""}`}
                >
                  {failed && i === 2 ? (
                    <CircleAlert size={14} />
                  ) : failed && i > 2 ? (
                    <span>—</span>
                  ) : (
                    <Check size={14} />
                  )}
                </span>
                <strong>{step}</strong>
                <span className="muted">
                  {failed && i === 2
                    ? `Connection error · ${r.stepSeconds[i]} s`
                    : failed && i > 2
                      ? "Not run"
                      : `${r.stepSeconds[i]} s`}
                </span>
                <Status
                  value={
                    failed && i === 2
                      ? "Failed"
                      : failed && i > 2
                        ? "Skipped"
                        : "Complete"
                  }
                />
              </div>
            ))}
          </div>
        </DetailSection>
        {failed && (
          <div className="error-notice">
            <CircleAlert size={16} />
            <div>
              <strong>Stopped at Verify</strong>
              <p>
                Sample error: database connection was unavailable. Earlier steps
                kept their records. Later steps did not run.
              </p>
            </div>
          </div>
        )}
        <p className="muted">
          This run is a saved sample. No background process is active.
        </p>
      </>
    );
  }
  return (
    <>
      <p className="detail-lead">
        Separate what the logs show from what we infer.
      </p>
      <div className="label-guide">
        <div>
          <Label />
          <h3>Directly recorded</h3>
          <p>
            Request counts, paths, status codes, timestamps, response sizes, and
            identity check results.
          </p>
        </div>
        <div>
          <Label type="Inferred" />
          <h3>Based on rules and evidence</h3>
          <p>
            Traffic class, session grouping, confidence, priority, and potential
            issues. Open a detail to inspect the inputs.
          </p>
        </div>
        <div>
          <Label type="Unknown" />
          <h3>Not visible in the data</h3>
          <p>
            Task completion, intent, content understanding, clicks, form steps,
            and edge blocks without a CDN log.
          </p>
        </div>
      </div>
      <DetailSection title="The six traffic classes">
        <div className="detail-link-list">
          {classes.map((c) => (
            <Link key={c.id} href={href("/events", { class: String(c.id) })}>
              <ClassName id={c.id} full />
              <ArrowUpRight size={12} />
            </Link>
          ))}
        </div>
      </DetailSection>
      <div className="detail-notice">
        <ShieldCheck size={15} />
        <p>
          A claimed identity is not verified until its check returns VERIFIED.
          HTTP 200 is a response code, not a task outcome.
        </p>
      </div>
    </>
  );
}
// The identity check result, stated so a claim never reads as a fact.
function identityFact(agent: (typeof agents)[number]) {
  const text =
    agent.verdict === "VERIFIED"
      ? `The ${agent.name} identity check returned VERIFIED.`
      : agent.verdict === "CLAIMED"
        ? `These clients claim to be ${agent.name}. The identity check did not verify the claim.`
        : `The client identity is unknown. No identity check applies.`;
  return { source: "Identity check", text };
}
function RecommendationDetail({
  r,
  href,
  open,
  run,
}: {
  r: Recommendation;
  href: Href;
  open: OpenDetail;
  run: number;
}) {
  // Run #13 predates rec-01 and rec-04; rec-05 was new in that run.
  const absent = run === 13 && ["rec-01", "rec-04"].includes(r.id);
  const status =
    run === 13 ? (r.id === "rec-05" ? "New" : "Still open") : r.status;
  const runWindow = run === 13 ? "02:00–08:00" : "08:00–14:00";
  const agent = agents.find((a) => a.id === r.agentId)!;
  const evidence = events.filter((e) => r.sessionIds.includes(e.sessionId));
  const sourceEvent =
    evidence.find(
      (e) => e.status >= 400 && r.target.split(" → ").includes(e.path),
    ) || evidence.find((e) => r.target.endsWith(e.path));
  return (
    <>
      <div className="detail-chips">
        {!absent && <Status value={status} />}
        <span className="pattern-badge">{r.pattern}</span>
        <span className="muted">Run #{run}</span>
      </div>
      {absent && (
        <div className="detail-notice">
          <Info size={14} />
          <p>
            This recommendation is not in run #{run}. It first appears in run
            #14. The evidence below is from run #14.
          </p>
        </div>
      )}
      <div className="target-path">
        <span>Recommended journey</span>
        <code>{r.target}</code>
      </div>
      <DetailSection title="Why test this" label="Inferred">
        <p className="detail-why">{r.why}</p>
      </DetailSection>
      <DetailSection title="What the data shows" label="Observed">
        <ul className="fact-list">
          {[...r.facts, identityFact(agent)].map((f) => (
            <li key={f.text}>
              <span>{f.text}</span>
              <small>{f.source}</small>
            </li>
          ))}
        </ul>
      </DetailSection>
      <DetailSection title="Evidence to inspect" label="Observed">
        <p className="muted">
          Run #{absent ? 14 : run} ({absent ? "08:00–14:00" : runWindow}) has{" "}
          {r.sessions} matching sessions and {r.events} requests. This sample
          workspace keeps {r.sessionIds.length} of the sessions.
        </p>
        <div className="detail-link-list">
          {r.sessionIds.map((sid) => {
            const s = sessions.find((s) => s.id === sid)!;
            return (
              <button key={sid} onClick={() => open("session", sid)}>
                <code>{sid}</code>
                <span>
                  Sample session · {s.requests} requests
                  {s.retry ? " · has retries" : ""}
                </span>
                <ChevronRight size={14} />
              </button>
            );
          })}
          {sourceEvent && (
            <button onClick={() => open("event", sourceEvent.id)}>
              <code>{sourceEvent.path}</code>
              <span>
                {sourceEvent.status >= 400
                  ? `Request that got HTTP ${sourceEvent.status}`
                  : `Request to the target page · HTTP ${sourceEvent.status}`}
              </span>
              <ChevronRight size={14} />
            </button>
          )}
        </div>
        <div className="evidence-actions">
          <Link href={href("/sessions", { rec: r.id })}>
            Sample sessions ({r.sessionIds.length})
            <ArrowUpRight size={14} />
          </Link>
          <Link href={href("/events", { rec: r.id })}>
            Sample requests ({evidence.length})
            <ArrowUpRight size={14} />
          </Link>
        </div>
      </DetailSection>
      <DetailSection title="Suggested validation">
        <p>{r.validation}</p>
      </DetailSection>
      <DetailSection title="Priority" label="Inferred">
        <div className="priority-formula">
          <strong>{r.score}</strong>
          <span>=</span>
          <span>
            3<small>Impact</small>
          </span>
          <span>×</span>
          <span>
            {r.frequency}
            <small>Frequency</small>
          </span>
          <span>×</span>
          <span>
            {r.severity}
            <small>Severity</small>
          </span>
          <span>×</span>
          <span>
            {r.confidence === "High" ? "1.0" : "0.6"}
            <small>Confidence</small>
          </span>
        </div>
        <Fields
          items={[
            ["Impact · 3", "Target is a key or conversion page."],
            [
              `Frequency · ${r.frequency}`,
              r.sessions > 50
                ? "More than 50 affected sessions."
                : r.sessions >= 5
                  ? "5–50 affected sessions."
                  : "Fewer than 5 affected sessions.",
            ],
            [
              `Severity · ${r.severity}`,
              r.severity === 3
                ? "Blocked access or repeated navigation."
                : "Discovery or full-journey gap.",
            ],
            [
              "Confidence",
              r.confidence === "High"
                ? "High · verified identity, IP not shared."
                : "Medium · identity or grouping is not fully verified.",
            ],
          ]}
        />
      </DetailSection>
      <div className="outcome-panel">
        <h3>Suggested next step</h3>
        <p>{r.next}</p>
      </div>
      <details className="fact-bundle">
        <summary>
          <ChevronRight size={13} />
          Inspect the fact bundle
        </summary>
        <Fields
          items={[
            ["Pattern rule", r.rule],
            ["Target", <code key="target">{r.target}</code>],
            ["Evidence", `${r.sessions} sessions · ${r.events} events`],
            ["Access policy", "Allows crawler access"],
            ["Versions", "Rule v3 · registry v12 · prompt v2"],
            ["Text source", "Template text · fixed sample"],
          ]}
        />
      </details>
      <DetailSection title="History">
        <p className="muted">
          {r.history}. The stored evidence stays linked to this run.
        </p>
      </DetailSection>
      <div className="detail-footer">
        <span>Template text</span>
        <span>Sample data · Oct 16, 2026 at 14:02</span>
      </div>
    </>
  );
}
