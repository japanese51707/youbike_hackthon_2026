// ADR-309：緊急調度案件升級追蹤。時間一律用後端回的欄位，前端不自己累加計時。
import { isApiMode, request } from "./httpClient.js";

export const STAGE_LABELS = ["已開案", "需再提示", "需核實／電話聯絡", "需安排支援"];
export const CLOSE_LABELS = { dispatched: "已派工（舊規則）", recovered: "確認站況恢復" };
export const ACTION_LABELS = {
  acknowledged: "已讀（暫時靜音）",
  called: "已電話聯絡",
  deferred: "延後處理",
  dispatch: "轉去組單",
};

const EMPTY = { cases: [], counts: { open: 0, banner: 0, prompt: 0 } };

export async function getEscalations() {
  if (!isApiMode) return EMPTY;
  return request("/alerts/escalations", { timeoutMs: 45_000 });
}

/** ADR-335：我的分級提醒（後端依登入身分授權，司機只拿得到自己的）。 */
export async function getMyNotifications() {
  if (!isApiMode) return { notifications: [] };
  return request("/alerts/notifications");
}

/** action：seen / ack / mute —— 只會動到自己那一筆，不替別人消音。 */
export async function markNotification(notificationId, action) {
  return request(
    `/alerts/notifications/${encodeURIComponent(notificationId)}/${encodeURIComponent(action)}`,
    { method: "POST" });
}

export async function getEscalationHistory(limit = 100) {
  if (!isApiMode) return [];
  return request(`/alerts/escalations/history?limit=${encodeURIComponent(limit)}`);
}

/** action：acknowledged / called / deferred / dispatch */
export async function recordCaseAction(caseId, action, { note = "", contact = "" } = {}) {
  return request(`/alerts/escalations/${encodeURIComponent(caseId)}/${encodeURIComponent(action)}`, {
    method: "POST",
    body: { note, contact },
  });
}

const DEFAULT_STAGE_MINUTES = [30, 45, 60];
const NEXT_STAGE_LABELS = ["需再提示", "需電話聯絡", "最高催辦"];

/** 無時區的開案時間當台北牆上時間，避免被當成 UTC 多算 8 小時。 */
export function parseCaseTime(value) {
  if (value == null) return NaN;
  const text = String(value).trim();
  if (!text) return NaN;
  if (/[zZ]|[+-]\d{2}:?\d{2}$/.test(text)) return Date.parse(text);
  if (/^\d{4}-\d{2}-\d{2}T/.test(text)) return Date.parse(`${text}+08:00`);
  return Date.parse(text);
}

/** 從開案時間算出已等待幾分鐘（後端沒帶回 waited_minutes 時用）。 */
export function waitedSince(openedAt, nowMs = Date.now()) {
  const opened = parseCaseTime(openedAt);
  if (!Number.isFinite(opened)) return null;
  return Math.max(0, (nowMs - opened) / 60000);
}

/** 下一欄：開案後 30／45／60 分升級，不是數到幾百小時。 */
export function nextChaseCopy(row, nowMs = Date.now()) {
  const thresholds = Array.isArray(row?.stage_thresholds) && row.stage_thresholds.length
    ? row.stage_thresholds
    : DEFAULT_STAGE_MINUTES;
  const waited = waitedSince(row?.opened_at, nowMs) ?? Number(row?.waited_minutes) ?? 0;
  let stage = 0;
  thresholds.forEach((limit, index) => {
    if (waited >= limit) stage = index + 1;
  });
  if (stage >= thresholds.length) {
    return "已滿 60 分（最高催辦），約每 15 分再提醒，直到站況恢復";
  }
  const remain = Math.max(0, Math.round(thresholds[stage] - waited));
  return `還有 ${remain} 分到「${NEXT_STAGE_LABELS[stage] ?? "下一階段"}」（滿 ${thresholds[stage]} 分）`;
}

/** 把分鐘數講成人看得懂的話。 */
export function formatWaited(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return "—";
  const total = Math.max(0, Math.round(Number(minutes)));
  if (total < 60) return `${total} 分`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${hours} 小時 ${rest} 分` : `${hours} 小時`;
}
