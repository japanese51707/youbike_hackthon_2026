import { mockAdapter } from "./mockAdapter.js";
import { apiConfig } from "./apiConfig.js";
import { isApiMode, request } from "./httpClient.js";
import { fetchBackendStations } from "./backendStations.js";
import { getBackendDashboard, getTwinDashboard } from "./backendDashboard.js";

const dashboardCache = { full: null, twin: null };

export function peekDashboardData(lite = false) {
  return lite ? dashboardCache.twin : dashboardCache.full;
}

// 調度面板資料。
// - API 模式：站點/建議/警示/KPI/車輛/天氣全部走後端真實端點（backendDashboard），
//   後端整體不可用時才降級到 mock 並標明原因。
// - mock 模式：全用 mock；若只是想預覽後端站點，useBackendStations 開關可只覆蓋站點。
export async function getDashboardData({ lite = false } = {}) {
  const key = lite ? "twin" : "full";
  const remember = (payload) => {
    dashboardCache[key] = payload;
    return payload;
  };

  if (isApiMode) {
    try {
      return remember(lite ? await getTwinDashboard() : await getBackendDashboard());
    } catch (err) {
      const base = await mockAdapter.getDashboard();
      return remember({ ...base, stationsSource: `mock（後端連線失敗：${err.message}）` });
    }
  }

  // mock 模式：預設全 mock；useBackendStations 開時只把站點覆蓋成後端（其餘仍 mock）。
  const base = await mockAdapter.getDashboard();
  if (!apiConfig.useBackendStations) {
    return remember({ ...base, stationsSource: "mock" });
  }
  try {
    const stations = await fetchBackendStations();
    return remember({ ...base, stations, stationsSource: "backend" });
  } catch (err) {
    return remember({ ...base, stationsSource: `mock（後端連線失敗：${err.message}）` });
  }
}

// 單站詳情：API 模式接後端 GET /stations/{id}（含 current/history/prediction/params），
// mock 模式回 mock 詳情。
export function getStationDetail(stationId) {
  if (isApiMode) {
    return request(`/stations/${encodeURIComponent(stationId)}`);
  }
  return mockAdapter.getStationDetail(stationId);
}

// 單站加值資料（API 模式）：
// - 靜態打包 /stations/{id}/static：地形（實測高程 elevation / 坡度 / 地形分類）、POI、指紋。
// - 該站最近測站即時天氣 /weather/by-location：沃羅諾伊最近雨量站 + 氣象站（雨量/溫度/濕度）。
// 兩者獨立容錯：任一失敗只讓該塊為 null，不影響詳情主體。
export async function getStationEnrichment(stationId, { lat, lng } = {}) {
  if (!isApiMode) return { static: null, weather: null };
  const settle = (p) => p.then((value) => value).catch(() => null);
  const hasCoord = Number.isFinite(Number(lat)) && Number.isFinite(Number(lng));
  const [staticData, weather] = await Promise.all([
    settle(request(`/stations/${encodeURIComponent(stationId)}/static`)),
    hasCoord
      ? settle(request(`/weather/by-location?lat=${Number(lat)}&lng=${Number(lng)}`))
      : Promise.resolve(null),
  ]);
  return { static: staticData, weather };
}
