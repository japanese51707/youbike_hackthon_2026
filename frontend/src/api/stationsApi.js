import { mockAdapter } from "./mockAdapter.js";
import { apiConfig } from "./apiConfig.js";
import { fetchBackendStations } from "./backendStations.js";

// 調度面板資料：其餘（建議/警示/車輛/KPI/天氣）仍為 mock；
// 站點可改接後端 /stations（gated）。後端連線失敗時安全退回 mock 站點並標明來源。
export async function getDashboardData() {
  const base = await mockAdapter.getDashboard();
  if (!apiConfig.useBackendStations) {
    return { ...base, stationsSource: "mock" };
  }
  try {
    const stations = await fetchBackendStations();
    return { ...base, stations, stationsSource: "backend" };
  } catch (err) {
    return { ...base, stationsSource: `mock（後端連線失敗：${err.message}）` };
  }
}

export function getStationDetail(stationId) {
  return mockAdapter.getStationDetail(stationId);
}
