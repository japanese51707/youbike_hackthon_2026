import assert from "node:assert/strict";
import test from "node:test";
import { cachedRead, clearResourceCache, peekResource, rememberResource } from "./resourceCache.js";

test("remember then peek returns the same payload", () => {
  clearResourceCache();
  rememberResource("board", { empty: 3 });
  assert.deepEqual(peekResource("board"), { empty: 3 });
});

test("cachedRead reuses fresh value and shares in-flight", async () => {
  clearResourceCache();
  let calls = 0;
  const loader = async () => {
    calls += 1;
    return { n: calls };
  };
  const [a, b] = await Promise.all([
    cachedRead("stations", loader, { ttlMs: 60_000 }),
    cachedRead("stations", loader, { ttlMs: 60_000 }),
  ]);
  assert.deepEqual(a, { n: 1 });
  assert.deepEqual(b, { n: 1 });
  assert.equal(calls, 1);
  const c = await cachedRead("stations", loader, { ttlMs: 60_000 });
  assert.deepEqual(c, { n: 1 });
  assert.equal(calls, 1);
});

test("cachedRead keeps last value when refresh fails", async () => {
  clearResourceCache();
  rememberResource("kpi", { health: 90 });
  const result = await cachedRead("kpi", async () => {
    throw new Error("timeout");
  }, { ttlMs: 0, keepOnError: true });
  assert.deepEqual(result, { health: 90 });
});
