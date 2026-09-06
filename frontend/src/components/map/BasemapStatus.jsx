import { Tag, Typography } from "antd";
import { mapConfig } from "../../config/mapConfig.js";

const statusLabels = {
  loading: { color: "processing", text: "底圖載入中" },
  ready: { color: "success", text: "OpenFreeMap" },
  "no-basemap": { color: "warning", text: "底圖不可用｜資料層仍可操作" },
  "map-unavailable": { color: "error", text: "此裝置無法啟動 WebGL 地圖" },
};

export default function BasemapStatus({ status, reason }) {
  const state = statusLabels[status] ?? statusLabels.loading;

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
      <Tag color={state.color}>{state.text}</Tag>
      {reason ? <Typography.Text type="secondary">{reason}</Typography.Text> : null}
      <span className="map-attribution">
        {mapConfig.attribution.map((item, index) => (
          <span key={item.url}>
            {index ? "｜" : ""}
            <Typography.Link
              href={item.url}
              target="_blank"
              rel="noreferrer"
            >
              {item.label}
            </Typography.Link>
          </span>
        ))}
      </span>
    </div>
  );
}
