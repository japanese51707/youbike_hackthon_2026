// 調度路線規劃（示意 Mock）——透明、確定性的貪婪規則。
//
// 重要邊界（ADR-004）：這不是正式最佳化，真正的路線最佳化屬後端規則引擎。
// 本模組只用既有 mock 站況與載具位置產生「示意路線」供前端展示，
// 不做真實決策、不進派遣 payload。規則完全透明可追溯：
//   1. 只納入服務半徑內、且有取/補需求的站點。
//   2. 以「缺口/溢出嚴重度優先，再取最近」貪婪串接路線。
//   3. 取/補數量依站點容量與目標水位估算。

import { haversineKm } from "./geo.js";

const DEFICIT_STATUS = ["empty", "low"];
const SURPLUS_STATUS = ["full", "high"];

function severity(station) {
  if (station.status === "empty" || station.status === "full") return 3;
  if (station.status === "low" || station.status === "high") return 2;
  return 0;
}

// 依容量與目標水位估算取/補數量（示意值）。
export function estimateQuantity(station, targetRatio) {
  const capacity = Number(station.total_docks) || 0;
  const available = Number(station.available_bikes) || 0;
  const target = capacity * targetRatio;
  if (DEFICIT_STATUS.includes(station.status)) {
    return Math.max(0, Math.round(target - available));
  }
  if (SURPLUS_STATUS.includes(station.status)) {
    return Math.max(0, Math.round(available - target));
  }
  return 0;
}

// 目前可用載具：有座標、非離勤/休息、且手上沒有任務。
export function availableVehicles(operators) {
  return (operators ?? []).filter(
    (op) =>
      op.current_location &&
      Number.isFinite(Number(op.current_location.lat)) &&
      Number.isFinite(Number(op.current_location.lng)) &&
      op.status !== "off_duty" &&
      op.status !== "resting" &&
      !op.current_task_id,
  );
}

// 司機接單後的停靠序列（示意）：先取車後補車，各自從目前位置就近串接。
// 純操作型排序，非派工決策（守 ADR-004）；不進派遣 payload。
export function sequenceDriverRoute(start, acceptedStops) {
  if (!start || !Array.isArray(acceptedStops) || !acceptedStops.length) {
    return { start, route: [], totalDistanceKm: 0 };
  }

  const chainNearest = (items, from) => {
    const remaining = [...items];
    const ordered = [];
    let cursor = from;
    while (remaining.length) {
      remaining.sort(
        (a, b) =>
          haversineKm(cursor, { lat: a.lat, lng: a.lng }) -
          haversineKm(cursor, { lat: b.lat, lng: b.lng }),
      );
      const next = remaining.shift();
      const legKm = haversineKm(cursor, { lat: next.lat, lng: next.lng });
      ordered.push({ ...next, leg_km: Number(legKm.toFixed(2)) });
      cursor = { lat: next.lat, lng: next.lng };
    }
    return { ordered, cursor };
  };

  const pickups = acceptedStops.filter((s) => s.action === "取車");
  const dropoffs = acceptedStops.filter((s) => s.action !== "取車");

  const first = chainNearest(pickups, start);
  const second = chainNearest(dropoffs, first.cursor);
  const route = [...first.ordered, ...second.ordered];
  const totalDistanceKm = Number(
    route.reduce((sum, stop) => sum + stop.leg_km, 0).toFixed(2),
  );

  return { start, route, totalDistanceKm };
}

export function planRouteForVehicle(vehicle, stations, config) {
  const { serviceRadiusKm, maxStops, targetRatio } = config;
  const start = {
    lat: Number(vehicle.current_location.lat),
    lng: Number(vehicle.current_location.lng),
  };

  const candidates = (stations ?? []).filter((station) => {
    const relevant =
      DEFICIT_STATUS.includes(station.status) ||
      SURPLUS_STATUS.includes(station.status);
    if (!relevant) return false;
    if (estimateQuantity(station, targetRatio) <= 0) return false;
    return (
      haversineKm(start, { lat: station.lat, lng: station.lng }) <=
      serviceRadiusKm
    );
  });

  const remaining = [...candidates];
  const route = [];
  let cursor = start;

  while (route.length < maxStops && remaining.length) {
    remaining.sort((a, b) => {
      const sev = severity(b) - severity(a);
      if (sev !== 0) return sev;
      return (
        haversineKm(cursor, { lat: a.lat, lng: a.lng }) -
        haversineKm(cursor, { lat: b.lat, lng: b.lng })
      );
    });
    const next = remaining.shift();
    const legKm = haversineKm(cursor, { lat: next.lat, lng: next.lng });
    route.push({
      station_id: next.station_id,
      station_name: next.station_name,
      lat: Number(next.lat),
      lng: Number(next.lng),
      status: next.status,
      action: DEFICIT_STATUS.includes(next.status) ? "補車" : "取車",
      quantity: estimateQuantity(next, targetRatio),
      leg_km: Number(legKm.toFixed(2)),
    });
    cursor = { lat: next.lat, lng: next.lng };
  }

  const totalDistanceKm = Number(
    route.reduce((sum, stop) => sum + stop.leg_km, 0).toFixed(2),
  );

  return { vehicle, start, route, totalDistanceKm, radiusKm: serviceRadiusKm };
}
