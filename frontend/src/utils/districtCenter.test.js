import assert from "node:assert/strict";
import test from "node:test";
import { districtCenter } from "./districtCenter.js";

test("districtCenter returns a point inside New Taipei for known districts", () => {
  const sanzhi = districtCenter("三芝區");
  assert.ok(sanzhi);
  assert.ok(sanzhi.lat > 25.1 && sanzhi.lat < 25.35);
  assert.ok(sanzhi.lng > 121.4 && sanzhi.lng < 121.6);

  const banqiao = districtCenter("板橋區");
  assert.ok(banqiao.lat > 24.9 && banqiao.lat < 25.1);
  assert.ok(banqiao.lng > 121.4 && banqiao.lng < 121.5);
});

test("districtCenter is stable and ignores unknown names", () => {
  assert.equal(districtCenter("三芝區"), districtCenter("三芝區"));
  assert.equal(districtCenter(""), null);
  assert.equal(districtCenter("火星區"), null);
});
