import assert from "node:assert/strict";
import test from "node:test";
import {
  driverActorOptions,
  fieldOperators,
  pickDriverActor,
} from "./pickDriverActor.js";

const rows = [
  { operator_id: "OP-D", name: "調度", role: "dispatcher" },
  { operator_id: "OP-1", name: "閒置司機", role: "operator", role_type: "driver" },
  {
    operator_id: "OP-2",
    name: "有單司機",
    role: "operator",
    role_type: "driver",
    current_task_id: "T-2",
    status: "on_duty",
  },
  {
    operator_id: "OP-3",
    name: "執行中",
    role: "operator",
    role_type: "driver",
    current_task_id: "T-3",
    status: "busy",
  },
];

test("pickDriverActor keeps the current person when they already have a task", () => {
  assert.equal(pickDriverActor(rows, "OP-2"), "OP-2");
});

test("pickDriverActor prefers a busy driver when the current person has no task", () => {
  assert.equal(pickDriverActor(rows, "OP-D"), "OP-3");
  assert.equal(pickDriverActor(rows, ""), "OP-3");
  assert.equal(pickDriverActor(rows, "OP-1"), "OP-3");
});

test("pickDriverActor falls back to any tasked driver, then the current id", () => {
  assert.equal(pickDriverActor([rows[0], rows[2]], "OP-D"), "OP-2");
  assert.equal(pickDriverActor([rows[0]], "OP-D"), "OP-D");
  assert.equal(pickDriverActor([], ""), "");
});

test("driverActorOptions lists field people with tasked drivers first", () => {
  const options = driverActorOptions(rows);
  assert.deepEqual(options.map((row) => row.value), ["OP-2", "OP-3", "OP-1"]);
  assert.match(options[0].label, /有任務/);
  assert.match(options[2].label, /待命/);
  assert.equal(fieldOperators(rows).some((row) => row.operator_id === "OP-D"), false);
});
