import test from "node:test";
import assert from "node:assert/strict";
import { deriveServiceGrade, isInRiderServiceArea, recommendNearbyStations, SERVICE_GRADES } from "./riderStations.js";

const origin = { lat: 25.014, lng: 121.463 };

test("捷運大站列為核心站，小型住宅站列為一般站", () => {
  assert.equal(deriveServiceGrade({ station_name: "捷運板橋站", total_docks: 30 }).key, "core");
  assert.equal(deriveServiceGrade({ station_name: "巷口小站", total_docks: 20, area_type: "residential" }).key, "neighbor");
  assert.equal(deriveServiceGrade({ station_name: "運動中心", total_docks: 36 }).key, "priority");
});

test("新竹座標不在找車服務範圍，板橋在範圍內", () => {
  const banqiao = { lat: 25.01427, lng: 121.46256 };
  const hsinchu = { lat: 24.8067, lng: 120.9686 };
  const stations = [{ lat: 25.014, lng: 121.463, station_name: "板橋站" }];
  assert.equal(isInRiderServiceArea(banqiao, stations), true);
  assert.equal(isInRiderServiceArea(hsinchu, stations), false);
  assert.equal(isInRiderServiceArea(hsinchu, []), false);
});

test("一般站權重不低於 1，核心站尖峰加分也遠小於舊的 2 倍", () => {
  assert.ok(SERVICE_GRADES.neighbor.weight >= 1);
  assert.ok(SERVICE_GRADES.neighbor.peakWeight >= 1);
  assert.ok(SERVICE_GRADES.core.peakWeight < 1.3);
  assert.ok(SERVICE_GRADES.core.peakWeight > SERVICE_GRADES.priority.peakWeight);
});

test("尖峰時近的一般站仍排在遠的核心大站前面", () => {
  const now = new Date("2026-09-14T08:10:00+08:00");
  const result = recommendNearbyStations({
    origin,
    intent: "return",
    now,
    stations: [
      {
        station_id: "N",
        station_name: "巷口小站",
        lat: 25.0168,
        lng: 121.463,
        total_docks: 20,
        available_bikes: 4,
        available_docks: 12,
        status: "normal",
        area_type: "residential",
      },
      {
        station_id: "C",
        station_name: "捷運板橋站",
        lat: 25.025,
        lng: 121.463,
        total_docks: 80,
        available_bikes: 10,
        available_docks: 70,
        status: "normal",
        area_type: "transit",
      },
    ],
  });
  assert.equal(result.peak, true);
  assert.deepEqual(result.items.map((row) => row.station_id), ["N", "C"]);
});

test("還車只推薦有空位的站", () => {
  const result = recommendNearbyStations({
    origin,
    intent: "return",
    now: new Date("2026-09-14T11:00:00+08:00"),
    stations: [
      {
        station_id: "FULL",
        station_name: "捷運板橋站",
        lat: 25.0143,
        lng: 121.4626,
        total_docks: 80,
        available_bikes: 80,
        available_docks: 0,
        status: "full",
        area_type: "transit",
      },
      {
        station_id: "OK",
        station_name: "文化路站",
        lat: 25.015,
        lng: 121.465,
        total_docks: 40,
        available_bikes: 10,
        available_docks: 12,
        status: "normal",
      },
    ],
  });
  assert.deepEqual(result.items.map((row) => row.station_id), ["OK"]);
  assert.equal(result.unavailable[0].station_id, "FULL");
});
