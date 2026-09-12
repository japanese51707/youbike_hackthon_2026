import test from "node:test";
import assert from "node:assert/strict";
import { pairDispatchFlows, flowPairStats } from "./twinFlow.js";

test("pairs each pickup to the nearest unused dropoff in the same district", () => {
  const pairs = pairDispatchFlows([
    { station_id: "P1", station_name: "取1", action: "取車", district: "板橋區", lat: 25.01, lng: 121.46, quantity: 10 },
    { station_id: "Dfar", station_name: "遠補", action: "補車", district: "新店區", lat: 24.96, lng: 121.54, quantity: 8 },
    { station_id: "Dnear", station_name: "近補", action: "補車", district: "板橋區", lat: 25.012, lng: 121.462, quantity: 6 },
  ]);
  assert.equal(pairs.length, 1);
  assert.equal(pairs[0].to.station_id, "Dnear");
  assert.equal(pairs[0].sameDistrict, true);
  assert.equal(flowPairStats(pairs).sameDistrictShare, 100);
});

test("does not invent pairs when only dropoffs exist", () => {
  assert.deepEqual(pairDispatchFlows([
    { station_id: "D1", action: "補車", district: "板橋區", lat: 25.01, lng: 121.46, quantity: 4 },
  ]), []);
});
