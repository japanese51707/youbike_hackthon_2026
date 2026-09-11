import test from "node:test";
import assert from "node:assert/strict";
import { request } from "./httpClient.js";

test("write requests require an explicit actor", async () => {
  await assert.rejects(request("/dispatch/confirm-trip", { method: "POST", actorId: "" }), /選擇操作身分/);
});
test("dispatch confirmation sends the backend reference and actor", async () => {
  const original = globalThis.fetch;
  let seen;
  globalThis.fetch = async (url, options) => { seen = { url, options }; return { ok: true, json: async () => ({ confirmed: true }) }; };
  try {
    const body = { draft_id: "DRAFT-123", version: 1 };
    const result = await request("/dispatch/confirm-trip", { method: "POST", body, actorId: "OP-002" });
    assert.equal(result.confirmed, true);
    assert.equal(seen.url, "/api/v1/dispatch/confirm-trip");
    assert.deepEqual(JSON.parse(seen.options.body), body);
    assert.equal(seen.options.headers["X-Operator-Id"], "OP-002");
  } finally { globalThis.fetch = original; }
});
test("backend conflicts remain errors and preserve the explanation", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => ({ ok: false, status: 409, json: async () => ({ message: "草稿已過期" }) });
  try { await assert.rejects(request("/dispatch/confirm-trip", { method: "POST", actorId: "OP-002" }), e => e.status === 409 && e.message === "草稿已過期"); }
  finally { globalThis.fetch = original; }
});
test("unavailable data never produces a Mock response", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = async () => { throw new TypeError("network failure"); };
  try { await assert.rejects(request("/stations"), /network failure/); }
  finally { globalThis.fetch = original; }
});
