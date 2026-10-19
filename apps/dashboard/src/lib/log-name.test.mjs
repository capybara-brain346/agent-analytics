import assert from "node:assert/strict";
import test from "node:test";
import { parseLogName } from "./log-name.ts";

test("parseLogName reads site, source and start; other names give null", () => {
  assert.deepEqual(
    parseLogName("shop_eu__cdn__20261001T0930Z__gptbot-burst.log.gz"),
    {
      site: "shop_eu",
      source: "cdn",
      start: "2026-10-01T09:30:00Z",
      label: "gptbot-burst",
    },
  );
  assert.equal(parseLogName("example__origin__20261001T0000Z.log").label, null);
  assert.equal(parseLogName("access.log"), null);
  assert.equal(parseLogName("example__cdn__2026-10-01.log"), null);
});
