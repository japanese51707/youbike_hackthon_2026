import { request } from "./httpClient.js";

// 實走道路路線（後端 /routing/road）。
// 後端保證一定回得了東西：路由服務不可用時會回 mode="straight" 的直線幾何，
// 呼叫端要照實把 mode 顯示出來，不要假裝是實走路線。
export function getRoadRoute(coordinates) {
  return request("/routing/road", { method: "POST", body: { coordinates } });
}
