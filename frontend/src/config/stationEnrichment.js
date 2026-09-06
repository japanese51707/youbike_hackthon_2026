// 站點前端補充資料（ADR-203：frontend-local view model，與共同 API 契約分離）。
//
// - 海拔為「範例估計值」，非量測資料，僅供 Demo 呈現與站間相對高低比較，
//   日後應由 DEM／高程 API 取代；不得視為官方高程或送入派遣 payload。
// - 特徵標註由「站名 + area_type」以透明規則自動推斷，屬前端呈現分類。
//
// 缺對應資料時回傳 null／空陣列，由 UI 顯示不可用，不捏造。

import { areaTypeLabels } from "../utils/formatters.js";

// 範例海拔（公尺）：依站點所在地大致地形估計，非實測。
const STATION_ELEVATION_SAMPLE_M = {
  "500101001": 15, // 中和 南勢角
  "500101002": 12, // 中和 景安
  "500102010": 8, // 板橋車站
  "500103005": 6, // 三重國小（河岸低地）
  "500104020": 7, // 新莊運動中心
  "500105011": 5, // 蘆洲（低地）
  "500106003": 9, // 永和國小
  "500107008": 30, // 土城醫院（丘陵）
  "500108002": 250, // 林口三井Outlet（林口台地）
  "500109014": 18, // 新店大坪林
};

export function getStationElevation(station) {
  const value = STATION_ELEVATION_SAMPLE_M[station?.station_id];
  return Number.isFinite(value) ? value : null;
}

// 容量規模：由既有 total_docks 分級（真實欄位推導）。
export function deriveCapacityTier(station) {
  const capacity = Number(station?.total_docks);
  if (!Number.isFinite(capacity)) return null;
  if (capacity >= 70) return "大型場站";
  if (capacity >= 45) return "中型站";
  return "小型站";
}

// 尖峰潮汐型態：依 area_type 推斷（推斷值，非實測流量）。
const TIDAL_BY_AREA = {
  school: "早尖峰流出（上學）",
  residential: "早尖峰流出（通勤）",
  transit: "晚尖峰流入（返程）",
  commercial: "晚尖峰流入（下班）",
  leisure: "假日／午後為主",
  mixed: "雙向型",
};

export function deriveTidalPattern(station) {
  return TIDAL_BY_AREA[station?.area_type] ?? "雙向型";
}

// 鄰站相對高度：用範例海拔比較本站與鄰站均值，推斷車輛累積傾向。
// 需要 nearby_stations 與雙方範例海拔；缺資料回 null。
export function computeElevationVsNeighbors(station, nearbyIds) {
  const self = getStationElevation(station);
  if (self == null || !Array.isArray(nearbyIds) || !nearbyIds.length) return null;

  const elevations = nearbyIds
    .map((id) => STATION_ELEVATION_SAMPLE_M[id])
    .filter((value) => Number.isFinite(value));
  if (!elevations.length) return null;

  const avgNeighbor = Math.round(
    elevations.reduce((sum, value) => sum + value, 0) / elevations.length,
  );
  const diff = Math.round(self - avgNeighbor);
  const tendency =
    diff <= -3 ? "地勢偏低，易累積車輛" : diff >= 3 ? "地勢偏高，車輛易流出" : "與鄰站相近";

  return { self, avgNeighbor, diff, tendency };
}

// 尚未接入真實資料源的站點屬性（誠實列出，不以假值冒充）。
export const PENDING_DATA_SOURCES = Object.freeze([
  "即時天氣（每站點級）",
  "實測高程（DEM／API）",
  "周邊人流／捷運進出量",
  "即時路況與調度 ETA",
  "最近一次調度時間與頻率",
]);

// 依站名關鍵字推斷站點特徵；規則透明、可追溯，不引入外部資料。
export function deriveStationTags(station) {
  const name = station?.station_name ?? "";
  const tags = [];

  if (/捷運/.test(name)) tags.push("捷運站旁");
  else if (/車站/.test(name)) tags.push("交通樞紐");
  else if (/站(\(|$)/.test(name)) tags.push("交通節點");

  if (/(國小|國中|高中|高工|國民小學|大學|學院|科大|學校)/.test(name)) {
    tags.push("學區");
  }
  if (/(運動中心|體育|公園|游泳|運動場)/.test(name)) tags.push("休閒運動");
  if (/(Outlet|outlet|購物|商場|百貨|市場|夜市|商圈)/.test(name)) {
    tags.push("商業");
  }
  if (/醫院|診所/.test(name)) tags.push("醫療");

  if (!tags.length) {
    const areaTag = areaTypeLabels[station?.area_type];
    tags.push(areaTag ?? "住宅／混合");
  }

  return [...new Set(tags)];
}
