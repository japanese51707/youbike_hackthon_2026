export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return "—";
  }
  return new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: digits,
  }).format(Number(value));
}

export function formatCurrency(value) {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("zh-TW", {
    style: "currency",
    currency: "TWD",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatDateTime(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

// 解析站點時間戳，支援兩種格式：
//   ISO（系統 timestamp，如 2026-09-10T23:20:57+08:00）
//   官方/CWA 緊湊格式（source_timestamp，如 20260910T231902，視為台北時間）
export function parseStationTime(value) {
  if (!value || typeof value !== "string") return null;
  const compact = value.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})$/);
  if (compact) {
    const [, y, mo, d, h, mi, s] = compact;
    const dt = new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}+08:00`);
    return Number.isNaN(dt.getTime()) ? null : dt;
  }
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? null : dt;
}

// 站點資料時間（含秒），優先用資料源更新時間 source_timestamp，退回系統 timestamp。
export function formatStationTime(station, { withSeconds = true } = {}) {
  const date =
    parseStationTime(station?.source_timestamp) ||
    parseStationTime(station?.timestamp);
  if (!date) return "—";
  return date.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    ...(withSeconds ? { second: "2-digit" } : {}),
    hour12: false,
  });
}

export const stationStatusLabels = {
  offline: "暫停營運",
  empty: "無車可借",
  low: "偏低",
  normal: "正常",
  high: "偏高",
  full: "車位滿載",
};

export const terrainLabels = {
  flat: "平地",
  gentle_up: "緩上坡",
  gentle_down: "緩下坡",
  moderate_up: "中上坡",
  moderate_down: "中下坡",
  steep_up: "陡上坡",
  steep_down: "陡下坡",
};

export const areaTypeLabels = {
  transit: "轉乘站",
  school: "學區",
  leisure: "休閒",
  commercial: "商業區",
  mixed: "混合",
  residential: "住宅區",
};

export const freshnessLabels = {
  mock: "Mock 展示",
  historical: "歷史快照",
  historical_fallback: "歷史推估",
  live: "即時",
  stale: "延遲",
  cached: "快取",
};

export const taskStatusLabels = {
  assigned: "已指派",
  in_progress: "執行中",
  completed: "已完成",
};
