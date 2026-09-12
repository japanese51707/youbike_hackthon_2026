// 後端站點讀取（GET /api/v1/stations）。
// 後端走 data_source 層（mock / historical / tdx / youbike_official，由 config.yaml 切換），
// 回標準站點欄位。這裡只做「當不可信輸入」的容錯正規化，不假造缺漏欄位。
// 統一走 httpClient.request（與其餘端點同一 base URL + Vite proxy + 錯誤處理），
// 不再自己組絕對網址，避免站點與其他端點打到不同後端。
import { request } from "./httpClient.js";

const REQUIRED = [
  "station_id",
  "station_name",
  "district",
  "lat",
  "lng",
  "total_docks",
  "available_bikes",
  "available_docks",
  "usage_rate",
  "status",
];

function normalize(raw) {
  return {
    ...raw,
    lat: Number(raw.lat),
    lng: Number(raw.lng),
    total_docks: Number(raw.total_docks),
    available_bikes: Number(raw.available_bikes),
    available_docks: Number(raw.available_docks),
    usage_rate: Number(raw.usage_rate),
  };
}

function isValid(s) {
  return (
    s &&
    REQUIRED.every((k) => s[k] !== undefined && s[k] !== null) &&
    Number.isFinite(Number(s.lat)) &&
    Number.isFinite(Number(s.lng))
  );
}

export async function fetchBackendStations() {
  const data = await request("/stations");
  if (!Array.isArray(data)) throw new Error("後端 /stations 格式非陣列");
  const stations = data.filter(isValid).map(normalize);
  if (!stations.length) throw new Error("後端 /stations 無有效站點");
  return stations;
}
