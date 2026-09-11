import test from "node:test";
import assert from "node:assert/strict";
import { escapeHtml } from "./escapeHtml.js";
test("external station names cannot inject tooltip HTML", () => {
  assert.equal(escapeHtml('<img src=x onerror="alert(1)">'), '&lt;img src=x onerror=&quot;alert(1)&quot;&gt;');
  assert.equal(escapeHtml("捷運站 & '出口'"), "捷運站 &amp; &#39;出口&#39;");
  assert.equal(escapeHtml(null), "");
});
