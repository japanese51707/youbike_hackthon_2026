import test from "node:test";
import assert from "node:assert/strict";
import { pairMockFlows, resolveTwinFlowRecommendations } from "./twinFlowMock.js";

function station(id, district, usage, extra = {}) {
  const docks = extra.total_docks ?? 20;
  const bikes = extra.available_bikes ?? Math.round((usage / 100) * docks);
  return {
    station_id: id,
    station_name: `站${id}`,
    district,
    lat: extra.lat ?? 25.01 + (extra.latOff ?? 0),
    lng: extra.lng ?? 121.46 + (extra.lngOff ?? 0),
    status: extra.status ?? (usage <= 0 ? "empty" : usage >= 100 ? "full" : usage >= 75 ? "high" : usage <= 25 ? "low" : "normal"),
    usage_rate: usage,
    total_docks: docks,
    available_bikes: bikes,
    available_docks: docks - bikes,
  };
}

test("mock flows connect one surplus station to several nearby deficits", () => {
  const stations = [
    station("P1", "板橋區", 96, { latOff: 0, lngOff: 0, status: "full" }),
    station("P2", "板橋區", 88, { latOff: 0.004, lngOff: 0.003, status: "high" }),
    station("D1", "板橋區", 4, { latOff: 0.006, lngOff: 0.002, status: "empty" }),
    station("D2", "板橋區", 12, { latOff: 0.008, lngOff: 0.005, status: "low" }),
    station("D3", "板橋區", 18, { latOff: -0.005, lngOff: 0.004, status: "low" }),
  ];
  const pairs = pairMockFlows(stations);
  assert.ok(pairs.length >= 4);
  assert.ok(pairs.some((pair) => pair.from.station_id === "P1" && pair.to.station_id === "D1"));
  assert.ok(new Set(pairs.map((pair) => `${pair.from.station_id}->${pair.to.station_id}`)).size === pairs.length);
});

test("mock flows stay dense when a district has many surplus and deficit stations", () => {
  const stations = Array.from({ length: 16 }, (_, i) =>
    station(`S${i}`, "板橋區", i < 8 ? 90 - i : 8 + (i - 8), {
      latOff: (i % 4) * 0.006,
      lngOff: Math.floor(i / 4) * 0.006,
      status: i < 8 ? "high" : "low",
    }),
  );
  const pairs = pairMockFlows(stations);
  assert.ok(pairs.length >= 20);
});

test("resolve uses the denser status mock even if a single dispatch pair exists", () => {
  const stations = [
    station("P1", "板橋區", 92, { status: "full" }),
    station("D1", "板橋區", 3, { latOff: 0.008, lngOff: 0.006, status: "empty" }),
    station("D2", "板橋區", 10, { latOff: -0.006, lngOff: 0.004, status: "low" }),
  ];
  const resolved = resolveTwinFlowRecommendations({
    stations,
    recommendations: [
      { station_id: "P1", station_name: "取1", action: "取車", district: "板橋區", lat: 25.01, lng: 121.46, quantity: 10 },
      { station_id: "D1", station_name: "補1", action: "補車", district: "板橋區", lat: 25.018, lng: 121.466, quantity: 8 },
    ],
  });
  assert.equal(resolved.source, "status-mock");
  assert.ok(resolved.pairs.length >= 2);
});
