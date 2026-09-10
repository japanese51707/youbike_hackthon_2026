import { mockAdapter } from "./mockAdapter.js";

// 司機手機端資料：以現有調度建議當「任務池」，並取一名操作員位置作為出發點。
// 全部來自既有 mock，不新增後端契約；接單/完成僅存在前端頁面狀態（示意）。
export async function getDriverWorkspace() {
  const [dashboard, workspace] = await Promise.all([
    mockAdapter.getDashboard(),
    mockAdapter.getOperatorWorkspace(),
  ]);

  const operator =
    workspace.operators.find((op) => op.role === "operator") ??
    workspace.operators[0] ??
    null;

  return {
    operator,
    recommendations: dashboard.recommendations,
    stations: dashboard.stations,
  };
}
