import { isApiMode, request } from "./httpClient.js";
import { applyStationDecision, createMockReview } from "../utils/optimizationReview.js";

let mockReview = null;

function mockStore() {
  if (!mockReview) mockReview = createMockReview();
  return mockReview;
}

function delay(value) {
  return new Promise((resolve) => {
    window.setTimeout(() => resolve(value), 180);
  });
}

// ADR-120/304：每日最適化建議。status 有四種，只有 ok 可以套用。
// Mock／示意路徑只改本機暫存，不打後端、不派工。
export const getDailyReview = (params = {}) => {
  if (!isApiMode) {
    mockReview = createMockReview();
    return delay(mockStore());
  }
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""),
  ).toString();
  return request(`/optimization/daily-review${query ? `?${query}` : ""}`);
};

// 逐站二次定義：accept（照建議）/ keep（維持原值）/ re_adjust（人工改值）
export const decideStation = (reviewId, stationId, decision, params) => {
  if (!isApiMode || reviewId?.startsWith("REV-MOCK-")) {
    const review = mockStore();
    review.station_changes = applyStationDecision(review.station_changes, stationId, decision);
    return delay({ review_id: review.review_id, station_id: stationId, decision, params: params ?? null });
  }
  return request(`/optimization/daily-review/station/${encodeURIComponent(stationId)}`, {
    method: "POST",
    body: { review_id: reviewId, decision, ...(params ? { params } : {}) },
  });
};

// ADR-304：approve 必帶 review_id；同一個 review_id 重送回原結果、不重複寫版本
export const approveReview = (reviewId) => {
  if (!isApiMode || reviewId?.startsWith("REV-MOCK-")) {
    const review = mockStore();
    review.approval_state = "approved";
    const committed = (review.station_changes || [])
      .filter((row) => (row.decision || "accept") !== "keep")
      .map((row) => row.station_id);
    return delay({
      message: "已核准並套用。",
      committed_stations: committed,
      effective_note: review.effective_note,
    });
  }
  return request("/optimization/daily-review/approve", { method: "POST", body: { review_id: reviewId } });
};

export const rejectReview = (reviewId) => {
  if (!isApiMode || reviewId?.startsWith("REV-MOCK-")) {
    mockReview = createMockReview();
    return delay({ message: "已退回，未存版本。", rejected: true });
  }
  return request("/optimization/daily-review/reject", { method: "POST", body: { review_id: reviewId } });
};

// ADR-304 §7 / ADR-124：核准後係數會不會真的影響調度，由後端的 coefficient_mode 決定。
// 前端不得自行假設「已套用＝調度行為已改變」。
export const EFFECT_LABELS = {
  off: {
    tag: "未生效",
    color: "default",
    text: "係數目前為「不生效」模式：核准只會存成可回溯的參數版本，不會改變任何一次派工。",
  },
  shadow: {
    tag: "影子模式",
    color: "gold",
    text: "係數目前為「影子」模式：系統會算出套用後的目標水位並記錄差異，但實際派工仍用基準值。",
  },
  on: {
    tag: "已生效",
    color: "green",
    text: "係數目前為「生效」模式：核准後會影響動態目標水位，進而改變建議的補／取車數量。",
  },
};

export const STATUS_LABELS = {
  ok: { text: "可套用", color: "green" },
  no_data: { text: "沒有資料", color: "default" },
  insufficient_samples: { text: "樣本不足", color: "gold" },
  failed: { text: "計算失敗", color: "red" },
};
