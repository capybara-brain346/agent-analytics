import assert from "node:assert/strict";
import test from "node:test";
import { queryString } from "./client.ts";
import { rangeOf, scopeFromQuery, scopeParams } from "./filters.ts";

const query = (obj) => ({ get: (k) => obj[k] ?? null });

test("queryString leaves out empty values and repeats array keys", () => {
  assert.equal(queryString(), "");
  assert.equal(queryString({ a: "", b: undefined, c: null }), "");
  assert.equal(
    queryString({ site: "s", class: ["1", "2"], flag: false, n: 0 }),
    "?site=s&class=1&class=2&flag=false&n=0",
  );
});

test("scopeFromQuery falls back to the default range", () => {
  assert.deepEqual(scopeFromQuery(query({ range: "bogus", class: "1,2" })), {
    site: "",
    range: "24h",
    classes: "1,2",
  });
  assert.equal(scopeFromQuery(query({ range: "7d" })).range, "7d");
  assert.equal(rangeOf("nope").hours, 24);
});

test("scopeParams builds the window ending at now", () => {
  const now = new Date("2026-10-17T12:00:00Z");
  const p = scopeParams({ site: "", range: "7d", classes: "1,4" }, now);
  assert.equal(p.to, "2026-10-17T12:00:00.000Z");
  assert.equal(p.from, "2026-10-10T12:00:00.000Z");
  assert.equal(p.site, undefined);
  assert.deepEqual(p.class, ["1", "4"]);
  assert.equal(
    scopeParams({ site: "x", range: "1h", classes: "" }, now).class,
    undefined,
  );
});
