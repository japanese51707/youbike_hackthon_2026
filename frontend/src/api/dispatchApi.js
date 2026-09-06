import { mockAdapter } from "./mockAdapter.js";

export function confirmRecommendation(recommendationId) {
  return mockAdapter.confirmRecommendation(recommendationId);
}

export function acknowledgeAlert(alertId) {
  return mockAdapter.acknowledgeAlert(alertId);
}
