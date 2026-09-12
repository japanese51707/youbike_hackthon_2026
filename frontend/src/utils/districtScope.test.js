import test from "node:test";
import assert from "node:assert/strict";
import {
  CITY_SCOPE,
  convexHull,
  countScopedCoverage,
  districtOutline,
  filterByDistrict,
  isCityScope,
  listDistricts,
  outlineBounds,
} from "./districtScope.js";

const stations = [
  { station_id: "a", district: "中和區", lat: 25.0, lng: 121.5 },
  { station_id: "b", district: "板橋區", lat: 25.01, lng: 121.46 },
  { station_id: "c", district: "板橋區", lat: 25.02, lng: 121.47 },
];

test("lists unique districts in Traditional Chinese order", () => {
  assert.deepEqual(listDistricts(stations), ["中和區", "板橋區"]);
});

test("city scope keeps every row; a district drops the others", () => {
  assert.equal(isCityScope(CITY_SCOPE), true);
  assert.equal(filterByDistrict(stations, CITY_SCOPE).length, 3);
  assert.deepEqual(
    filterByDistrict(stations, "板橋區").map((row) => row.station_id),
    ["b", "c"],
  );
});

test("convex hull keeps the outer square and drops the interior point", () => {
  const hull = convexHull([
    [0, 0],
    [2, 0],
    [2, 2],
    [0, 2],
    [1, 1],
  ]);
  assert.equal(hull.length, 4);
  assert.deepEqual(hull.sort((a, b) => a[0] - b[0] || a[1] - b[1]), [
    [0, 0],
    [0, 2],
    [2, 0],
    [2, 2],
  ]);
});

test("official catalog wins over the station hull", () => {
  const catalog = {
    板橋區: [
      [
        [
          [121.4, 25.0],
          [121.5, 25.0],
          [121.5, 25.1],
          [121.4, 25.1],
          [121.4, 25.0],
        ],
      ],
    ],
  };
  const outline = districtOutline("板橋區", stations, catalog);
  assert.equal(outline.source, "town-boundary");
  assert.deepEqual(outlineBounds(outline.polygons), [
    [121.4, 25.0],
    [121.5, 25.1],
  ]);
  assert.equal(districtOutline(CITY_SCOPE, stations, catalog), null);
});

test("missing catalog falls back to a padded station hull", () => {
  const clustered = [
    { district: "板橋區", lat: 25.0, lng: 121.46 },
    { district: "板橋區", lat: 25.0, lng: 121.48 },
    { district: "板橋區", lat: 25.02, lng: 121.48 },
    { district: "板橋區", lat: 25.02, lng: 121.46 },
  ];
  const outline = districtOutline("板橋區", clustered, {});
  assert.equal(outline.source, "station-hull");
  assert.ok(outline.polygons[0][0].length >= 4);
});

test("scoped coverage counts only stations inside the current set", () => {
  const scoped = filterByDistrict(stations, "板橋區");
  const coverage = countScopedCoverage({
    stations: scoped,
    mode: "past",
    historyFrame: { stations: [{ station_id: "b", available_bikes: 4 }] },
  });
  assert.equal(coverage.covered, 1);
  assert.equal(coverage.available, 1);
});
