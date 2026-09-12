// 前端資料來源設定。base URL 已統一由 httpClient 管理（VITE_API_BASE_URL，預設 /api/v1 走 Vite proxy）；
// 這裡不再自定 base URL，避免站點與其他端點打到不同後端。
// useBackendStations：調度面板站點是否改接後端 GET /stations。
// 預設跟隨 isApiMode（API 模式就接後端，mock 模式就用 mock）；可用 VITE_BACKEND_STATIONS=0 強制關閉。
import { isApiMode } from "./httpClient.js";

export const apiConfig = Object.freeze({
  useBackendStations:
    isApiMode && (import.meta.env.VITE_BACKEND_STATIONS ?? "1") !== "0",
});
