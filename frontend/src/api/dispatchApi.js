import { mockAdapter } from "./mockAdapter.js";
import { getActorId, isApiMode, request } from "./httpClient.js";
// ADR-304 的草稿可行性判斷放在 utils/dispatchGating.js（純邏輯、可獨立測試）
export { blockingReasonsOf, canConfirm, nextStepFor, onboardBlocking } from "../utils/dispatchGating.js";

// 後端組單三入口（ADR-119）。路線/載運/可行性由後端 dispatch_builder 計算，
// 前端只送選擇、拿回草稿（含 draft_id/version、stations、estimate、blocking_reasons、
// load_plan、vehicle_candidates）。確認前依 blocking_reasons 決定能否送出。
function ensureDraft(draft) {
  if (!draft || draft.error || !draft.draft_id) {
    throw new Error(draft?.error || "無法建立草稿");
  }
  return draft;
}

// 入口 b：以站為起點（可選指定車 / 指定司機）。
export async function buildFromStation(stationId, { vehicleId, operatorId, escortId } = {}) {
  const body = { station_id: stationId };
  if (vehicleId) body.vehicle_id = vehicleId;
  if (operatorId) body.operator_id = operatorId;
  if (escortId) body.escort_id = escortId;   // ADR-308 隨車（可選）
  return ensureDraft(
    await request("/dispatch/build/from-station", { method: "POST", body }),
  );
}

// 入口 a：以車為起點（operator_id 預設帶當前操作身分，可被指定司機覆寫）。
export async function buildFromVehicle(vehicleId, { district, operatorId, escortId } = {}) {
  const body = { vehicle_id: vehicleId, operator_id: operatorId || getActorId() };
  if (district) body.district = district;
  if (escortId) body.escort_id = escortId;   // ADR-308 隨車（可選）
  return ensureDraft(
    await request("/dispatch/build/from-vehicle", { method: "POST", body }),
  );
}

// 入口 c：緊急出車（一或多個種子站；可選指定車 / 指定司機）。
export async function buildEmergency(stationIds, { vehicleId, operatorId, escortId } = {}) {
  const body = { station_ids: Array.isArray(stationIds) ? stationIds : [stationIds] };
  if (vehicleId) body.vehicle_id = vehicleId;
  if (operatorId) body.operator_id = operatorId;
  if (escortId) body.escort_id = escortId;   // ADR-308 隨車（可選）
  return ensureDraft(
    await request("/dispatch/build/emergency", { method: "POST", body }),
  );
}

// 相容舊呼叫：以建議站為起點組單。
export async function previewRecommendation(recommendation, choices = {}) {
  if (!isApiMode) return recommendation;
  return buildFromStation(recommendation.station_id, {
    vehicleId: choices.vehicle_id,
  });
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
