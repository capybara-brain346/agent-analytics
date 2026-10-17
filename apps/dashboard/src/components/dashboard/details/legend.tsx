"use client";

import Link from "next/link";
import { ArrowUpRight, ShieldCheck } from "lucide-react";
import { classMeta as classes } from "@/lib/classes";
import { ClassName, Href, Label } from "../shared";
import { DetailSection } from "./common";

export function LegendDetail({ href }: { href: Href }) {
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
