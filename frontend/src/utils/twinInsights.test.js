import test from "node:test";
import assert from "node:assert/strict";
import { getisOrdGiStar } from "./spatialStats.js";
import {
  TWIN_INSIGHT,
  buildFlowInsight,
  buildGaugeInsight,
  buildNetworkInsight,
  buildTwinInsights,
  cityWideGate,
  districtStatusRows,
} from "./twinInsights.js";

function station(id, lat, lng, extra = {}) {
  const docks = extra.total_docks ?? 20;
  const bikes = extra.available_bikes ?? 10;
  const usage = extra.usage_rate ?? Math.round((bikes / docks) * 1000) / 10;
  return {
    station_id: id,
    station_name: extra.station_name ?? `站${id}`,
    district: extra.district ?? "板橋區",
    lat,
    lng,
    total_docks: docks,
    available_bikes: bikes,
    available_docks: docks - bikes,
    usage_rate: usage,
    status: extra.status ?? "normal",
    observed_at: extra.observed_at ?? "2026-09-12T08:00:00+08:00",
  };
}

function cluster(prefix, lat0, lng0, count, extra) {
  return Array.from({ length: count }, (_, i) =>
    station(`${prefix}-${i}`, lat0 + i * 0.001, lng0 + (i % 5) * 0.001, extra),
  );
}

test("district scope rewrites the gate and gauge wording", () => {
  const stations = cluster("a", 25.01, 121.46, 8, { district: "板橋區", status: "empty", available_bikes: 0, usage_rate: 0 });
  const gate = cityWideGate({ mode: "past", stations, temporalCovered: 1, temporalAvailable: 2, scopeLabel: "板橋區" });
  assert.match(gate.reason, /板橋區結論已關閉/);
  const insight = buildGaugeInsight(stations, "板橋區");
  assert.match(insight.findings[0], /板橋區 8 站/);
});

test("city-wide gate stays closed when the time machine is not live", () => {
  const stations = cluster("a", 25.01, 121.46, 20, { status: "empty", available_bikes: 0, usage_rate: 0 });
  const gate = cityWideGate({ mode: "past", stations, temporalCovered: 2, temporalAvailable: 8 });
  assert.equal(gate.cityWideOk, false);
  assert.match(gate.reason, /全市結論已關閉/);
});

test("city-wide gate opens on live snapshots with enough stations", () => {
  const stations = cluster("a", 25.01, 121.46, 8, {});
  const gate = cityWideGate({ mode: "live", stations, temporalCovered: 0, temporalAvailable: 0 });
  assert.equal(gate.cityWideOk, true);
});

test("gauge insight reports empty-rate and the worst district", () => {
  const stations = [
    ...cluster("banqiao", 25.01, 121.46, 6, { district: "板橋區", status: "empty", available_bikes: 0, usage_rate: 0 }),
    ...cluster("xindian", 24.97, 121.54, 6, { district: "新店區", status: "normal", available_bikes: 10, usage_rate: 50 }),
  ];
  const insight = buildGaugeInsight(stations);
  assert.equal(insight.dataMode, "real");
  assert.equal(insight.metrics[0].value, 50);
  assert.match(insight.findings.join(""), /空站最集中在板橋區/);
  const ranked = districtStatusRows(stations);
  assert.equal(ranked[0].district, "板橋區");
});

test("past mode builds no city-wide findings even if layers are on", () => {
  const stations = cluster("a", 25.01, 121.46, 12, { status: "empty", available_bikes: 0, usage_rate: 0 });
  const report = buildTwinInsights({
    stations,
    activeLayers: ["gauge", "voronoi"],
    mode: "past",
    temporalCovered: 2,
    temporalAvailable: 8,
  });
  assert.equal(report.cityWideOk, false);
  assert.equal(report.layers.every((layer) => layer.findings.length === 0), true);
});

test("network centrality is a real computation on actual station coordinates", () => {
  const stations = [
    ...cluster("banqiao", 25.01, 121.46, 5, { district: "板橋區" }),
    ...cluster("xindian", 24.97, 121.54, 5, { district: "新店區" }),
  ];
  const insight = buildNetworkInsight(stations);
  assert.equal(insight.dataMode, "real");
  assert.ok(insight.metrics[0].value >= 1);
  assert.match(insight.caveats.join(""), /實際站點座標實算/);
});

test("flow concludes only as illustrative pairing", () => {
  const insight = buildFlowInsight([
    { station_id: "P1", station_name: "取1", action: "取車", district: "板橋區", lat: 25.01, lng: 121.46, quantity: 10 },
    { station_id: "D1", station_name: "補1", action: "補車", district: "板橋區", lat: 25.012, lng: 121.462, quantity: 8 },
  ]);
  assert.equal(insight.dataMode, "method");
  assert.match(insight.findings[0], /同區最近/);
  assert.match(insight.caveats.join(""), /不是真實借還 OD/);
  const mockInsight = buildFlowInsight(
    [
      { station_id: "P1", station_name: "取1", action: "取車", district: "板橋區", lat: 25.01, lng: 121.46, quantity: 10 },
      { station_id: "D1", station_name: "補1", action: "補車", district: "板橋區", lat: 25.012, lng: 121.462, quantity: 8 },
    ],
    { source: "status-mock" },
  );
  assert.match(mockInsight.findings[0], /示意取→補/);
  assert.match(mockInsight.caveats.join(""), /mock 配對/);
});

test("high coverage past snapshots can open city-wide conclusions", () => {
  const stations = cluster("a", 25.01, 121.46, 10, { status: "empty", available_bikes: 0, usage_rate: 0 });
  const gate = cityWideGate({ mode: "past", stations, temporalCovered: 9, temporalAvailable: 10 });
  assert.equal(gate.cityWideOk, true);
  const report = buildTwinInsights({
    stations,
    liveStations: stations.map((s) => ({ ...s, status: "normal", available_bikes: 10, usage_rate: 50 })),
    activeLayers: ["gauge"],
    mode: "past",
    temporalCovered: 9,
    temporalAvailable: 10,
  });
  assert.equal(report.cityWideOk, true);
  assert.ok(report.headline);
});

test("Gi* tags method below the sample floor and real at city scale", () => {
  const small = buildTwinInsights({
    stations: cluster("s", 25.01, 121.46, 12, { status: "empty", available_bikes: 0, usage_rate: 0 }),
    activeLayers: ["voronoi"],
    mode: "live",
  });
  assert.equal(small.layers[0].dataMode, "method");

  const hot = cluster("hot", 25.01, 121.46, 40, { status: "empty", available_bikes: 0, usage_rate: 0 });
  const cold = cluster("cold", 25.08, 121.55, 40, { status: "normal", available_bikes: 10, usage_rate: 50 });
  const large = buildTwinInsights({
    stations: [...hot, ...cold],
    activeLayers: ["voronoi"],
    mode: "live",
  });
  assert.ok(large.nStations >= TWIN_INSIGHT.giRealMinStations);
  assert.equal(large.layers[0].dataMode, "real");
  assert.ok(large.layers[0].metrics[0].value >= 1);
});

test("indexed Gi* still flags a tight high-pressure cluster", () => {
  const hot = cluster("hot", 25.012, 121.462, 8, { status: "empty", available_bikes: 0, usage_rate: 0 });
  const cold = cluster("cold", 25.08, 121.55, 8, { status: "normal", available_bikes: 10, usage_rate: 50 });
  const gi = getisOrdGiStar([...hot, ...cold], { radiusKm: 3 });
  const hotZ = gi.filter((row) => String(row.station.station_id).startsWith("hot"));
  assert.ok(hotZ.some((row) => row.z > 1.5));
});
