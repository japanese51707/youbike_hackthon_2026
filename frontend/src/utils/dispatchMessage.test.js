import test from "node:test";
import assert from "node:assert/strict";
import { isSameMessage, similarity, stripStationName } from "./dispatchMessage.js";

test("拿掉警報開頭重複的站名", () => {
  assert.equal(
    stripStationName("YouBike2.0_民生公園｜現況 6 台，即將空站", "YouBike2.0_民生公園"),
    "現況 6 台，即將空站",
  );
  assert.equal(
    stripStationName("YouBike2.0_中央路一段292巷口 已空站，建議立即補車", "YouBike2.0_中央路一段292巷口"),
    "已空站，建議立即補車",
  );
});

test("站名不在開頭就整句保留", () => {
  assert.equal(stripStationName("已空站，建議立即補車", "民生公園"), "已空站，建議立即補車");
  assert.equal(stripStationName("", "民生公園"), "");
  assert.equal(stripStationName("已空站", null), "已空站");
});

test("只差幾個數字的兩句話算重複", () => {
  const a = "現況 6 台，30 分鐘後預測仍將淨流出至 –0.3 台（缺口約 0 台）——需求被壓抑，最高緊急補車";
  const b = "現況 1 台，30 分鐘後預測仍將淨流出至 –0.3 台（缺口約 0 台）——需求被壓抑，最高緊急補車";
  assert.ok(similarity(a, b) > 0.9);
  assert.equal(isSameMessage(a, b), true);
});

test("現況與預測是兩件事，不可以被收掉", () => {
  const alert = "已空站（無車可借），建議立即補車";
  const reason = "30 分鐘後預測到達存量最低 1.0 台，低於安全緩衝 2 台，即將空站";
  assert.equal(isSameMessage(alert, reason), false);
});

test("一句是另一句的前綴延伸時算重複", () => {
  assert.equal(isSameMessage("已空站，建議立即補車", "已空站"), true);
});

test("缺一邊就不算重複（不會誤刪唯一的說明）", () => {
  assert.equal(isSameMessage("", "已空站"), false);
  assert.equal(isSameMessage("已空站", null), false);
  assert.equal(similarity("", "x"), 0);
});
