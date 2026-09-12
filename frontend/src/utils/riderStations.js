// 騎乘者找站：服務等級與附近推薦。
// 分級目前依站名關鍵字、area_type、車柱數推估，與實際尖峰調度名單會有誤差。
// 排序以步行距離為主，庫存遞減、等級只做小幅加分；一般站不扣分。
// 只供騎乘者參考，不是規則引擎的派工決策（守 ADR-004／ADR-104）。

import { haversineKm } from "./geo.js";

export const SERVICE_GRADES = {
  core: {
    key: "core",
    label: "核心站",
    hint: "規模較大，比較不容易一下子借光",
    color: "gold",
    halo: [212, 160, 48, 210],
    haloRadius: 20,
    weight: 1.08,
    peakWeight: 1.18,
  },
  priority: {
    key: "priority",
    label: "重點站",
    hint: "人流較多，車位通常也較多",
    color: "blue",
    halo: [47, 110, 196, 190],
    haloRadius: 16,
    weight: 1.04,
    peakWeight: 1.1,
  },
  neighbor: {
    key: "neighbor",
    label: "一般站",
    hint: "以步行距離為主",
    color: "default",
    halo: [150, 150, 150, 70],
    haloRadius: 10,
    weight: 1,
    peakWeight: 1,
  },
};

const CORE_NAME = /捷運|轉運|車站|高鐵|台鐵|臺鐵|客運/;
const PRIORITY_NAME = /醫院|運動中心|Outlet|大學|高中|國中|國小/;

export function deriveServiceGrade(station) {
  const name = String(station?.station_name || "");
  const docks = Number(station?.total_docks);
  const area = station?.area_type;
  if (area === "transit" || CORE_NAME.test(name) || (Number.isFinite(docks) && docks >= 60)) {
    return SERVICE_GRADES.core;
  }
  if (
    area === "school" ||
    area === "commercial" ||
    PRIORITY_NAME.test(name) ||
    (Number.isFinite(docks) && docks >= 40)
  ) {
    return SERVICE_GRADES.priority;
  }
  return SERVICE_GRADES.neighbor;
}

// 北北基大致範圍；新竹約 24.81, 120.97，會被 lng 擋下。
const SERVICE_BBOX = { minLat: 24.84, maxLat: 25.32, minLng: 121.28, maxLng: 122.05 };
const SERVICE_NEAR_KM = 20;

export function isInRiderServiceArea(origin, stations = []) {
  const lat = Number(origin?.lat);
  const lng = Number(origin?.lng);
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  const nearby = (stations || []).filter((station) => Number.isFinite(Number(station?.lat)) && Number.isFinite(Number(station?.lng)));
  if (nearby.length) {
    return nearby.some((station) => haversineKm(origin, station) <= SERVICE_NEAR_KM);
  }
  return lat >= SERVICE_BBOX.minLat && lat <= SERVICE_BBOX.maxLat && lng >= SERVICE_BBOX.minLng && lng <= SERVICE_BBOX.maxLng;
}

export function isPeakHour(now = new Date()) {
  const hour = now.getHours();
  const weekend = now.getDay() === 0 || now.getDay() === 6;
  if (weekend) return hour >= 10 && hour < 20;
  return (hour >= 7 && hour < 9) || (hour >= 17 && hour < 19);
}

function walkMinutes(distanceKm) {
  if (!Number.isFinite(distanceKm)) return null;
  return Math.max(1, Math.round((distanceKm * 1000) / 80));
}

function stockOf(station, intent) {
  const key = intent === "return" ? "available_docks" : "available_bikes";
  const value = Number(station?.[key]);
  return Number.isFinite(value) ? value : 0;
}

// 騎乘者要的是「走過去還借得到／還得掉」，不是派工優先序。
// 距離主導；庫存 3～5 台就夠用，再多幾乎不再加分；等級只做小幅加分，一般站不扣分。
function reliability(stock) {
  return 1 - Math.exp(-Math.max(0, stock) / 4);
}

function walkCost(distanceKm) {
  return (distanceKm + 0.06) ** 1.45;
}

export function riderScore({ available, stock, distanceKm, grade, peak }) {
  if (!available || !Number.isFinite(distanceKm)) return -1;
  const boost = peak ? grade.peakWeight : grade.weight;
  return (reliability(stock) * boost) / walkCost(distanceKm);
}

export function recommendNearbyStations({
  stations = [],
  origin,
  intent = "rent",
  now = new Date(),
  limit = 6,
  maxKm = 2,
} = {}) {
  const peak = isPeakHour(now);
  const rows = (stations || [])
    .map((station) => {
      const grade = deriveServiceGrade(station);
      const distanceKm = haversineKm(origin, station);
      const stock = stockOf(station, intent);
      const online = station?.service_available !== false && station?.status !== "offline";
      const available = online && stock > 0;
      const score = riderScore({ available, stock, distanceKm, grade, peak });
      const reasons = [];
      if (Number.isFinite(distanceKm)) reasons.push(`步行約 ${walkMinutes(distanceKm)} 分鐘`);
      reasons.push(intent === "return" ? `可還 ${stock} 位` : `可借 ${stock} 台`);
      reasons.push(peak ? `${grade.label}，${grade.hint}` : grade.label);
      return {
        ...station,
        grade,
        distanceKm,
        stock,
        available,
        walkMin: walkMinutes(distanceKm),
        score,
        reasons,
      };
    })
    .filter((row) => Number.isFinite(row.distanceKm) && row.distanceKm <= maxKm);

  const items = rows
    .filter((row) => row.available)
    .sort((a, b) => b.score - a.score || a.distanceKm - b.distanceKm)
    .slice(0, limit);

  return {
    peak,
    intent,
    items,
    unavailable: rows
      .filter((row) => !row.available)
      .sort((a, b) => a.distanceKm - b.distanceKm)
      .slice(0, 3),
  };
}

export function walkDirectionsUrl(origin, station) {
  if (!origin || !station) return null;
  const lat1 = Number(origin.lat);
  const lng1 = Number(origin.lng);
  const lat2 = Number(station.lat);
  const lng2 = Number(station.lng);
  if (![lat1, lng1, lat2, lng2].every(Number.isFinite)) return null;
  return `https://www.google.com/maps/dir/?api=1&origin=${lat1},${lng1}&destination=${lat2},${lng2}&travelmode=walking`;
}
