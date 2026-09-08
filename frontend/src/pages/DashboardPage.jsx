import { CloudOutlined, EnvironmentOutlined } from "@ant-design/icons";
import { Card, Select, Space, Tabs, Tag, Typography } from "antd";
import { useMemo, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import MetricCard from "../components/common/MetricCard.jsx";
import AlertPanel from "../components/dashboard/AlertPanel.jsx";
import DeficitRankingPanel from "../components/dashboard/DeficitRankingPanel.jsx";
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
  const [mapFocus, setMapFocus] = useState(null);

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

  const focusStation = (station) => {
    if (!station) return;
    setMapFocus({
      longitude: Number(station.lng),
      latitude: Number(station.lat),
      zoom: 15,
      key: `${station.station_id}-${Date.now()}`,
    });
  };

  const unacked = dashboard.data?.alerts.filter((a) => !a.acknowledged).length ?? 0;

  return (
    <AsyncState
      loading={dashboard.loading}
      error={dashboard.error}
      data={dashboard.data}
      onRetry={dashboard.reload}
    >
      {dashboard.data ? (
        <div className="fixed-page">
          {/* 精簡工具列：標題 + 天氣 + 地圖篩選 */}
          <div className="dashboard-toolbar">
            <Typography.Title level={2}>調度決策儀表板</Typography.Title>
            <Space wrap size={8}>
              <Tag icon={<EnvironmentOutlined />}>{dashboard.data.weather.district}</Tag>
              <Tag icon={<CloudOutlined />} color="blue">
                {dashboard.data.weather.description}｜{dashboard.data.weather.temperature}°C
              </Tag>
              <Select
                size="small"
                value={statusFilter}
                options={statusOptions}
                onChange={setStatusFilter}
                style={{ minWidth: 110 }}
              />
              <Select
                size="small"
                value={districtFilter}
                onChange={setDistrictFilter}
                style={{ minWidth: 130 }}
                options={[
                  { value: "all", label: "全部行政區" },
                  ...districts.map((d) => ({ value: d, label: d })),
                ]}
              />
              <Select
                size="small"
                value={mapDimension}
                onChange={setMapDimension}
                style={{ minWidth: 150 }}
                options={[
                  { value: "status", label: "顏色：站點狀態" },
                  { value: "usage", label: "顏色：使用率" },
                ]}
              />
              <Tag>{filteredStations.length} 站</Tag>
            </Space>
          </div>

          {/* KPI 條 */}
          <div className="metric-grid metric-grid-five dashboard-kpis">
            <MetricCard title="空站率" value={dashboard.data.kpi.empty_rate} suffix="%" precision={2} tone="danger" />
            <MetricCard title="滿站率" value={dashboard.data.kpi.full_rate} suffix="%" precision={2} tone="warning" />
            <MetricCard title="平均使用率" value={dashboard.data.kpi.avg_usage_rate} suffix="%" precision={1} />
            <MetricCard title="待調度站點" value={dashboard.data.kpi.stations_need_dispatch} suffix="站" tone="danger" />
            <MetricCard title="全系統站點" value={dashboard.data.kpi.total_stations} suffix="站" note="地圖顯示 10 筆 Mock" />
          </div>

          {/* 主區：左地圖 / 右操作分頁（填滿、不捲動） */}
          <div className="dashboard-main">
            <div className="dashboard-map">
              <StationMap
                stations={filteredStations}
                dimension={mapDimension}
                onSelectStation={openStation}
                focus={mapFocus}
              />
            </div>

            <div className="dashboard-side">
              <Card size="small">
                <Tabs
                  defaultActiveKey="reco"
                  items={[
                    {
                      key: "reco",
                      label: `調度建議 ${dashboard.data.recommendations.length}`,
                      children: (
                        <RecommendationPanel
                          recommendations={dashboard.data.recommendations}
                          onConfirm={dashboard.confirmRecommendation}
                          onFocus={focusStation}
                          embedded
                        />
                      ),
                    },
                    {
                      key: "alert",
                      label: `即時警示 ${unacked}`,
                      children: (
                        <AlertPanel
                          alerts={dashboard.data.alerts}
                          onAcknowledge={dashboard.acknowledgeAlert}
                          embedded
                        />
                      ),
                    },
                    {
                      key: "rank",
                      label: "缺口榜",
                      children: (
                        <DeficitRankingPanel
                          stations={stations}
                          onFocus={focusStation}
                          embedded
                        />
                      ),
                    },
                  ]}
                />
              </Card>
            </div>
          </div>

          <StationDrawer
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            detail={dashboard.detail}
            loading={dashboard.detailLoading}
            error={dashboard.detailError}
            weather={dashboard.data.weather}
          />
        </div>
      ) : null}
    </AsyncState>
  );
}
