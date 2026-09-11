import { isApiMode, request } from "./httpClient.js";
import { mockAdapter } from "./mockAdapter.js";

export function getOperatorWorkspace() {
  if (isApiMode) return Promise.all([request("/dispatch/tasks"), request("/operators")]).then(([tasks, operators]) => ({ tasks, operators }));
  return mockAdapter.getOperatorWorkspace();
}

export function completeTaskStop(taskId, sequence) {
  if (isApiMode) throw new Error("請使用司機頁輸入現場存量逐站回報");
  return mockAdapter.completeTaskStop(taskId, sequence);
}

export function getOperationsOverview() {
  if (isApiMode) return request("/dispatch/overview");
  return mockAdapter.getOverview();
}

export function resetDemoData() {
  if (isApiMode) throw new Error("後端模式不提供展示資料重置");
  return mockAdapter.resetDemo();
}
