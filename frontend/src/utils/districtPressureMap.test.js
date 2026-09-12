import assert from "node:assert/strict";
import test from "node:test";
import { DISTRICT_SHAPES } from "./districtPressureMap.js";

test("projects all 29 New Taipei districts into SVG paths", () => {
  assert.equal(DISTRICT_SHAPES.length, 29);
  assert.ok(DISTRICT_SHAPES.every((row) => row.district.endsWith("區") && row.d.startsWith("M")));
  assert.ok(DISTRICT_SHAPES.some((row) => row.district === "板橋區"));
});
