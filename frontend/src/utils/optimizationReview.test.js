import assert from "node:assert/strict";
import test from "node:test";
import {
  applyStationDecision,
  createMockReview,
  describeParamChange,
  isReviewActionable,
  paramLabel,
  summarizeReviewDecisions,
} from "./optimizationReview.js";

test("mock review is actionable and uses Chinese param labels", () => {
  const review = createMockReview();
  assert.equal(review.mock, true);
  assert.equal(isReviewActionable(review), true);
  assert.equal(paramLabel("base_outflow_coef"), "平日流出係數");
  assert.match(describeParamChange(review.station_changes[0].params[0]), /平日流出係數/);
});

test("station decisions and approval summary stay local", () => {
  const review = createMockReview();
  const kept = applyStationDecision(review.station_changes, "500103005", "keep");
  const summary = summarizeReviewDecisions(kept);
  assert.equal(summary.keepCount, 1);
  assert.equal(summary.acceptCount, 3);
  assert.ok(summary.keepNames.includes("三重國小"));
});
