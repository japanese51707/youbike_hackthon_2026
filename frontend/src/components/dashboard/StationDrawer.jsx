import { Alert, Descriptions, Drawer, Empty, Spin, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { formatDateTime, stationStatusLabels } from "../../utils/formatters.js";

function historyOption(history) {
  return {
    grid: { left: 36, right: 18, top: 30, bottom: 30 },
    tooltip: { trigger: "axis" },
    legend: { data: ["可借車輛", "緊急度"] },
    xAxis: {
      type: "category",
      data: history.map((item) => formatDateTime(item.timestamp)),
    },
    yAxis: [
      { type: "value", name: "台" },
      { type: "value", name: "分", max: 100 },
    ],
    series: [
      {
        name: "可借車輛",
        type: "line",
        smooth: true,
        data: history.map((item) => item.available_bikes),
        itemStyle: { color: "#087f5b" },
      },
      {
        name: "緊急度",
        type: "line",
        yAxisIndex: 1,
        data: history.map((item) => item.urgency_score),
        itemStyle: { color: "#f08c00" },
      },
    ],
  };
}

export default function StationDrawer({ open, onClose, detail, loading, error }) {
  const current = detail?.current;

  return (
    <Drawer
      title={current?.station_name || "站點詳情"}
      width={520}
      open={open}
      onClose={onClose}
    >
      {loading ? <Spin /> : null}
      {error ? <Alert type="error" showIcon message={error.message} /> : null}
      {!loading && !error && current ? (
        <div className="drawer-stack">
          <Descriptions column={2} size="small" bordered>
            <Descriptions.Item label="行政區">{current.district}</Descriptions.Item>
            <Descriptions.Item label="狀態">
              <Tag>{stationStatusLabels[current.status] || current.status}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="可借">{current.available_bikes} 台</Descriptions.Item>
            <Descriptions.Item label="可還">{current.available_docks} 位</Descriptions.Item>
            <Descriptions.Item label="使用率">{current.usage_rate}%</Descriptions.Item>
            <Descriptions.Item label="資料時間">{formatDateTime(current.timestamp)}</Descriptions.Item>
          </Descriptions>

          {detail.prediction ? (
            <Alert
              type="warning"
              showIcon
              message={`到達時預測 ${detail.prediction.predicted_available} 台`}
              description={`不確定區間 ${detail.prediction.lower_bound}–${detail.prediction.upper_bound} 台；決策應由規則引擎依區間下界判斷。`}
            />
          ) : (
            <Alert type="info" showIcon message="此站目前沒有 Mock 預測明細" />
          )}

          <div>
            <Typography.Title level={5}>站點歷史</Typography.Title>
            {detail.history?.length ? (
              <ReactECharts option={historyOption(detail.history)} style={{ height: 260 }} />
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此站沒有歷史 Mock" />
            )}
          </div>
        </div>
      ) : null}
    </Drawer>
  );
}
