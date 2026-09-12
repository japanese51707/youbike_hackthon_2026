import test from "node:test";
import assert from "node:assert/strict";
import { addFaultDelta, formatFaultSummary, previewFaultAdd } from "./riderFaultReports.js";

test("本次新增會加在本站已通報之上", () => {
  const current = { station_id: "A", bikes: 2, docks: 1, station_down: false, other: 0 };
  const preview = previewFaultAdd(current, "bike", 3);
  assert.equal(preview.add, 3);
  assert.equal(preview.next.bikes, 5);
  assert.equal(preview.next.docks, 1);
  assert.equal(preview.current.bikes, 2);
});

test("已通報文案列出台與柱", () => {
  assert.equal(formatFaultSummary({ bikes: 2, docks: 1 }), "本站已通報故障 2 台、1 柱");
  assert.equal(formatFaultSummary({ bikes: 0, docks: 0 }), "");
});

test("整站不能用只標旗標，不加數量", () => {
  const next = addFaultDelta({ station_id: "A", bikes: 1, docks: 0 }, "station", 4);
  assert.equal(next.station_down, true);
  assert.equal(next.bikes, 1);
});
