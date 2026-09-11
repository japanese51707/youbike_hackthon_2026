// ADR-123／304：草稿可行性的純邏輯（沒有網路依賴，可獨立測試）。
//
// 後端在預覽階段就回 blocking_reasons：空陣列＝可以確認；非空＝按下確認會被 409 擋下。
// 前端的責任是「按之前就講清楚，而不是按了才報錯」——所以確認鈕依這裡的判斷決定要不要失效。

// 這些原因可以就地回報車上台數解決，不必重新挑站點。
const ONBOARD_CODES = new Set(["vehicle_onboard_unknown", "vehicle_onboard_stale"]);

// code 與訊息都由後端給；這裡只補「使用者下一步該做什麼」。
export const NEXT_STEP = {
  vehicle_onboard_unknown: "請先回報這台車目前車上幾台。",
  vehicle_onboard_stale: "車上台數的回報已過期，請重新回報。",
  load_below_zero: "車上的車不夠放，請先裝載或改成先取後放。",
  load_exceeds_capacity: "途中會超過車容量，請減少站點或換大車。",
  total_quantity_exceeds_capacity: "總搬運量超過車容量，請減少站點。",
  stop_beyond_forecast_horizon: "有站點超出最長預測視野（120 分），請縮短路線。",
  cross_district_not_allowed: "這個班別不可跨區，請改同區或走緊急出車。",
  labor_hours_exceeded: "這位司機剩餘連續工時不足，請換人或縮短本趟。",
  task_time_overlap: "人或車與既有未結束任務時間重疊，請換人車或等前一趟結束。",
  missing_vehicle: "請先選擇調度車。",
  missing_operator: "請先選擇執行司機。",
};

export function blockingReasonsOf(draft) {
  return Array.isArray(draft?.blocking_reasons) ? draft.blocking_reasons : [];
}

export function onboardBlocking(draft) {
  return blockingReasonsOf(draft).some(reason => ONBOARD_CODES.has(reason?.code));
}

// 確認鈕能不能按。沒有草稿、有阻擋原因、或人車未定，都不能按。
export function canConfirm(draft, { requireResources = true } = {}) {
  if (!draft) return false;
  if (blockingReasonsOf(draft).length > 0) return false;
  if (requireResources && !(draft.assigned_operator && draft.assigned_vehicle)) return false;
  return true;
}

export function nextStepFor(code) {
  return NEXT_STEP[code] || "";
}
