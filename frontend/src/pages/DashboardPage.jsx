import {
  ClockCircleOutlined,
  CloudOutlined,
  EnvironmentOutlined,
} from "@ant-design/icons";
import { Card, Checkbox, Select, Space, Tag, Tooltip, Typography, message } from "antd";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import StationDrawer from "../components/dashboard/StationDrawer.jsx";
import StationMap from "../components/dashboard/StationMap.jsx";
import DispatchSidePanel from "../components/dashboard/dispatch/DispatchSidePanel.jsx";
import OrderBuilder from "../components/dashboard/dispatch/OrderBuilder.jsx";
import useDashboardData from "../hooks/useDashboardData.js";
import {
  buildEmergency as mockBuildEmergency,
  buildFromStation as mockBuildFromStation,
  buildFromVehicle as mockBuildFromVehicle,
  estimateQuantity,
  stationUrgency,
} from "../utils/tripPlanner.js";
import {
  buildEmergency as apiBuildEmergency,
  buildFromStation as apiBuildFromStation,
  buildFromVehicle as apiBuildFromVehicle,
  confirmRecommendation,
  reportVehicleOnboard,
} from "../api/dispatchApi.js";
import { isApiMode } from "../api/httpClient.js";
import { parseStationTime } from "../utils/formatters.js";

// 狀態勾選項（多選）：不含「全部」，未勾＝全部顯示。
const statusOptions = [
  { value: "empty", label: "空站" },
  { value: "low", label: "偏低" },
  { value: "normal", label: "正常" },
  { value: "high", label: "偏高" },
  { value: "full", label: "滿站" },
];

const ACTION_STATUS = new Set(["empty", "low", "high", "full"]);

function formatClock(date) {
  if (!date) return "—";
  return date.toLocaleString("zh-TW", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

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
  // 狀態篩選改多選（勾選）：空陣列＝全部顯示。
  const [statusFilter, setStatusFilter] = useState([]);
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
  // 追蹤清單：API 模式用後端真實任務（/dispatch/tasks 對映），mock 模式用本機示意單。
  const trackOrders = isApiMode ? dashboard.data?.orders || [] : orders;

  const districts = useMemo(
    () => [...new Set(stations.map((s) => s.district))].sort(),
    [stations],
  );

  // 站點資料時間：取這批站點中最新的 source_timestamp（資料源更新時間）
  // 與 timestamp（系統取得時間），讓調派員知道「看到的是幾點的站況」。
  const dataTime = useMemo(() => {
    let src = null;
    let fetched = null;
    for (const s of stations) {
      const sp = parseStationTime(s.source_timestamp);
      const ft = parseStationTime(s.timestamp);
      if (sp && (!src || sp > src)) src = sp;
      if (ft && (!fetched || ft > fetched)) fetched = ft;
    }
    return { src, fetched };
  }, [stations]);

  const filteredStations = useMemo(
    () =>
      stations.filter(
        (s) =>
          (statusFilter.length === 0 || statusFilter.includes(s.status)) &&
          (districtFilter === "all" || s.district === districtFilter),
      ),
    [districtFilter, stations, statusFilter],
  );

  // 需調度清單（緊急站排行）：
  // - 有後端建議時，直接用後端已排序、已算緊急度的 recommendations（priority_score / reason /
  //   target_available 皆為後端規則引擎產出），並附上該站完整站況供地圖定位與狀態顯示。
  // - 無後端建議（mock 模式或後端該塊降級）時，退回以站況估的示意排序。
  const urgencyItems = useMemo(() => {
    const stationById = new Map(stations.map((s) => [s.station_id, s]));

    if (recommendations.length) {
      return recommendations
        .map((rec) => {
          // 後端建議自帶 lat/lng/station_name/district；若站點清單有更完整站況則合併。
          const station = stationById.get(rec.station_id) ?? {
            station_id: rec.station_id,
            station_name: rec.station_name,
            district: rec.district,
            lat: rec.lat,
            lng: rec.lng,
            status: rec.status ?? (["補車"].includes(rec.action) ? "low" : "high"),
          };
          return {
            station,
            action: rec.action,
            // target_available（補到/抽到幾台）是主指令；quantity 為輔助增減量。
            quantity: rec.quantity,
            targetAvailable: rec.target_available,
            urgency: Number(rec.priority_score) || 0,
            priorityLevel: rec.priority_level,
            urgencyTier: rec.urgency_tier,
            reason: rec.reason,
            predicted: rec.predicted_at_arrival,
            // 誠實標示：即時源無歷史 lag 特徵時緊急度為降級版，不假裝是完整預測。
            predictionStatus: rec.prediction_status,
          };
        })
        .sort((a, b) => b.urgency - a.urgency);
    }

    // 降級：無後端建議時，用站況估示意排序。
    return stations
      .filter((s) => ACTION_STATUS.has(s.status))
      .map((s) => ({
        station: s,
        action: ["empty", "low"].includes(s.status) ? "補車" : "取車",
        quantity: estimateQuantity(s),
        urgency: stationUrgency(s),
        predicted: undefined,
      }))
      .sort((a, b) => b.urgency - a.urgency);
  }, [recommendations, stations]);

  // 狀態示意推進計時器：只在 mock 模式運作（API 模式的任務進度來自後端真實 tasks）。
  useEffect(() => {
    if (isApiMode) return undefined;
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

  // 點警報卡：定位地圖到該站並開單站詳情。警報自帶座標，找不到站況也能定位。
  const focusAlert = (alert) => {
    const station =
      stations.find((s) => s.station_id === alert.station_id) || {
        station_id: alert.station_id,
        lat: alert.lat,
        lng: alert.lng,
      };
    if (Number.isFinite(Number(station.lat)) && Number.isFinite(Number(station.lng))) {
      focusStation(station);
    }
    openStation(alert.station_id);
  };

  // 把後端 build 錯誤轉成使用者可讀提示（後端錯誤格式為 {error/message}）。
  const showBuildError = (err) =>
    message.error(err?.message || "後端組單失敗，請稍後再試");

  // 三入口：以車、以站、緊急。
  // API 模式：草稿由後端 dispatch_builder 計算（含 blocking_reasons / load_plan）。
  // mock 模式：維持前端 tripPlanner 示意草稿。
  const startFromVehicle = useCallback(
    async (vehicle) => {
      if (vehicle.status === "maintenance") return;
      if (isApiMode) {
        try {
          const draft = await apiBuildFromVehicle(vehicle.vehicle_id, {
            district: vehicle.current_district,
          });
          setBuilder({ ...draft, mode_key: "vehicle" });
        } catch (err) {
          showBuildError(err);
        }
        return;
      }
      const draft = mockBuildFromVehicle(vehicle, stations, { district: vehicle.current_district });
      if (draft) setBuilder(draft);
    },
    [stations],
  );

  const startFromStation = useCallback(
    async (station) => {
      focusStation(station);
      if (isApiMode) {
        try {
          const draft = await apiBuildFromStation(station.station_id);
          setBuilder({ ...draft, mode_key: "station" });
        } catch (err) {
          showBuildError(err);
        }
        return;
      }
      const draft = mockBuildFromStation(station, stations, vehicles);
      if (draft) setBuilder(draft);
    },
    [stations, vehicles],
  );

  const startEmergency = useCallback(
    async (alert) => {
      const seed = stations.find((s) => s.station_id === alert.station_id);
      if (seed) focusStation(seed);
      if (isApiMode) {
        try {
          const draft = await apiBuildEmergency([alert.station_id]);
          setBuilder({ ...draft, mode_key: "emergency" });
        } catch (err) {
          showBuildError(err);
        }
        return;
      }
      if (!seed) return;
      const draft = mockBuildEmergency(seed, stations, vehicles);
      if (draft) setBuilder(draft);
    },
    [stations, vehicles],
  );

  // 換車：API 模式帶 vehicle_id 重打後端 build；mock 模式用候選車重算示意。
  const changeBuilderVehicle = async (vehicleId) => {
    if (isApiMode) {
      setBuilder((prev) => {
        if (!prev?.draft_id) return prev;
        const modeKey = prev.mode_key;
        const seedId = prev.stations?.[0]?.station_id;
        const rebuild =
          modeKey === "vehicle"
            ? apiBuildFromVehicle(vehicleId, {})
            : modeKey === "emergency"
              ? apiBuildEmergency(prev.stations.map((s) => s.station_id), { vehicleId })
              : apiBuildFromStation(seedId, { vehicleId });
        rebuild
          .then((draft) => setBuilder({ ...draft, mode_key: modeKey }))
          .catch(showBuildError);
        return prev; // 先保留舊草稿，重算完成後由 then 覆蓋
      });
      return;
    }
    setBuilder((prev) => {
      if (!prev) return prev;
      const chosen =
        prev.candidates?.find((c) => c.vehicle.vehicle_id === vehicleId)?.vehicle;
      if (!chosen) return prev;
      const rebuilt =
        prev.mode === "emergency"
          ? mockBuildEmergency(prev.seedStation, stations, vehicles, { vehicle: chosen })
          : mockBuildFromStation(prev.seedStation, stations, vehicles, { vehicle: chosen });
      return rebuilt ?? prev;
    });
  };

  const changeBuilderDistrict = (district) => {
    if (isApiMode) {
      setBuilder((prev) => {
        if (!prev?.draft_id || prev.mode_key !== "vehicle") return prev;
        apiBuildFromVehicle(prev.assigned_vehicle, { district })
          .then((draft) => setBuilder({ ...draft, mode_key: "vehicle" }))
          .catch(showBuildError);
        return prev;
      });
      return;
    }
    setBuilder((prev) => {
      if (!prev || prev.mode !== "vehicle") return prev;
      return mockBuildFromVehicle(prev.vehicle, stations, { district }) ?? prev;
    });
  };

  // 換司機（僅 API 後端草稿）：帶 operator_id 重打同入口 build，後端重算可行性。
  const changeBuilderOperator = (operatorId) => {
    if (!isApiMode) return;
    setBuilder((prev) => {
      if (!prev?.draft_id) return prev;
      const modeKey = prev.mode_key;
      const seedId = prev.stations?.[0]?.station_id;
      const vehicleId = prev.assigned_vehicle;
      const rebuild =
        modeKey === "vehicle"
          ? apiBuildFromVehicle(vehicleId, { operatorId })
          : modeKey === "emergency"
            ? apiBuildEmergency(prev.stations.map((s) => s.station_id), { vehicleId, operatorId })
            : apiBuildFromStation(seedId, { vehicleId, operatorId });
      rebuild
        .then((draft) => setBuilder({ ...draft, mode_key: modeKey }))
        .catch(showBuildError);
      return prev;
    });
  };

  // 回報車上台數後，用同入口重打 build 讓後端重算可行性（解除 onboard 阻擋）。
  const reportOnboardAndRebuild = async (vehicleId, onboardBikes) => {
    try {
      await reportVehicleOnboard(vehicleId, onboardBikes);
      message.success(`已回報 ${vehicleId} 車上 ${onboardBikes} 台`);
      const prev = builder;
      if (!prev?.draft_id) return;
      const modeKey = prev.mode_key;
      const seedId = prev.stations?.[0]?.station_id;
      const draft =
        modeKey === "vehicle"
          ? await apiBuildFromVehicle(vehicleId, {})
          : modeKey === "emergency"
            ? await apiBuildEmergency(prev.stations.map((s) => s.station_id), { vehicleId })
            : await apiBuildFromStation(seedId, { vehicleId });
      setBuilder({ ...draft, mode_key: modeKey });
    } catch (err) {
      message.error(err?.message || "回報失敗");
    }
  };

  // 確認派發：
  // - API 模式：送後端 confirm-trip（寫入真實派工，需 dispatcher 身分），成功後重載面板。
  // - mock 模式：維持本機示意單 + 計時器推進。
  const confirmDraft = async () => {
    const prev = builder;
    if (!prev) return;

    if (isApiMode && prev.draft_id) {
      try {
        const task = await confirmRecommendation(prev);
        message.success(`已確認派工${task?.task_id ? `：${task.task_id}` : ""}`);
        setBuilder(null);
        dashboard.reload({ silent: true }).catch(() => {});
      } catch (err) {
        message.error(err?.message || "確認派工失敗");
      }
      return;
    }

    if (!prev.stops?.length) return;
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
    setBuilder(null);
  };

  // 地圖草稿路線：mock 草稿有 start/stops；後端草稿的路線改由清單呈現（座標未來接即時定位）。
  const draftRoute =
    builder && !builder.draft_id
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
              <Tag color={dashboard.data.stationsSource === "backend" ? "green" : "gold"}>
                站點來源：{dashboard.data.stationsSource === "backend" ? "後端 API" : dashboard.data.stationsSource}
              </Tag>
              {dataTime.src || dataTime.fetched ? (
                <Tooltip
                  title={
                    <span className="mono">
                      資料源更新：{formatClock(dataTime.src)}
                      <br />
                      系統取得：{formatClock(dataTime.fetched)}
                    </span>
                  }
                >
                  <Tag icon={<ClockCircleOutlined />} color="default">
                    資料時間 {formatClock(dataTime.src ?? dataTime.fetched)}
                  </Tag>
                </Tooltip>
              ) : null}
              <Tag icon={<EnvironmentOutlined />}>{dashboard.data.weather.district}</Tag>
              <Tag icon={<CloudOutlined />} color="blue">
                {dashboard.data.weather.description}｜{dashboard.data.weather.temperature}°C
              </Tag>
              <Checkbox.Group
                className="status-filter-checks"
                options={statusOptions}
                value={statusFilter}
                onChange={setStatusFilter}
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

          {/* KPI 列：待調度突出（大），其餘四項縮成一小排指標 */}
          <div className="kpi-row">
            <div className="kpi-primary">
              <span className="kpi-primary-label">待調度站點</span>
              <span className="kpi-primary-value mono">
                {dashboard.data.kpi.stations_need_dispatch}
              </span>
              <span className="kpi-primary-unit">站需立即處理</span>
            </div>
            <div className="kpi-mini-group">
              <span className="kpi-mini">
                空站率 <b className="mono">{dashboard.data.kpi.empty_rate}%</b>
              </span>
              <span className="kpi-mini">
                滿站率 <b className="mono">{dashboard.data.kpi.full_rate}%</b>
              </span>
              <span className="kpi-mini">
                平均使用率 <b className="mono">{dashboard.data.kpi.avg_usage_rate}%</b>
              </span>
              <span className="kpi-mini">
                全系統 <b className="mono">{dashboard.data.kpi.total_stations}</b> 站
                <span className="kpi-mini-note">（地圖 {stations.length} 筆）</span>
              </span>
            </div>
          </div>

          {/* 主區：左地圖（舞台）/ 右欄狀態機（待命態 / 組單態） */}
          <div className="dashboard-main">
            <div className="dashboard-map">
              <StationMap
                stations={filteredStations}
                dimension={mapDimension}
                onSelectStation={openStation}
                focus={mapFocus}
                highlightStationId={dashboard.selectedStationId}
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
                    onChangeOperator={changeBuilderOperator}
                    onChangeDistrict={changeBuilderDistrict}
                    onConfirm={confirmDraft}
                    onReportOnboard={reportOnboardAndRebuild}
                    onCancel={() => setBuilder(null)}
                  />
                ) : (
                  <DispatchSidePanel
                    alerts={alerts}
                    onAcknowledge={dashboard.acknowledgeAlert}
                    onEmergency={startEmergency}
                    onFocusAlert={focusAlert}
                    urgencyItems={urgencyItems}
                    onPickStation={startFromStation}
                    onFocus={focusStation}
                    orders={trackOrders}
                    apiMode={isApiMode}
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
          />
        </div>
      ) : null}
    </AsyncState>
  );
}
