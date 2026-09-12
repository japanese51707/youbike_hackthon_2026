import test from "node:test";
import assert from "node:assert/strict";
import { GI_STAR_RAMP, giStarFillColor, interpolateColorRange } from "./spatialStats.js";

test("Gi* 漸層在端點與 0 使用固定色，中間會插值", () => {
  assert.deepEqual(giStarFillColor(-3).slice(0, 3), GI_STAR_RAMP[0][1]);
  assert.deepEqual(giStarFillColor(0).slice(0, 3), GI_STAR_RAMP[2][1]);
  assert.deepEqual(giStarFillColor(3).slice(0, 3), GI_STAR_RAMP[4][1]);
  const midHot = giStarFillColor(0.98);
  assert.ok(midHot[0] > GI_STAR_RAMP[2][1][0]);
  assert.ok(midHot[0] < GI_STAR_RAMP[3][1][0]);
});

test("color range interpolates from the first stop to the last", () => {
  const ramp = [
    [0, 0, 0],
    [100, 50, 0],
    [200, 100, 0],
  ];
  assert.deepEqual(interpolateColorRange(ramp, 0).slice(0, 3), [0, 0, 0]);
  assert.deepEqual(interpolateColorRange(ramp, 1).slice(0, 3), [200, 100, 0]);
  const mid = interpolateColorRange(ramp, 0.5);
  assert.deepEqual(mid.slice(0, 3), [100, 50, 0]);
});
