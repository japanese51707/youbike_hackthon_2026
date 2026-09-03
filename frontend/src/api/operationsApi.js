import { mockAdapter } from "./mockAdapter.js";

export function getOperatorWorkspace() {
  return mockAdapter.getOperatorWorkspace();
}

export function completeTaskStop(taskId, sequence) {
  return mockAdapter.completeTaskStop(taskId, sequence);
}

export function getOperationsOverview() {
  return mockAdapter.getOverview();
}

export function resetDemoData() {
  return mockAdapter.resetDemo();
}
