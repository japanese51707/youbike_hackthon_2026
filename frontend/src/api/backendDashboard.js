// 後端調度面板資料聚合：把各真實端點抓下來，對映成前端既有結構。
// 站點已由 backendStations 接真；這裡補上 recommendations / alerts / kpi / vehicles / weather。
// 每一塊都獨立容錯：單一端點失敗只降級該塊，不讓整個面板崩掉（誠實標示來源）。
import { request } from "./httpClient.js";
import { fetchBackendStations } from "./backendStations.js";

// 後端 /kpi 回「站數」，前端 KPI 卡要「率」，這裡換算成前端既有欄位。
function mapKpi(raw) {
  const total = Number(raw.total_stations) || 0;
  const inService = Number(raw.in_service_stations) || total || 1;
  const empty = Number(raw.empty_stations) || 0;
  const full = Number(raw.full_stations) || 0;
  return {
    empty_rate: total ? Number(((empty / total) * 100).toFixed(2)) : 0,
    full_rate: total ? Number(((full / total) * 100).toFixed(2)) : 0,
    avg_usage_rate: Number(raw.avg_usage_rate) || 0,
    total_stations: total,
    // 待調度站點：空站 + 滿站（需要立即介入的站），與需調度清單口徑一致。
    stations_need_dispatch: empty + full,
    // 保留後端原始欄位，供需要更精細顯示的元件使用。
    health_rate_pct: raw.health_rate_pct,
    offline_stations: raw.offline_stations,
    healthy_stations: raw.healthy_stations,
    in_service_stations: inService,
    source: raw.source,
    freshness_counts: raw.freshness_counts,
  };
}

// 後端 /weather/by-location 回 {source, rainfall, weather}，前端天氣 Tag 需要 district/description/temperature。
function mapWeather(raw, district) {
  const wx = raw?.weather ?? {};
  const rain = raw?.rainfall ?? {};
  return {
    district: rain.town || wx.town || district || "新北市",
    description: wx.raw_weather || wx.condition || "—",
    condition: wx.condition,
    temperature: Number.isFinite(Number(wx.temperature_c)) ? Number(wx.temperature_c) : null,
    humidity: Number.isFinite(Number(wx.humidity)) ? Number(wx.humidity) : null,
    rainfall_now: Number.isFinite(Number(rain.now)) ? Number(rain.now) : null,
    source: raw?.source || "cwa",
    observed_at: wx.observed_at || rain.observed_at || null,
  };
}

const FALLBACK_WEATHER = {
  district: "新北市",
  description: "天氣暫不可用",
  temperature: null,
  source: "unavailable",
};

// 取一個代表座標打天氣（用站點清單第一站；沒有就用新北市中心）。
function pickWeatherPoint(stations) {
  const s = (stations ?? []).find(
    (x) => Number.isFinite(Number(x.lat)) && Number.isFinite(Number(x.lng)),
  );
  return s
    ? { lat: Number(s.lat), lng: Number(s.lng), district: s.district }
    : { lat: 25.0169, lng: 121.4627, district: "板橋區" };
}

// 後端 task → 前端追蹤卡（TrackSection）結構。只顯示未結案任務。
const TRACK_STATUSES = new Set(["assigned", "in_progress"]);
function mapTasksToOrders(tasks) {
  return (tasks ?? [])
    .filter((t) => TRACK_STATUSES.has(t.task_status))
    .map((t) => ({
      order_id: t.task_id,
      status: t.task_status, // assigned / in_progress（TRACK_STATUS 有對應標籤）
      vehicle: { vehicle_id: t.assigned_vehicle },
      operator_id: t.assigned_operator,
      district: t.district,
      stops: (t.route ?? []).map((s, i) => ({
        seq: i + 1,
        station_id: s.station_id,
        station_name: s.station_name,
        action: s.action,
        quantity: s.est_quantity ?? s.quantity,
        stop_status: s.station_status === "done" ? "completed" : s.station_status,
      })),
      estimate: {
        totalMin: t.estimated_total_minutes ?? 0,
        distanceKm: t.estimated_distance_km ?? 0,
      },
    }));
}

// 各塊獨立容錯：回傳 {value, error}，讓上層決定如何標示來源。
async function settle(promise) {
  try {
    return { value: await promise };
  } catch (err) {
    return { error: err };
  }
}

export async function getBackendDashboard() {
  // 站點先抓（天氣要靠站點座標），其餘並行。
  const stations = await fetchBackendStations();
  const point = pickWeatherPoint(stations);

  const [recs, alerts, kpi, vehicles, weather, tasks] = await Promise.all([
    settle(request("/dispatch/recommendations?limit=50")),
    settle(request("/alerts")),
    settle(request("/kpi")),
    settle(request("/vehicles")),
    settle(
      request(
        `/weather/by-location?lat=${point.lat}&lng=${point.lng}`,
      ),
    ),
    // 進行中任務追蹤：只取未結案的（assigned/in_progress），對映成追蹤卡結構。
    settle(request("/dispatch/tasks")),
  ]);

  const sources = {
    stations: "backend",
    recommendations: recs.error ? `mock（${recs.error.message}）` : "backend",
    alerts: alerts.error ? `mock（${alerts.error.message}）` : "backend",
    kpi: kpi.error ? `mock（${kpi.error.message}）` : "backend",
    vehicles: vehicles.error ? `mock（${vehicles.error.message}）` : "backend",
    weather: weather.error ? "unavailable" : "backend",
  };

  return {
    stations,
    recommendations: recs.value ?? [],
    alerts: alerts.value ?? [],
    kpi: kpi.value ? mapKpi(kpi.value) : null,
    vehicles: vehicles.value ?? [],
    weather: weather.value ? mapWeather(weather.value, point.district) : FALLBACK_WEATHER,
    orders: mapTasksToOrders(tasks.value),
    stationsSource: "backend",
    sources: { ...sources, tasks: tasks.error ? `mock（${tasks.error.message}）` : "backend" },
  };
}
