import assert from "node:assert/strict";
import test from "node:test";
import {
  DISTRICT_MAP_FIT,
  DISTRICT_SHAPES,
  clampMapView,
  easeInOutCubic,
  isFitView,
  lerpMapView,
  panMapView,
  viewForDistrict,
  zoomMapView,
} from "./districtPressureMap.js";

test("zoom stays on the cursor and can return to the full city view", () => {
  const fit = DISTRICT_MAP_FIT;
  const zoomed = zoomMapView(fit, { x: 180, y: 215, factor: 0.5 });
  assert.equal(isFitView(zoomed), false);
  assert.ok(zoomed.w < fit.w);
  assert.ok(Math.abs((180 - zoomed.x) / zoomed.w - 0.5) < 1e-6);
  assert.equal(isFitView(zoomMapView(zoomed, { x: 180, y: 215, factor: 4 })), true);
  const panned = panMapView(zoomed, { dx: 1000, dy: 1000 });
  assert.ok(panned.x + panned.w <= fit.x + fit.w + 1e-6);
  assert.ok(panned.y + panned.h <= fit.y + fit.h + 1e-6);
  assert.deepEqual(clampMapView({ x: -20, y: -20, w: fit.w, h: fit.h }), fit);
});

test("projects all 29 New Taipei districts into SVG paths", () => {
  assert.equal(DISTRICT_SHAPES.length, 29);
  assert.ok(DISTRICT_SHAPES.every((row) => row.district.endsWith("區") && row.d.startsWith("M") && row.bbox));
  assert.ok(DISTRICT_SHAPES.some((row) => row.district === "板橋區"));
});

test("lerpMapView eases from start to end", () => {
  assert.equal(easeInOutCubic(0), 0);
  assert.equal(easeInOutCubic(1), 1);
  assert.ok(easeInOutCubic(0.25) < 0.25);
  assert.ok(easeInOutCubic(0.75) > 0.75);
  const mid = lerpMapView({ x: 0, y: 0, w: 100, h: 100 }, { x: 10, y: 20, w: 50, h: 50 }, 0.5);
  assert.equal(mid.x, 5);
  assert.equal(mid.w, 75);
});

test("viewForDistrict zooms to a district and is smaller than the city", () => {
  const city = DISTRICT_MAP_FIT;
  const banqiao = viewForDistrict("板橋區");
  assert.equal(isFitView(banqiao), false);
  assert.ok(banqiao.w < city.w);
  assert.ok(banqiao.h < city.h);
  assert.deepEqual(viewForDistrict("沒有這個區"), city);
});
