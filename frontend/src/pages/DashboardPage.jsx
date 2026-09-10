import { CloudOutlined, EnvironmentOutlined } from "@ant-design/icons";
import { Card, Select, Space, Tag, Typography } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import MetricCard from "../components/common/MetricCard.jsx";
import StationDrawer from "../components/dashboard/StationDrawer.jsx";
import StationMap from "../components/dashboard/StationMap.jsx";
import DispatchSidePanel from "../components/dashboard/dispatch/DispatchSidePanel.jsx";
import OrderBuilder from "../components/dashboard/dispatch/OrderBuilder.jsx";
import useDashboardData from "../hooks/useDashboardData.js";
import {
  buildEmergency,
  buildFromStation,
  buildFromVehicle,
  estimateQuantity,
  stationUrgency,
} from "../utils/tripPlanner.js";

const statusOptions = [
  { value: "all", label: "全部狀態" },
  { value: "empty", label: "空站" },
  { value: "low", label: "偏低" },
  { value: "normal", label: "正常" },
  { value: "high", label: "偏高" },
  { value: "full", label: "滿站" },
];

const ACTION_STATUS = new Set(["empty", "low", "high", "full"]);

// 送出後的狀態生命週期示意推進：assigned → accepted → in_progress（逐站完成）→ completed。
function advanceOrder(order) {
  if (order.status === "assigned") return { ...order, status: "accepted" };
  if (order.status === "accepted") return { ...order, status: "in_progress" };
  if (order.status === "in_progress") {
    const stops = order.stops.map((s) => ({ ...s }));
    const idx = stops.findIndex((s) => s.stop_status !== "completed");
    if (idx >= 0) stops[idx].stop_status = "completed";
    const allDone = stops.every((s) => s.stop_status === "completed");
    return { ...order, stops, status: allDone ? "completed" : "in_progress" };
  }
  return order;
}

export default function DashboardPage() {
  const dashboard = useDashboardData();
  const [statusFilter, setStatusFilter] = useState("all");
  const [districtFilter, setDistrictFilter] = useState("all");
  const [mapDimension, setMapDimension] = useState("status");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [mapFocus, setMapFocus] = useState(null);
  const [builder, setBuilder] = useState(null); // null=待命態；物件=組單態
  const [orders, setOrders] = useState([]); // 送出的調度單（本機追蹤）
  const orderSeq = useRef(0);

  const stations = dashboard.data?.stations || [];
  const vehicles = dashboard.data?.vehicles || [];
  const recommendations = dashboard.data?.recommendations || [];
  const alerts = dashboard.data?.alerts || [];

  const districts = useMemo(
    () => [...new Set(stations.map((s) => s.district))].sort(),
    [stations],
  );

  const filteredStations = useMemo(
    () =>
      stations.filter(
        (s) =>
          (statusFilter === "all" || s.status === statusFilter) &&
          (districtFilter === "all" || s.district === districtFilter),
      ),
    [districtFilter, stations, statusFilter],
  );

  // 需調度清單（緊急站排行，缺口榜併入）：以既有站況 + 調度建議合併，依緊急度排序。
  const urgencyItems = useMemo(() => {
    const recByStation = new Map(recommendations.map((r) => [r.station_id, r]));
    return stations
      .filter((s) => ACTION_STATUS.has(s.status))
      .map((s) => {
        const rec = recByStation.get(s.station_id);
        const action = rec?.action ?? (["empty", "low"].includes(s.status) ? "補車" : "取車");
        const quantity = rec?.quantity ?? estimateQuantity(s);
        const urgency = Number.isFinite(Number(rec?.priority_score))
          ? Number(rec.priority_score)
          : stationUrgency(s);
        return {
          station: s,
          action,
          quantity,
          urgency,
          predicted: rec?.predicted_at_arrival,
        };
      })
      .sort((a, b) => b.urgency - a.urgency);
  }, [recommendations, stations]);

  // 狀態示意推進計時器（只在有未完成單時運作）。
  useEffect(() => {
    const hasActive = orders.some((o) => o.status !== "completed");
    if (!hasActive) return undefined;
    const timer = setInterval(() => {
      setOrders((prev) => {
        const idx = prev.findIndex((o) => o.status !== "completed");
        if (idx < 0) return prev;
        return prev.map((o, i) => (i === idx ? advanceOrder(o) : o));
      });
    }, 3500);
    return () => clearInterval(timer);
  }, [orders]);

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

  // 三入口：以車、以站、緊急。
  const startFromVehicle = useCallback(
    (vehicle) => {
      if (vehicle.status === "maintenance") return;
      const draft = buildFromVehicle(vehicle, stations, { district: vehicle.current_district });
      if (draft) setBuilder(draft);
    },
    [stations],
  );

  const startFromStation = useCallback(
    (station) => {
      const draft = buildFromStation(station, stations, vehicles);
      if (draft) setBuilder(draft);
      focusStation(station);
    },
    [stations, vehicles],
  );

  const startEmergency = useCallback(
    (alert) => {
      const seed = stations.find((s) => s.station_id === alert.station_id);
      if (!seed) return;
      const draft = buildEmergency(seed, stations, vehicles);
      if (draft) setBuilder(draft);
      focusStation(seed);
    },
    [stations, vehicles],
  );

  const changeBuilderVehicle = (vehicleId) => {
    setBuilder((prev) => {
      if (!prev) return prev;
      const chosen =
        prev.candidates?.find((c) => c.vehicle.vehicle_id === vehicleId)?.vehicle;
      if (!chosen) return prev;
      const rebuilt =
        prev.mode === "emergency"
          ? buildEmergency(prev.seedStation, stations, vehicles, { vehicle: chosen })
          : buildFromStation(prev.seedStation, stations, vehicles, { vehicle: chosen });
      return rebuilt ?? prev;
    });
  };

  const changeBuilderDistrict = (district) => {
    setBuilder((prev) => {
      if (!prev || prev.mode !== "vehicle") return prev;
      return buildFromVehicle(prev.vehicle, stations, { district }) ?? prev;
    });
  };

  const confirmDraft = () => {
    setBuilder((prev) => {
      if (!prev || !prev.stops.length) return prev;
      orderSeq.current += 1;
      const order = {
        order_id: `SND-${String(orderSeq.current).padStart(3, "0")}`,
        mode: prev.mode,
        vehicle: prev.vehicle,
        stops: prev.stops.map((s) => ({ ...s, stop_status: "pending" })),
        estimate: prev.estimate,
        status: "assigned",
        created_at: new Date().toISOString(),
      };
      setOrders((list) => [order, ...list]);
      return null;
    });
  };

  const draftRoute = builder
    ? { start: builder.start, stops: builder.stops }
    : null;

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
            <MetricCard
              title="全系統站點"
              value={dashboard.data.kpi.total_stations}
              suffix="站"
              note={`地圖顯示 ${stations.length} 筆 Mock`}
            />
          </div>

          {/* 主區：左地圖（舞台）/ 右欄狀態機（待命態 / 組單態） */}
          <div className="dashboard-main">
            <div className="dashboard-map">
              <StationMap
                stations={filteredStations}
                dimension={mapDimension}
                onSelectStation={openStation}
                focus={mapFocus}
                vehicles={vehicles}
                onSelectVehicle={startFromVehicle}
                draftRoute={draftRoute}
              />
            </div>

            <div className="dashboard-side">
              <Card size="small" className="dispatch-side-card" styles={{ body: { padding: 0, height: "100%" } }}>
                {builder ? (
                  <OrderBuilder
                    draft={builder}
                    districts={districts}
                    onChangeVehicle={changeBuilderVehicle}
                    onChangeDistrict={changeBuilderDistrict}
                    onConfirm={confirmDraft}
                    onCancel={() => setBuilder(null)}
                  />
                ) : (
                  <DispatchSidePanel
                    alerts={alerts}
                    onAcknowledge={dashboard.acknowledgeAlert}
                    onEmergency={startEmergency}
                    urgencyItems={urgencyItems}
                    onPickStation={startFromStation}
                    onFocus={focusStation}
                    orders={orders}
                  />
                )}
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
