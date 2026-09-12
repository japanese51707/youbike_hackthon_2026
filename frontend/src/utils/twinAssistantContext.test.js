import test from "node:test";
import assert from "node:assert/strict";
import { compactTwinContext, fallbackTwinAnswer } from "./twinAssistantContext.js";

test("compact context keeps insight numbers and drops raw citywide lists", () => {
  const snapshot = Array.from({ length: 8 }, (_, i) => ({
    station_id: `S${i}`,
    station_name: `站${i}`,
    district: i < 5 ? "板橋區" : "新店區",
    status: i < 4 ? "empty" : "normal",
    available_bikes: i < 4 ? 0 : 10,
    total_docks: 20,
    usage_rate: i < 4 ? 0 : 50,
  }));
  const ctx = compactTwinContext(
    {
      mode: "live",
      nStations: 8,
      stationsSource: "backend",
      cityWideOk: true,
      headline: "全市空站率 50%。",
      layers: [
        {
          key: "gauge",
          title: "站點標記",
          dataMode: "real",
          metrics: [{ label: "空站率", value: 50, unit: "%" }],
          findings: ["全市 8 站中，空站 4（50%）。"],
          caveats: [],
          evidence: [{ label: "板橋區", detail: "空站 4/5" }],
        },
      ],
    },
    { snapshot },
  );
  assert.equal(ctx.n_stations, 8);
  assert.equal(ctx.top_empty.length, 4);
  assert.equal(ctx.top_districts[0].district, "板橋區");
  assert.equal(ctx.layers[0].metrics[0].value, 50);
  assert.ok(ctx.analysis_notes.some((note) => note.key === "gauge"));
  assert.ok(ctx.analysis_notes.some((note) => note.key === "voronoi"));
  assert.ok(ctx.analysis_notes.some((note) => note.name === "待接真實資料"));
});

test("local fallback refuses dispatch and can summarize", () => {
  const context = {
    mode: "live",
    n_stations: 8,
    stations_source: "backend",
    city_wide_ok: true,
    headline: "全市空站率 50%。",
    layers: [],
    top_districts: [{ district: "板橋區", empty: 4, count: 5, empty_rate: 80 }],
  };
  assert.match(fallbackTwinAnswer(context, ""), /全市空站率 50%/);
  assert.match(fallbackTwinAnswer(context, "派車去板橋"), /不能決定/);
});
