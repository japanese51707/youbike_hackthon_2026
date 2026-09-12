// ADR-309：緊急調度案件升級追蹤。時間一律用後端回的欄位，前端不自己累加計時。
import { isApiMode, request } from "./httpClient.js";

export const STAGE_LABELS = ["已開案", "需再提示", "需電話聯絡"];
export const CLOSE_LABELS = { dispatched: "已派工", recovered: "站況恢復" };
export const ACTION_LABELS = {
  acknowledged: "已讀（暫時靜音）",
  called: "已電話聯絡",
  deferred: "延後處理",
  dispatch: "轉去組單",
};

const EMPTY = { cases: [], counts: { open: 0, banner: 0, prompt: 0 } };

export async function getEscalations() {
  if (!isApiMode) return EMPTY;
  return request("/alerts/escalations");
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

/** 把分鐘數講成人看得懂的話。 */
export function formatWaited(minutes) {
  if (minutes === null || minutes === undefined || Number.isNaN(Number(minutes))) return "—";
  const total = Math.max(0, Math.round(Number(minutes)));
  if (total < 60) return `${total} 分`;
  const hours = Math.floor(total / 60);
  const rest = total % 60;
  return rest ? `${hours} 小時 ${rest} 分` : `${hours} 小時`;
}
