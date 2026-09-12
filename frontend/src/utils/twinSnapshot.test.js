import test from "node:test";
import assert from "node:assert/strict";
import {
  applyUpdates,
  buildTwinView,
  pickTimelineFrame,
  updatesFromRecommendations,
} from "./twinSnapshot.js";

test("recommendation overlay uses the 60-minute arrival horizon", () => {
  const updates = updatesFromRecommendations([
    { station_id: "A", arrival_by_horizon: { 60: 3, 30: 7 }, predicted_at_arrival: 9 },
  ]);
  assert.equal(updates.get("A"), 3);
});

test("history frame overlay only changes stations that appear in the frame", () => {
  const stations = [
    { station_id: "A", total_docks: 20, available_bikes: 10, available_docks: 10, usage_rate: 50, status: "normal" },
    { station_id: "B", total_docks: 20, available_bikes: 10, available_docks: 10, usage_rate: 50, status: "normal" },
  ];
  const applied = applyUpdates(stations, new Map([["A", 0]]));
  assert.equal(applied.covered, 1);
  assert.equal(applied.stations[0].status, "empty");
  assert.equal(applied.stations[1].status, "normal");
});

test("past view prefers a city-wide history frame over temporal mock", () => {
  const view = buildTwinView({
    stations: [
      { station_id: "A", total_docks: 10, available_bikes: 5, available_docks: 5, usage_rate: 50, status: "normal" },
    ],
    mode: "past",
    temporalStations: [],
    historyFrame: { time: "08:00", stations: [{ station_id: "A", available_bikes: 0 }] },
    recommendations: [],
  });
  assert.equal(view.source, "historical-frame");
  assert.equal(view.covered, 1);
  assert.equal(view.stations[0].status, "empty");
});

test("pickTimelineFrame prefers 08:00 when present", () => {
  const frame = pickTimelineFrame({
    frames: [
      { time: "07:00", stations: [] },
      { time: "08:00", stations: [{ station_id: "A" }] },
      { time: "09:00", stations: [] },
    ],
  });
  assert.equal(frame.time, "08:00");
});
