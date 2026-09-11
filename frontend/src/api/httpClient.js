// ADR-206: API failures stay visible; switching to Mock is always explicit.
export const dataMode = import.meta.env?.VITE_DATA_MODE || "api";
export const isApiMode = dataMode !== "mock";
const baseUrl = (import.meta.env?.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
const actorKey = "youbike.demo.operator";
export const getActorId = () => globalThis.sessionStorage?.getItem(actorKey) || "";
export const setActorId = (id) => globalThis.sessionStorage?.setItem(actorKey, id || "");

export async function request(path, { method = "GET", body, timeoutMs = 20000, actorId = getActorId() } = {}) {
  if (method !== "GET" && !actorId) throw new Error("請先選擇操作身分");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${baseUrl}${path}`, {
      method, signal: controller.signal,
      headers: { Accept: "application/json", ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
        ...(actorId ? { "X-Operator-Id": actorId } : {}) },
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
    const payload = await response.json().catch(() => null);
    if (!response.ok) {
      const error = new Error(typeof payload?.message === "string" ? payload.message : `服務請求失敗（${response.status}）`);
      error.status = response.status;
      error.details = payload?.details;
      throw error;
    }
    if (payload === null) throw new Error("服務回傳格式不正確");
    return payload;
  } catch (error) {
    if (error.name === "AbortError") throw new Error("服務回應逾時，請重新整理確認結果");
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}
