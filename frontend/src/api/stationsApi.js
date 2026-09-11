import { mockAdapter } from "./mockAdapter.js";
import { isApiMode, request } from "./httpClient.js";

export async function getDashboardData() {
  if (!isApiMode) return mockAdapter.getDashboard();
  const [stations, recommendations, kpi, sourceStatus, alerts] = await Promise.all([
    request("/stations"), request("/dispatch/recommendations?limit=100"), request("/kpi"),
    request("/data/status"), request("/alerts"),
  ]);
  const denominator = kpi.in_service_stations;
  return { stations, recommendations, sourceStatus, alerts,
    stationDetail: { current: stations[0] || null },
    kpi: { ...kpi, empty_rate: denominator ? kpi.empty_stations / denominator * 100 : null,
      full_rate: denominator ? kpi.full_stations / denominator * 100 : null,
      stations_need_dispatch: recommendations.length },
    weather: { available: false, description: "天氣資料未提供" }, events: [], heatmap: {} };
}

export function getStationDetail(stationId) {
  return isApiMode ? request(`/stations/${encodeURIComponent(stationId)}`) : mockAdapter.getStationDetail(stationId);
}
