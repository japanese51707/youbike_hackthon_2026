import assert from "node:assert/strict";
import test from "node:test";
import { nextChaseCopy, parseCaseTime, waitedSince } from "./escalationApi.js";

test("naive opened_at is Taipei, not UTC, so remain is not 450", () => {
  const opened = "2026-09-13T09:19:00";
  const now = Date.parse("2026-09-13T10:20:00+08:00");
  assert.equal(parseCaseTime(opened), Date.parse("2026-09-13T09:19:00+08:00"));
  const waited = waitedSince(opened, now);
  assert.ok(waited > 50 && waited < 70);
  const copy = nextChaseCopy({ opened_at: opened, stage_thresholds: [30, 45, 60] }, now);
  assert.match(copy, /需電話聯絡|需再提示|最高催辦/);
  assert.doesNotMatch(copy, /450/);
});
