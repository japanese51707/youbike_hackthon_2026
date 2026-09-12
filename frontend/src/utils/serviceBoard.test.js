import assert from "node:assert/strict";
import test from "node:test";
import {
  buildHeadline,
  districtLongestOpen,
  districtPressureLevel,
  districtServiceRows,
  elapsedMinutesSince,
  formatDurationMinutes,
  longestOpenOfKind,
  pct,
  rankDistrictPressure,
  ratesFromKpi,
  resolveCardCopy,
} from "./serviceBoard.js";

test("ratesFromKpi uses in-service stations as the denominator", () => {
  const rates = ratesFromKpi({
    in_service_stations: 100,
    empty_stations: 10,
    full_stations: 5,
    healthy_stations: 85,
    health_rate_pct: 85,
  });
  assert.equal(rates.emptyRate, 10);
  assert.equal(rates.fullRate, 5);
  assert.equal(rates.healthRate, 85);
});

test("districtPressureLevel is green / yellow / red by empty+full share", () => {
  assert.equal(districtPressureLevel(0, 40), "green");
  assert.equal(districtPressureLevel(2, 40), "yellow");
  assert.equal(districtPressureLevel(4, 40), "red");
  assert.equal(districtPressureLevel(1, 0), "none");
});

test("rankDistrictPressure sorts by empty+full and keeps only problem stations in drill-down", () => {
  const ranked = rankDistrictPressure([
    { station_id: "a", station_name: "空1", district: "板橋區", status: "empty" },
    { station_id: "b", station_name: "滿1", district: "板橋區", status: "full" },
    { station_id: "c", station_name: "正常", district: "板橋區", status: "normal" },
    { station_id: "d", station_name: "空2", district: "中和區", status: "empty" },
  ]);
  assert.equal(ranked[0].district, "板橋區");
  assert.equal(ranked[0].problems, 2);
  assert.equal(ranked[0].stations.length, 2);
  assert.equal(ranked[1].district, "中和區");
});

test("buildHeadline names the hottest districts", () => {
  assert.equal(
    buildHeadline({ empty: 51, full: 10, hotDistricts: ["板橋區", "中和區"] }),
    "目前 51 站借不到、10 站還不到；板橋區、中和區需關注。",
  );
  assert.equal(
    buildHeadline({ empty: 0, full: 0, hotDistricts: [] }),
    "目前 0 站借不到、0 站還不到；各區大致穩定。",
  );
});

test("pct is zero when the denominator is missing", () => {
  assert.equal(pct(3, 0), 0);
});

test("formatDurationMinutes splits hours", () => {
  assert.equal(formatDurationMinutes(null), "—");
  assert.equal(formatDurationMinutes(23), "23 分");
  assert.equal(formatDurationMinutes(60), "1 時");
  assert.equal(formatDurationMinutes(75), "1 時 15 分");
});

test("elapsedMinutesSince uses opened_at so reload does not invent a new clock", () => {
  const opened = "2026-09-12T09:00:00+08:00";
  const now = Date.parse("2026-09-12T09:20:00+08:00");
  assert.equal(Math.round(elapsedMinutesSince(opened, now)), 20);
});

test("longestOpenOfKind is null when nobody is burning", () => {
  assert.equal(longestOpenOfKind({ open: [] }, "empty", Date.now()), null);
});

test("districtLongestOpen picks the burning station in that district", () => {
  const opened = "2026-09-12T09:00:00+08:00";
  const now = Date.parse("2026-09-12T09:40:00+08:00");
  const minutes = districtLongestOpen("板橋區", {
    open: [
      { district: "板橋區", opened_at: opened, elapsed_minutes: 10 },
      { district: "中和區", opened_at: opened, elapsed_minutes: 99 },
    ],
  }, now);
  assert.equal(Math.round(minutes), 40);
});

test("rankDistrictPressure tags each district with a pressure color", () => {
  const stations = [
    { station_id: "empty", station_name: "空", district: "板橋區", status: "empty" },
    ...Array.from({ length: 19 }, (_, i) => ({
      station_id: `n${i}`,
      station_name: "健康",
      district: "板橋區",
      status: "normal",
    })),
  ];
  assert.equal(rankDistrictPressure(stations)[0].pressure, "yellow");
});

test("districtServiceRows reports empty rate against in-service stations", () => {
  const rows = districtServiceRows([
    { station_id: "a", station_name: "空1", district: "板橋區", status: "empty" },
    { station_id: "b", station_name: "健康", district: "板橋區", status: "normal" },
    { station_id: "c", station_name: "離線", district: "板橋區", status: "offline" },
    { station_id: "d", station_name: "滿1", district: "中和區", status: "full" },
  ]);
  const banqiao = rows.find((row) => row.district === "板橋區");
  assert.equal(banqiao.empty, 1);
  assert.equal(banqiao.inService, 2);
  assert.equal(banqiao.emptyRate, 50);
  assert.equal(banqiao.offline, 1);
  assert.equal(banqiao.emptyStations[0].station_name, "空1");
});

test("resolveCardCopy uses whatever is in the window, not a full 24h", () => {
  const withAvg = resolveCardCopy({
    city: { avg_resolved_minutes: 12, resolved_count: 3 },
    history: { collected_minutes: 40 },
    longestOpen: 8,
  });
  assert.equal(withAvg.value, "12 分");
  assert.match(withAvg.hint, /已收集 40 分/);

  const onlyOpen = resolveCardCopy({
    city: { resolved_count: 0 },
    history: { collected_minutes: 15 },
    longestOpen: 15,
  });
  assert.equal(onlyOpen.value, "15 分");
  assert.match(onlyOpen.timer, /尚無排除/);

  const liveOnly = resolveCardCopy({
    city: {},
    liveProblems: 7,
  });
  assert.equal(liveOnly.value, "7 站");
});
