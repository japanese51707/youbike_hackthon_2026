import { CloudOutlined, EnvironmentOutlined } from "@ant-design/icons";
import { Alert, Card, Select, Space, Table, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import MetricCard from "../components/common/MetricCard.jsx";
import AlertPanel from "../components/dashboard/AlertPanel.jsx";
import RecommendationPanel from "../components/dashboard/RecommendationPanel.jsx";
import StationDrawer from "../components/dashboard/StationDrawer.jsx";
import StationMap from "../components/dashboard/StationMap.jsx";
import useDashboardData from "../hooks/useDashboardData.js";

const statusOptions = [
  { value: "all", label: "全部狀態" },
  { value: "empty", label: "空站" },
  { value: "low", label: "偏低" },
  { value: "normal", label: "正常" },
  { value: "high", label: "偏高" },
  { value: "full", label: "滿站" },
];

export default function DashboardPage() {
  const dashboard = useDashboardData();
  const [statusFilter, setStatusFilter] = useState("all");
  const [districtFilter, setDistrictFilter] = useState("all");
  const [mapDimension, setMapDimension] = useState("status");
  const [drawerOpen, setDrawerOpen] = useState(false);

  const stations = dashboard.data?.stations || [];
  const districts = useMemo(
    () => [...new Set(stations.map((station) => station.district))].sort(),
    [stations],
  );
  const filteredStations = useMemo(
    () =>
      stations.filter(
        (station) =>
          (statusFilter === "all" || station.status === statusFilter) &&
          (districtFilter === "all" || station.district === districtFilter),
      ),
    [districtFilter, stations, statusFilter],
  );

  const openStation = (stationId) => {
    dashboard.selectStation(stationId);
    setDrawerOpen(true);
  };

  return (
    <AsyncState
      loading={dashboard.loading}
      error={dashboard.error}
      data={dashboard.data}
      onRetry={dashboard.reload}
    >
      {dashboard.data ? (
        <div className="page-stack">
          <div className="page-heading">
            <div>
              <Typography.Title level={2}>調度決策儀表板</Typography.Title>
              <Typography.Paragraph>
                監看站點壓力、預覽規則引擎建議，再由人員確認執行。
              </Typography.Paragraph>
            </div>
            <Space wrap>
              <Tag icon={<EnvironmentOutlined />}>{dashboard.data.weather.district}</Tag>
              <Tag icon={<CloudOutlined />} color="blue">
                {dashboard.data.weather.description}｜{dashboard.data.weather.temperature}°C
              </Tag>
            </Space>
          </div>

          <div className="metric-grid metric-grid-five">
            <MetricCard title="空站率" value={dashboard.data.kpi.empty_rate} suffix="%" precision={2} tone="danger" />
            <MetricCard title="滿站率" value={dashboard.data.kpi.full_rate} suffix="%" precision={2} tone="warning" />
            <MetricCard title="平均使用率" value={dashboard.data.kpi.avg_usage_rate} suffix="%" precision={1} />
            <MetricCard title="待調度站點" value={dashboard.data.kpi.stations_need_dispatch} suffix="站" tone="danger" />
            <MetricCard title="全系統站點" value={dashboard.data.kpi.total_stations} suffix="站" note="目前地圖僅顯示 10 筆 Mock" />
          </div>

          <Card className="filter-card">
            <Space wrap>
              <Typography.Text strong>地圖篩選</Typography.Text>
              <Select value={statusFilter} options={statusOptions} onChange={setStatusFilter} />
              <Select
                value={districtFilter}
                onChange={setDistrictFilter}
                options={[
                  { value: "all", label: "全部行政區" },
                  ...districts.map((district) => ({ value: district, label: district })),
                ]}
              />
              <Select
                value={mapDimension}
                onChange={setMapDimension}
                options={[
                  { value: "status", label: "顏色：站點狀態" },
                  { value: "usage", label: "顏色：使用率" },
                ]}
              />
              <Tag>{filteredStations.length} 站</Tag>
            </Space>
          </Card>

          <StationMap
            stations={filteredStations}
            dimension={mapDimension}
            onSelectStation={openStation}
          />

          <div className="two-column-grid">
            <RecommendationPanel
              recommendations={dashboard.data.recommendations}
              onConfirm={dashboard.confirmRecommendation}
            />
            <AlertPanel
              alerts={dashboard.data.alerts}
              onAcknowledge={dashboard.acknowledgeAlert}
            />
          </div>

          <Card title="區域類型壓力摘要" extra={<Tag>{dashboard.data.heatmap.dimension}</Tag>}>
            <Table
              rowKey="group"
              size="small"
              pagination={false}
              dataSource={Object.entries(dashboard.data.heatmap.groups).map(([group, values]) => ({ group, ...values }))}
              columns={[
                { title: "類型", dataIndex: "group" },
                { title: "站數", dataIndex: "count" },
                { title: "平均使用率", dataIndex: "avg_usage", render: (value) => `${value}%` },
                { title: "空站數", dataIndex: "empty_count" },
              ]}
            />
          </Card>

          <Alert
            type="info"
            showIcon
            message="安全邊界"
            description="本頁只提供決策預覽；正式確認與權限驗證必須由後端執行，前端按鈕不是授權機制。"
          />

          <StationDrawer
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            detail={dashboard.detail}
            loading={dashboard.detailLoading}
            error={dashboard.detailError}
          />
        </div>
      ) : null}
    </AsyncState>
  );
}
