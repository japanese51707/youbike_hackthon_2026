/**
 * 調度建議分流：「緊急調度」與「次安排調度」（ADR-111 三層觸發的前端呈現）
 *
 * 緊急 = urgency_tier === "censored"（已空／已滿且仍在繼續流失，需求被壓抑，
 *        觀測到的缺口一定是低估的）或 priority_level === "high"
 *        （緊急度分數 ≥ config.priority_band.high_min，預設 70）。
 * 其餘一律次安排。
 *
 * ★判斷只讀後端既有欄位，前端不自己算緊急度——緊急度是 urgency + dispatcher 的職責
 *   （ADR-104：前端不得成為第二套觸發邏輯）。同時吃後端原始鍵（snake_case）與
 *   DashboardPage 整理過的 urgencyItems（camelCase）；舊資料沒有 urgency_tier 時
 *   自動只看 priority_level，不會壞。
 */

export const URGENT = "urgent";
export const SCHEDULED = "scheduled";

export const TRIAGE_LABELS = {
  [URGENT]: "緊急調度",
  [SCHEDULED]: "次安排調度",
};

export const TRIAGE_HINTS = {
  [URGENT]: "已觸底或緊急度高，需要立刻找人出車",
  [SCHEDULED]: "還有時間，可以排進後續班次",
};

const tierOf = (item) => item?.urgency_tier ?? item?.urgencyTier;
const levelOf = (item) => item?.priority_level ?? item?.priorityLevel;

export function triageOf(item) {
  if (!item) return SCHEDULED;
  if (tierOf(item) === "censored") return URGENT;
  if (levelOf(item) === "high") return URGENT;
  return SCHEDULED;
}

export function splitByTriage(items = []) {
  const urgent = [];
  const scheduled = [];
  for (const item of items) {
    (triageOf(item) === URGENT ? urgent : scheduled).push(item);
  }
  return { urgent, scheduled };
}

/** urgencyItems 的行政區在 item.station.district；後端原始建議在 item.district。 */
export const districtOf = (item) =>
  item?.station?.district ?? item?.district ?? "未分區";

export const stationIdOf = (item) =>
  item?.station?.station_id ?? item?.station_id ?? null;

/** 依行政區統計任務數，多的排前面；同數以中文序穩定排序。 */
export function countByDistrict(items = []) {
  const counts = new Map();
  for (const item of items) {
    const district = districtOf(item);
    counts.set(district, (counts.get(district) || 0) + 1);
  }
  return [...counts.entries()]
    .map(([district, count]) => ({ district, count }))
    .sort((a, b) => b.count - a.count || a.district.localeCompare(b.district, "zh-TW"));
}

export function filterByDistrict(items = [], district) {
  if (!district || district === "all") return items;
  return items.filter((item) => districtOf(item) === district);
}

export function stationIdsOf(items = []) {
  return new Set(items.map(stationIdOf).filter(Boolean));
}
