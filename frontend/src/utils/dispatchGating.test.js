import test from "node:test";
import assert from "node:assert/strict";
import { blockingReasonsOf, canConfirm, nextStepFor, onboardBlocking } from "./dispatchGating.js";

const clean = { assigned_operator: "OP-004", assigned_vehicle: "CAR-001", blocking_reasons: [] };

test("a clean draft can be confirmed", () => {
  assert.equal(canConfirm(clean), true);
});

test("any blocking reason disables confirmation", () => {
  const blocked = { ...clean, blocking_reasons: [{ code: "load_below_zero", message: "車上只有 1 台" }] };
  assert.equal(canConfirm(blocked), false);
  assert.equal(blockingReasonsOf(blocked).length, 1);
});

test("a draft without assigned people or vehicle cannot be confirmed", () => {
  assert.equal(canConfirm({ blocking_reasons: [] }), false);
  assert.equal(canConfirm({ blocking_reasons: [] }, { requireResources: false }), true);
});

test("missing blocking_reasons is treated as no reasons, not as blocked", () => {
  assert.deepEqual(blockingReasonsOf({}), []);
  assert.equal(canConfirm({ assigned_operator: "OP-004", assigned_vehicle: "CAR-001" }), true);
});

test("onboard problems are recognised so the panel can offer an inline report", () => {
  assert.equal(onboardBlocking({ blocking_reasons: [{ code: "vehicle_onboard_unknown" }] }), true);
  assert.equal(onboardBlocking({ blocking_reasons: [{ code: "vehicle_onboard_stale" }] }), true);
  assert.equal(onboardBlocking({ blocking_reasons: [{ code: "load_below_zero" }] }), false);
  assert.equal(onboardBlocking(null), false);
});

test("every known code carries a next step for the operator", () => {
  for (const code of ["vehicle_onboard_unknown", "load_below_zero", "load_exceeds_capacity",
    "total_quantity_exceeds_capacity", "stop_beyond_forecast_horizon", "cross_district_not_allowed",
    "labor_hours_exceeded", "task_time_overlap"]) {
    assert.ok(nextStepFor(code).length > 0, code);
  }
  assert.equal(nextStepFor("unknown_code"), "");
});
