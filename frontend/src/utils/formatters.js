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

export const stationStatusLabels = {
  offline: "停用／離線",
  empty: "空站",
  low: "偏低",
  normal: "正常",
  high: "偏高",
  full: "滿站",
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
