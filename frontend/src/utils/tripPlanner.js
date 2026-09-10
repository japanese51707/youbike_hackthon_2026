// 互動式派工單組建（ADR-119 三入口）——前端示意版。
//
// 重要邊界（ADR-004 / ADR-206）：這不是正式最佳化。真正的最優組單、載運量切趟、
// 跨區/預備車決策屬後端 dispatch_builder。本模組只用既有 mock 站況與載具位置，
// 產生「先載後放」的示意草稿供調派員預覽，不做真實決策、不進派遣 payload。
// 規則完全透明、確定性、可追溯。

import { tripPlannerConfig } from "../config/fleetMock.js";
import { haversineKm } from "./geo.js";

const DEFICIT_STATUS = new Set(["empty", "low"]);
const SURPLUS_STATUS = new Set(["full", "high"]);

// 站點狀態嚴重度（先處理最極端的空/滿站）。
function severity(station) {
  if (station.status === "empty" || station.status === "full") return 3;
  if (station.status === "low" || station.status === "high") return 2;
  return 0;
}

// 站點緊急度代理值（0~100，示意）：優先用既有 urgency_score，否則依狀態估。
export function stationUrgency(station) {
  if (Number.isFinite(Number(station.urgency_score))) {
    return Number(station.urgency_score);
  }
  const byStatus = { empty: 95, full: 80, low: 60, high: 55, normal: 20 };
  return byStatus[station.status] ?? 0;
}

// 依容量與目標水位估算取/補數量（示意值，與 dispatchPlanner 同口徑）。
export function estimateQuantity(station, targetRatio = tripPlannerConfig.targetRatio) {
  const capacity = Number(station.total_docks) || 0;
  const available = Number(station.available_bikes) || 0;
  const target = capacity * targetRatio;
  if (DEFICIT_STATUS.has(station.status)) {
    return Math.max(0, Math.round(target - available));
  }
  if (SURPLUS_STATUS.has(station.status)) {
    return Math.max(0, Math.round(available - target));
  }
  return 0;
}

function hasCoords(o) {
  const lat = Number(o?.lat ?? o?.current_location?.lat);
  const lng = Number(o?.lng ?? o?.current_location?.lng);
  return Number.isFinite(lat) && Number.isFinite(lng);
}

function pointOf(o) {
  return {
    lat: Number(o.lat ?? o.current_location?.lat),
    lng: Number(o.lng ?? o.current_location?.lng),
  };
}

// 常態可用車：狀態 available 且非戰備預備車（standby 只由緊急動用）。
export function availableVehicles(vehicles) {
  return (vehicles ?? []).filter(
    (v) => v.status === "available" && !v.is_reserve && hasCoords(v),
  );
}

// 以站找車的候選順序（ADR-119 入口 b）：該區閒置 → 鄰近區閒置 → 總站待命。
// emergency 也用同序（就近閒置車優先於預備車）。
export function vehicleCandidatesForStation(station, vehicles, { includeReserve = true } = {}) {
  if (!station || !hasCoords(station)) return [];
  const here = pointOf(station);
  const withDist = (v) => ({
    vehicle: v,
    km: haversineKm(here, pointOf(v)),
  });

  const idleSameDistrict = (vehicles ?? [])
    .filter(
      (v) =>
        v.status === "available" &&
        !v.is_reserve &&
        hasCoords(v) &&
        v.current_district === station.district,
    )
    .map(withDist)
    .map((c) => ({ ...c, tier: "該區閒置" }));

  const idleNearby = (vehicles ?? [])
    .filter(
      (v) =>
        v.status === "available" &&
        !v.is_reserve &&
        hasCoords(v) &&
        v.current_district !== station.district,
    )
    .map(withDist)
    .sort((a, b) => a.km - b.km)
    .map((c) => ({ ...c, tier: "鄰近區閒置" }));

  const standby = includeReserve
    ? (vehicles ?? [])
        .filter((v) => v.is_reserve && hasCoords(v) && v.status !== "maintenance")
        .map(withDist)
        .map((c) => ({ ...c, tier: "總站待命" }))
    : [];

  return [...idleSameDistrict, ...idleNearby, ...standby];
}

// 就近串接（貪婪最近鄰），回傳排序後的停靠與各段距離。
function chainNearest(items, from) {
  const remaining = [...items];
  const ordered = [];
  let cursor = from;
  while (remaining.length) {
    remaining.sort(
      (a, b) => haversineKm(cursor, pointOf(a)) - haversineKm(cursor, pointOf(b)),
    );
    const next = remaining.shift();
    const legKm = haversineKm(cursor, pointOf(next));
    ordered.push({ ...next, leg_km: Number(legKm.toFixed(2)) });
    cursor = pointOf(next);
  }
  return { ordered, cursor };
}

// 核心：從起點組出「先載後放」草稿。
// start：{lat,lng}；stations：候選站清單；seed：可選的優先站（點進來的那站）。
function composeTrip({ start, stations, seed, capacity, cfg }) {
  const targetRatio = cfg.targetRatio;
  const withQty = (list) =>
    list
      .filter(hasCoords)
      .map((s) => ({ ...s, _qty: estimateQuantity(s, targetRatio) }))
      .filter((s) => s._qty > 0);

  const surplus = withQty((stations ?? []).filter((s) => SURPLUS_STATUS.has(s.status)));
  const deficit = withQty((stations ?? []).filter((s) => DEFICIT_STATUS.has(s.status)));

  const bySeverityThenNear = (from) => (a, b) => {
    const sev = severity(b) - severity(a);
    if (sev !== 0) return sev;
    return haversineKm(from, pointOf(a)) - haversineKm(from, pointOf(b));
  };

  // seed 若是缺車站，優先排進補車清單；若是滿站，優先排進取車清單。
  const seedIsDeficit = seed && DEFICIT_STATUS.has(seed.status);
  const seedIsSurplus = seed && SURPLUS_STATUS.has(seed.status);

  // 取車（先載）：從滿站載車直到接近載運上限。
  const pickPool = [...surplus].sort(bySeverityThenNear(start));
  if (seedIsSurplus) {
    const idx = pickPool.findIndex((s) => s.station_id === seed.station_id);
    if (idx > 0) pickPool.unshift(pickPool.splice(idx, 1)[0]);
  }
  const pickups = [];
  let carried = 0;
  for (const s of pickPool) {
    if (pickups.length >= cfg.maxPickups || carried >= capacity) break;
    const take = Math.min(s._qty, capacity - carried);
    if (take <= 0) continue;
    pickups.push({ ...s, action: "取車", quantity: take });
    carried += take;
  }

  // 補車（後放）：把載到的車放到缺車站，直到放完。
  const dropPool = [...deficit].sort(bySeverityThenNear(start));
  if (seedIsDeficit) {
    const idx = dropPool.findIndex((s) => s.station_id === seed.station_id);
    if (idx > 0) dropPool.unshift(dropPool.splice(idx, 1)[0]);
  }
  const dropoffs = [];
  let remaining = carried;
  for (const s of dropPool) {
    if (dropoffs.length >= cfg.maxDropoffs || remaining <= 0) break;
    const give = Math.min(s._qty, remaining);
    if (give <= 0) continue;
    dropoffs.push({ ...s, action: "補車", quantity: give });
    remaining -= give;
  }

  // 路線：起點 → 取車鏈 → 補車鏈（先載後放）。
  const pickChain = chainNearest(pickups, start);
  const dropChain = chainNearest(dropoffs, pickChain.cursor);
  const orderedStops = [...pickChain.ordered, ...dropChain.ordered].map((s, i) => ({
    seq: i + 1,
    station_id: s.station_id,
    station_name: s.station_name,
    district: s.district,
    lat: Number(s.lat),
    lng: Number(s.lng),
    status: s.status,
    action: s.action,
    quantity: s.quantity,
    leg_km: s.leg_km,
    stop_status: "pending",
  }));

  const distanceKm = Number(
    orderedStops.reduce((sum, s) => sum + (s.leg_km || 0), 0).toFixed(2),
  );
  const travelMin = Math.round((distanceKm / cfg.avgSpeedKmh) * 60);
  const workMin = orderedStops.length * cfg.perStopMinutes;
  const urgencySum = orderedStops.reduce(
    (sum, s) => sum + stationUrgency(s),
    0,
  );

  return {
    stops: orderedStops,
    estimate: {
      distanceKm,
      travelMin,
      workMin,
      totalMin: travelMin + workMin,
      capacity,
      capacityUsed: carried,
      unplacedBikes: remaining,
      urgencySum,
    },
  };
}

function capacityOf(vehicle) {
  return Number(vehicle?.max_capacity) || tripPlannerConfig.fallbackCapacity;
}

// 入口 a：以車為起點。用車當前位置排出最適出車站點順序（同區為主）。
export function buildFromVehicle(vehicle, stations, { district, cfg = tripPlannerConfig } = {}) {
  if (!vehicle || !hasCoords(vehicle)) return null;
  const targetDistrict = district || vehicle.current_district || null;
  const scope = targetDistrict
    ? (stations ?? []).filter((s) => s.district === targetDistrict)
    : stations;
  const start = pointOf(vehicle);
  const { stops, estimate } = composeTrip({
    start,
    stations: scope,
    seed: null,
    capacity: capacityOf(vehicle),
    cfg,
  });
  return {
    mode: "vehicle",
    vehicle,
    district: targetDistrict,
    start,
    stops,
    estimate,
    crossDistrict: false,
  };
}

// 入口 b：以站為起點。系統找可用車（該區→鄰近→總站待命）+ 算站點順序。
export function buildFromStation(station, stations, vehicles, { vehicle, cfg = tripPlannerConfig } = {}) {
  if (!station) return null;
  const candidates = vehicleCandidatesForStation(station, vehicles);
  const chosen = vehicle || candidates[0]?.vehicle || null;
  const start = chosen ? pointOf(chosen) : pointOf(station);
  // 補車需先有車可載：同區可能只有缺車站，故取車來源放寬到全體滿站（示意，跨區以旗標標示）。
  const scope = stations;
  const { stops, estimate } = composeTrip({
    start,
    stations: scope,
    seed: station,
    capacity: capacityOf(chosen),
    cfg,
  });
  const crossDistrict = stops.some((s) => s.district !== station.district);
  return {
    mode: "station",
    vehicle: chosen,
    candidates,
    seedStation: station,
    district: station.district,
    start,
    stops,
    estimate,
    crossDistrict,
  };
}

// 入口 c：緊急出車。資源優先序＝就近閒置車 > 預備車（含 standby）；可跨區。
export function buildEmergency(seedStation, stations, vehicles, { vehicle, cfg = tripPlannerConfig } = {}) {
  if (!seedStation) return null;
  const candidates = vehicleCandidatesForStation(seedStation, vehicles, {
    includeReserve: true,
  });
  const chosen = vehicle || candidates[0]?.vehicle || null;
  const start = chosen ? pointOf(chosen) : pointOf(seedStation);
  const { stops, estimate } = composeTrip({
    start,
    stations,
    seed: seedStation,
    capacity: capacityOf(chosen),
    cfg,
  });
  const crossDistrict = stops.some((s) => s.district !== seedStation.district);
  return {
    mode: "emergency",
    vehicle: chosen,
    candidates,
    seedStation,
    district: seedStation.district,
    start,
    stops,
    estimate,
    crossDistrict,
  };
}
