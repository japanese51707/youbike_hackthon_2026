// 前端資料來源設定（探索性接線 spike；正式方案待 ADR）。
// baseUrl 可用環境變數 VITE_API_BASE 覆寫；預設打本機後端。
// useBackendStations：調度面板站點是否改接後端 GET /stations（其餘資料仍為 mock）。
const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

export const apiConfig = Object.freeze({
  baseUrl: API_BASE,
  useBackendStations: (import.meta.env.VITE_BACKEND_STATIONS ?? "1") !== "0",
});
