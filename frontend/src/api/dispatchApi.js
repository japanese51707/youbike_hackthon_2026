import { mockAdapter } from "./mockAdapter.js";
import { isApiMode, request } from "./httpClient.js";
// ADR-304 的草稿可行性判斷放在 utils/dispatchGating.js（純邏輯、可獨立測試）
export { blockingReasonsOf, canConfirm, nextStepFor, onboardBlocking } from "../utils/dispatchGating.js";

export async function previewRecommendation(recommendation, choices = {}) {
  if (!isApiMode) return recommendation;
  const draft = await request("/dispatch/build/from-station", {
    method: "POST", body: { station_id: recommendation.station_id, ...choices },
  });
  if (draft.error || !draft.draft_id) throw new Error(draft.error || "無法建立草稿");
  return draft;
}
export function confirmRecommendation(draft) {
  return isApiMode ? request("/dispatch/confirm-trip", {
    method: "POST", body: { draft_id: draft.draft_id, version: draft.version },
  }) : mockAdapter.confirmRecommendation(draft.recommendation_id);
}
// ADR-123：回報調度車車上台數（值 + 來源 + 觀測時間都由後端記錄，可追溯）。
// 未回報或回報過期的車不可確認派工——後端不會把「未知」當成 0。
export function reportVehicleOnboard(vehicleId, onboardBikes) {
  return request(`/vehicles/${encodeURIComponent(vehicleId)}/onboard`, {
    method: "POST", body: { onboard_bikes: onboardBikes, source: "manual_report" },
  });
}

export function acknowledgeAlert(alertId) {
  return isApiMode ? request(`/alerts/${encodeURIComponent(alertId)}/acknowledge`, { method: "POST" })
    : mockAdapter.acknowledgeAlert(alertId);
}
export async function getDispatchResources() {
  const [operators, vehicles] = await Promise.all([request("/operators"), request("/vehicles")]);
  return { operators: operators.filter(o => ["driver", "depot_standby"].includes(o.role_type) && o.status === "on_duty" && !o.current_task_id),
    vehicles: vehicles.filter(v => v.status === "available" && !v.current_task_id) };
}
