import { mockAdapter } from "./mockAdapter.js";

export function getDashboardData() {
  return mockAdapter.getDashboard();
}

export function getStationDetail(stationId) {
  return mockAdapter.getStationDetail(stationId);
}
