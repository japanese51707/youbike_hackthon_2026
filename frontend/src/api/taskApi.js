import { request, getActorId } from "./httpClient.js";

const ACTIVE_STATUSES = ["assigned", "in_progress"];

// 司機工作台需要的一次性資料：本人 + 指派任務 + 任務用到的車輛/隨車人員。
// 車輛與隨車查詢失敗不應該讓整頁掛掉（司機在路上，有任務清單比有車牌重要），
// 所以走 allSettled，查不到就留空、畫面顯示編號。
export async function getAssignedWorkspace(actor = getActorId()) {
  if (!actor) return { operator: null, tasks: [], vehicles: {}, people: {} };
  const [operator, tasks] = await Promise.all([
    request(`/operators/${encodeURIComponent(actor)}`),
    request(`/dispatch/tasks?operator=${encodeURIComponent(actor)}`),
  ]);
  const active = (tasks || []).filter(
    (t) => ACTIVE_STATUSES.includes(t.task_status) && !t.resources_released,
  );
  const vehicleIds = [...new Set(active.map((t) => t.assigned_vehicle).filter(Boolean))];
  const peopleIds = [...new Set(active.map((t) => t.assigned_escort).filter(Boolean))];
  const [vehicleResults, peopleResults] = await Promise.all([
    Promise.allSettled(vehicleIds.map((id) => request(`/vehicles/${encodeURIComponent(id)}`))),
    Promise.allSettled(peopleIds.map((id) => request(`/operators/${encodeURIComponent(id)}`))),
  ]);
  const vehicles = {};
  vehicleIds.forEach((id, i) => {
    if (vehicleResults[i].status === "fulfilled") vehicles[id] = vehicleResults[i].value;
  });
  const people = {};
  peopleIds.forEach((id, i) => {
    if (peopleResults[i].status === "fulfilled") people[id] = peopleResults[i].value;
  });
  return { operator, tasks: tasks || [], vehicles, people };
}

export const startTask = id => request(`/dispatch/tasks/${encodeURIComponent(id)}/start`, { method: "POST" });
export const returnTask = (id, reason) => request(`/dispatch/tasks/${encodeURIComponent(id)}/return`, { method: "POST", body: { reason } });
export const reportStop = (id, stationId, actualAvailable) => request(`/dispatch/tasks/${encodeURIComponent(id)}/report`, {
  method: "POST", body: { station_id: stationId, actual_available: actualAvailable },
});
export const setDuty = status => request("/operators/me/duty", { method: "POST", body: { status } });
// ADR-123：司機回報自己任務中的調度車車上幾台（後端會擋掉不是自己任務的車）。
export const reportVehicleLoad = (vehicleId, onboardBikes) =>
  request(`/vehicles/${encodeURIComponent(vehicleId)}/onboard`, {
    method: "POST", body: { onboard_bikes: onboardBikes, source: "manual_report" },
  });
