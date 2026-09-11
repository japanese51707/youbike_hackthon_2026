import { request, getActorId } from "./httpClient.js";
export async function getAssignedWorkspace() {
  const actor = getActorId();
  if (!actor) return { operator: null, tasks: [] };
  const [operator, tasks] = await Promise.all([
    request(`/operators/${encodeURIComponent(actor)}`),
    request(`/dispatch/tasks?operator=${encodeURIComponent(actor)}`),
  ]);
  return { operator, tasks };
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
