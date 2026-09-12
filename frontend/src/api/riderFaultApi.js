import { isApiMode } from "./httpClient.js";
import {
  addFaultDelta,
  emptyFaultSummary,
  indexFaultSummaries,
  loadLocalFaultSummaries,
  persistLocalFaultSummaries,
} from "../utils/riderFaultReports.js";

const baseUrl = (import.meta.env?.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");

function applyLocal(stationId, stationName, issue, addQuantity) {
  const byId = loadLocalFaultSummaries();
  const next = addFaultDelta(byId[stationId] || emptyFaultSummary(stationId, stationName), issue, addQuantity);
  next.station_name = stationName || next.station_name;
  byId[stationId] = next;
  persistLocalFaultSummaries(byId);
  return next;
}

export async function fetchFaultSummaries() {
  if (isApiMode) {
    try {
      const response = await fetch(`${baseUrl}/rider/fault-summaries`, { headers: { Accept: "application/json" } });
      if (response.ok) {
        const payload = await response.json();
        const byId = indexFaultSummaries(payload?.summaries);
        persistLocalFaultSummaries(byId);
        return byId;
      }
    } catch {
      /* 後端暫時不可用時改看本機合計 */
    }
  }
  return loadLocalFaultSummaries();
}

export async function submitFaultReport({ stationId, stationName, issue, addQuantity, note }) {
  if (isApiMode) {
    const response = await fetch(`${baseUrl}/rider/fault-reports`, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({
        station_id: stationId,
        station_name: stationName,
        issue,
        add_quantity: addQuantity,
        note: note || null,
      }),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      throw new Error(payload?.message || "通報送出失敗");
    }
    const summary = payload?.summary;
    if (summary?.station_id) {
      const byId = loadLocalFaultSummaries();
      byId[summary.station_id] = summary;
      persistLocalFaultSummaries(byId);
    }
    return summary;
  }
  return applyLocal(stationId, stationName, issue, addQuantity);
}
