import BackendDriverPage from "./BackendDriverPage.jsx";
import { isApiMode } from "../api/httpClient.js";
import {
  CompassOutlined,
  EnvironmentOutlined,
  ExclamationCircleOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Empty,
  Segmented,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useCallback, useMemo, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import SharedMap from "../components/map/SharedMap.jsx";
import {
  createPlanRouteLayers,
  createVehicleLayer,
} from "../components/map/layers/planLayers.js";
import useDriverData from "../hooks/useDriverData.js";
import { sequenceDriverRoute } from "../utils/dispatchPlanner.js";
import { haversineKm } from "../utils/geo.js";

const priorityColors = { high: "red", medium: "orange", low: "blue" };

function toStop(rec) {
  return {
    recommendation_id: rec.recommendation_id,
    station_id: rec.station_id,
    station_name: rec.station_name,
    lat: Number(rec.lat),
    lng: Number(rec.lng),
    action: rec.action,
    quantity: rec.quantity,
    reason: rec.reason,
    priority_level: rec.priority_level,
  };
}

function navUrl(from, to) {
  if (!from || !to) return null;
  return `https://www.google.com/maps/dir/?api=1&origin=${from.lat},${from.lng}&destination=${to.lat},${to.lng}&travelmode=driving`;
}

// 整條路線導航：起點→各停靠點(途經點)→終點，僅帶公開座標。
function fullNavUrl(from, route) {
  if (!from || !Array.isArray(route) || !route.length) return null;
  const dest = route[route.length - 1];
  const mids = route.slice(0, -1);
  const base = `https://www.google.com/maps/dir/?api=1&origin=${from.lat},${from.lng}&destination=${dest.lat},${dest.lng}&travelmode=driving`;
  const waypoints = mids.length
    ? `&waypoints=${mids.map((s) => `${s.lat},${s.lng}`).join("|")}`
    : "";
  return base + waypoints;
}

function MockDriverPage() {
  const driver = useDriverData();
  const [messageApi, contextHolder] = message.useMessage();
  const [mode, setMode] = useState("pool");
  const [acceptedIds, setAcceptedIds] = useState([]);
  const [completedIds, setCompletedIds] = useState([]);

  const operator = driver.data?.operator ?? null;
  const start = operator?.current_location
    ? {
        lat: Number(operator.current_location.lat),
        lng: Number(operator.current_location.lng),
      }
    : null;

  const recommendations = driver.data?.recommendations ?? [];
  const pool = recommendations.filter(
    (rec) => !acceptedIds.includes(rec.recommendation_id),
  );

  const acceptedStops = useMemo(
    () =>
      recommendations
        .filter((rec) => acceptedIds.includes(rec.recommendation_id))
        .map(toStop),
    [acceptedIds, recommendations],
  );

  const plan = useMemo(
    () => sequenceDriverRoute(start, acceptedStops),
    [acceptedStops, start],
  );

  const currentStop =
    plan.route.find((stop) => !completedIds.includes(stop.station_id)) ?? null;

  const routeLayers = useMemo(() => {
    if (!start || !plan.route.length) return [];
    return [
      ...createPlanRouteLayers({ start, route: plan.route }),
      createVehicleLayer({ start }),
    ].filter(Boolean);
  }, [plan.route, start]);

  const routeTooltip = useCallback(({ object }) => {
    if (!object?.station_name) return null;
    return { text: `${object.action} ${object.quantity} 台\n${object.station_name}` };
  }, []);

  const accept = (rec) => {
    setAcceptedIds((ids) => [...ids, rec.recommendation_id]);
    messageApi.success("已接單，已加入路線（示意）");
    setMode("route");
  };

  const finishStop = (stop, note) => {
    setCompletedIds((ids) => [...ids, stop.station_id]);
    messageApi.success(`${stop.station_name}：${note}（示意，未送出指令）`);
  };

  return (
    <div className="driver-frame">
      {contextHolder}
      <AsyncState
        loading={driver.loading && !driver.data}
        error={driver.error}
        data={driver.data}
        onRetry={driver.reload}
      >
        {driver.data ? (
          <>
            <div className="driver-header">
              <div>
                <Typography.Text className="driver-title">司機任務</Typography.Text>
                <div className="driver-sub mono">
                  {operator?.name ?? "—"}｜已接 {acceptedStops.length}｜完成{" "}
                  {completedIds.length}
                </div>
              </div>
              <Tag color="gold">示意 Mock</Tag>
            </div>

            <Segmented
              block
              value={mode}
              onChange={setMode}
              options={[
                { value: "pool", label: `任務池 ${pool.length}` },
                { value: "route", label: `我的路線 ${plan.route.length}` },
                { value: "now", label: "當前停靠" },
              ]}
            />

            <div className="driver-body">
              {mode === "pool" ? (
                pool.length ? (
                  pool.map((rec) => {
                    const dist = start
                      ? haversineKm(start, { lat: rec.lat, lng: rec.lng }).toFixed(1)
                      : null;
                    return (
                      <div className="driver-card" key={rec.recommendation_id}>
                        <div className="driver-card-top">
                          <Tag color={rec.action === "補車" ? "green" : "orange"}>
                            {rec.action} {rec.quantity} 台
                          </Tag>
                          <Tag color={priorityColors[rec.priority_level]}>
                            {rec.priority_level}
                          </Tag>
                          {dist ? (
                            <span className="mono driver-dist">{dist} km</span>
                          ) : null}
                        </div>
                        <div className="driver-card-name">{rec.station_name}</div>
                        <div className="driver-card-reason">{rec.reason}</div>
                        <Button
                          type="primary"
                          block
                          size="large"
                          onClick={() => accept(rec)}
                        >
                          接單
                        </Button>
                      </div>
                    );
                  })
                ) : (
                  <Empty description="任務池已清空" />
                )
              ) : null}

              {mode === "route" ? (
                plan.route.length ? (
                  <>
                    <div className="driver-map">
                      <SharedMap
                        ariaLabel="司機總路線規劃地圖"
                        className="map-fill"
                        initialViewState={{
                          longitude: start.lng,
                          latitude: start.lat,
                          zoom: 12,
                        }}
                        layers={routeLayers}
                        getTooltip={routeTooltip}
                      />
                    </div>
                    <Button
                      block
                      size="large"
                      icon={<CompassOutlined />}
                      href={fullNavUrl(start, plan.route)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      整條路線 Google Maps 導航
                    </Button>
                    <div className="driver-route-total mono">
                      共 {plan.route.length} 站｜總距離 {plan.totalDistanceKm} km（示意）
                    </div>
                    {plan.route.map((stop, index) => {
                      const done = completedIds.includes(stop.station_id);
                      return (
                        <div
                          className={`driver-route-row${done ? " done" : ""}`}
                          key={stop.station_id}
                        >
                          <span className="driver-seq">{index + 1}</span>
                          <div className="driver-route-main">
                            <div className="driver-card-name">{stop.station_name}</div>
                            <div className="mono driver-sub">
                              {stop.action} {stop.quantity} 台｜本段 {stop.leg_km} km
                            </div>
                          </div>
                          {done ? <Tag color="green">完成</Tag> : null}
                        </div>
                      );
                    })}
                  </>
                ) : (
                  <Empty description="尚未接單" />
                )
              ) : null}

              {mode === "now" ? (
                currentStop ? (
                  <div className="driver-now">
                    <Tag
                      color={currentStop.action === "補車" ? "green" : "orange"}
                      className="driver-now-action"
                    >
                      {currentStop.action} {currentStop.quantity} 台
                    </Tag>
                    <div className="driver-now-name">
                      <EnvironmentOutlined /> {currentStop.station_name}
                    </div>
                    <div className="driver-card-reason">{currentStop.reason}</div>

                    <Button
                      type="primary"
                      block
                      size="large"
                      icon={<CompassOutlined />}
                      href={navUrl(start, currentStop)}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Google Maps 導航
                    </Button>

                    <Space className="driver-now-actions" size={8}>
                      <Button
                        block
                        size="large"
                        type="primary"
                        onClick={() => finishStop(currentStop, "完成")}
                      >
                        完成
                      </Button>
                      <Button
                        block
                        size="large"
                        icon={<ToolOutlined />}
                        onClick={() => finishStop(currentStop, "回報故障")}
                      >
                        故障
                      </Button>
                      <Button
                        block
                        size="large"
                        icon={<ExclamationCircleOutlined />}
                        onClick={() => finishStop(currentStop, "回報異常")}
                      >
                        異常
                      </Button>
                    </Space>
                  </div>
                ) : (
                  <Empty
                    description={
                      acceptedStops.length ? "所有停靠點已完成" : "尚未接單"
                    }
                  />
                )
              ) : null}
            </div>

            <Alert
              className="driver-foot"
              type="info"
              showIcon
              message="示意排程，不送出派遣指令；接單/完成僅存在本機工作階段。"
            />
          </>
        ) : null}
      </AsyncState>
    </div>
  );
}

export default function DriverPage() {
  return isApiMode ? <BackendDriverPage /> : <MockDriverPage />;
}
