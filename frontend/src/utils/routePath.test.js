import assert from "node:assert/strict";
import test from "node:test";
import {
  dashSegments,
  joinPaths,
  nearestVertexIndex,
  splitPathByWaypoints,
} from "./routePath.js";

test("nearestVertexIndex picks the closest vertex", () => {
  const path = [
    [121.0, 25.0],
    [121.1, 25.0],
    [121.2, 25.0],
  ];
  assert.equal(nearestVertexIndex(path, 121.09, 25.0), 1);
});

test("splitPathByWaypoints keeps later cuts from going backwards", () => {
  const path = [
    [0, 0],
    [1, 0],
    [2, 0],
    [3, 0],
  ];
  const legs = splitPathByWaypoints(path, [
    { lng: 0, lat: 0 },
    { lng: 2, lat: 0 },
    { lng: 3, lat: 0 },
  ]);
  assert.equal(legs.length, 2);
  assert.deepEqual(legs[0][0], [0, 0]);
  assert.deepEqual(legs[0].at(-1), [2, 0]);
  assert.deepEqual(legs[1][0], [2, 0]);
  assert.deepEqual(legs[1].at(-1), [3, 0]);
});

test("joinPaths drops duplicated joints", () => {
  assert.deepEqual(
    joinPaths([
      [
        [0, 0],
        [1, 0],
      ],
      [
        [1, 0],
        [2, 0],
      ],
    ]),
    [
      [0, 0],
      [1, 0],
      [2, 0],
    ],
  );
});

test("dashSegments returns alternating short strokes", () => {
  // 約 111m 的南北向短線，應切出多段虛線而不是整條實線
  const path = [
    [121.0, 25.0],
    [121.0, 25.001],
  ];
  const dashes = dashSegments(path, 0.03, 0.02);
  assert.ok(dashes.length >= 2);
  assert.ok(dashes.every((segment) => segment.length >= 2));
  assert.deepEqual(dashes[0][0], path[0]);
});
