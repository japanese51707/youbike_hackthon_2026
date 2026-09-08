import { Tag, Typography } from "antd";
import { mapConfig } from "../../config/mapConfig.js";

const statusLabels = {
  loading: { color: "processing", text: "底圖載入中" },
  ready: { color: "success", text: "OpenFreeMap" },
  "no-basemap": { color: "warning", text: "底圖不可用｜資料層仍可操作" },
  "map-unavailable": { color: "error", text: "此裝置無法啟動 WebGL 地圖" },
};

// 有底圖顯示時才需要來源標示（OSM/ODbL）；no-basemap/map-unavailable 沒有 OSM 圖磚就不顯示。
const BASEMAP_ACTIVE = new Set(["loading", "ready"]);

export default function BasemapStatus({ status, reason }) {
  const state = statusLabels[status] ?? statusLabels.loading;
  const showStatusTag = status !== "ready"; // 正常時不再放大顆標籤，只留小字來源
  const showAttribution = BASEMAP_ACTIVE.has(status);
  // 精簡來源文字：去連結、以小灰字呈現，仍保留授權要求的來源標示
  const attributionText = mapConfig.attribution
    .map((item) => item.label)
    .join(" · ");

  return (
    <div
      className={`basemap-status basemap-status-${status}`}
      role={
        status === "no-basemap" || status === "map-unavailable"
          ? "alert"
          : "status"
      }
      aria-live="polite"
    >
      {showStatusTag ? <Tag color={state.color}>{state.text}</Tag> : null}
      {reason ? <Typography.Text type="secondary">{reason}</Typography.Text> : null}
      {showAttribution ? (
        <span className="map-attribution">{attributionText}</span>
      ) : null}
    </div>
  );
}
