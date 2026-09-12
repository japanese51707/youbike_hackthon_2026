import test from "node:test";
import assert from "node:assert/strict";
import {
  SCHEDULED,
  URGENT,
  countByDistrict,
  districtOf,
  filterByDistrict,
  splitByTriage,
  stationIdsOf,
  triageOf,
} from "./dispatchTriage.js";

// urgencyItems 的形狀（DashboardPage 整理過）
const item = (over = {}) => ({
  station: { station_id: "S1", station_name: "測試站", district: "板橋區" },
  priorityLevel: "medium",
  ...over,
});

test("已觸底仍在流失的站一律緊急，即使分數沒到 high", () => {
  assert.equal(triageOf(item({ urgencyTier: "censored", priorityLevel: "low" })), URGENT);
});

test("緊急度 high 也算緊急", () => {
  assert.equal(triageOf(item({ priorityLevel: "high" })), URGENT);
});

test("其餘一律次安排", () => {
  assert.equal(triageOf(item({ urgencyTier: "warning" })), SCHEDULED);
  assert.equal(triageOf(item({ priorityLevel: "low" })), SCHEDULED);
  assert.equal(triageOf(null), SCHEDULED);
});

test("後端原始建議的 snake_case 欄位也吃得到", () => {
  assert.equal(triageOf({ urgency_tier: "censored" }), URGENT);
  assert.equal(triageOf({ priority_level: "high" }), URGENT);
  assert.equal(triageOf({ priority_level: "medium" }), SCHEDULED);
});

test("兩桶互斥且不漏件", () => {
  const list = [
    item({ station: { station_id: "A", district: "板橋區" }, priorityLevel: "high" }),
    item({ station: { station_id: "B", district: "板橋區" }, urgencyTier: "censored", priorityLevel: "low" }),
    item({ station: { station_id: "C", district: "板橋區" } }),
  ];
  const { urgent, scheduled } = splitByTriage(list);
  assert.deepEqual(urgent.map((r) => r.station.station_id), ["A", "B"]);
  assert.deepEqual(scheduled.map((r) => r.station.station_id), ["C"]);
  assert.equal(urgent.length + scheduled.length, list.length);
});

test("行政區統計依任務數由多到少", () => {
  const counts = countByDistrict([
    item({ station: { station_id: "A", district: "中和區" } }),
    item({ station: { station_id: "B", district: "板橋區" } }),
    item({ station: { station_id: "C", district: "中和區" } }),
  ]);
  assert.deepEqual(counts, [
    { district: "中和區", count: 2 },
    { district: "板橋區", count: 1 },
  ]);
});

test("沒有行政區的建議歸到未分區，不會被丟掉", () => {
  assert.equal(districtOf({ station: { station_id: "X" } }), "未分區");
  assert.deepEqual(countByDistrict([{ station: { station_id: "X" } }]), [
    { district: "未分區", count: 1 },
  ]);
});

test("行政區篩選：all 不過濾", () => {
  const list = [
    item({ station: { station_id: "A", district: "中和區" } }),
    item({ station: { station_id: "B", district: "板橋區" } }),
  ];
  assert.equal(filterByDistrict(list, "all").length, 2);
  assert.equal(filterByDistrict(list, "板橋區").length, 1);
});

test("地圖跟隨分頁時用清單的站點集合", () => {
  const ids = stationIdsOf([
    item({ station: { station_id: "A", district: "中和區" } }),
    item({ station: { station_id: "B", district: "中和區" } }),
    { station: {} },
  ]);
  assert.equal(ids.has("A"), true);
  assert.equal(ids.has("B"), true);
  assert.equal(ids.size, 2);
});
