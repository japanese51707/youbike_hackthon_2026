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
  empty: "空站",
  low: "偏低",
  normal: "正常",
  high: "偏高",
  full: "滿站",
};

export const taskStatusLabels = {
  assigned: "已指派",
  in_progress: "執行中",
  completed: "已完成",
};
