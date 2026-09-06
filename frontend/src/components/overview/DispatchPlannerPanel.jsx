import { Alert, Card, Empty, List, Select, Slider, Space, Tag, Typography } from "antd";
import { useCallback, useMemo, useState } from "react";
import SharedMap from "../map/SharedMap.jsx";
import {
  createPlanRouteLayers,
  createServiceRangeLayer,
  createVehicleLayer,
} from "../map/layers/planLayers.js";
import { fleetPlannerConfig } from "../../config/fleetMock.js";
import presentationConfig from "../../config/presentation.json";
import {
  availableVehicles,
  planRouteForVehicle,
} from "../../utils/dispatchPlanner.js";

const CONSIDERED_FACTORS = [
  "可用載具目前位置",
  "載具服務半徑（可調）",
  "站點缺口／溢出嚴重度",
  "站點間距離（球面估算）",
  "站點容量與目標水位",
];

export default function DispatchPlannerPanel({ stations, operators }) {
  const vehicles = useMemo(() => availableVehicles(operators), [operators]);
  const [vehicleId, setVehicleId] = useState(null);
  const [radiusKm, setRadiusKm] = useState(fleetPlannerConfig.serviceRadiusKm);

  const activeVehicle =
    vehicles.find((v) => v.operator_id === vehicleId) ?? vehicles[0] ?? null;

  const plan = useMemo(() => {
    if (!activeVehicle) return null;
    return planRouteForVehicle(activeVehicle, stations, {
      ...fleetPlannerConfig,
      serviceRadiusKm: radiusKm,
    });
  }, [activeVehicle, radiusKm, stations]);

  const layers = useMemo(() => {
    if (!plan) return [];
    return [
      createServiceRangeLayer({ start: plan.start, radiusKm: plan.radiusKm }),
      ...createPlanRouteLayers({ start: plan.start, route: plan.route }),
      createVehicleLayer({ start: plan.start }),
    ].filter(Boolean);
  }, [plan]);

  const getTooltip = useCallback(({ object }) => {
    if (!object?.station_name) return null;
    return {
      text: `${object.action} 約 ${object.quantity} 台\n${object.station_name}\n本段 ${object.leg_km} km`,
    };
  }, []);

  const initialViewState = useMemo(() => {
    if (activeVehicle?.current_location) {
      return {
        longitude: Number(activeVehicle.current_location.lng),
        latitude: Number(activeVehicle.current_location.lat),
        zoom: 12,
      };
    }
    return presentationConfig.maps.dashboard;
  }, [activeVehicle]);

  return (
    <Card
      className="planner-card"
      title="調度路線規劃"
      extra={
        <Space>
          <Tag color="gold">示意 Mock</Tag>
          <Tag color="default">非正式最佳化</Tag>
        </Space>
      }
    >
      {vehicles.length ? (
        <>
          <div className="planner-toolbar">
            <Space wrap>
              <Typography.Text strong>可用載具</Typography.Text>
              <Select
                value={activeVehicle?.operator_id}
                style={{ minWidth: 200 }}
                onChange={setVehicleId}
                options={vehicles.map((v) => ({
                  value: v.operator_id,
                  label: `${v.name}（${v.operator_id}）`,
                }))}
              />
            </Space>
            <Space wrap align="center">
              <Typography.Text strong>服務半徑</Typography.Text>
              <Slider
                min={1}
                max={15}
                value={radiusKm}
                onChange={setRadiusKm}
                style={{ width: 160 }}
                tooltip={{ formatter: (v) => `${v} km` }}
              />
              <Tag className="mono">{radiusKm} km</Tag>
            </Space>
          </div>

          <SharedMap
            ariaLabel="調度路線規劃示意地圖"
            className="planner-map"
            initialViewState={initialViewState}
            layers={layers}
            getTooltip={getTooltip}
          />

          <div className="planner-body">
            <div>
              <Typography.Title level={5}>
                示意路線｜{activeVehicle?.name}
                {plan?.route.length ? (
                  <Tag className="mono" style={{ marginLeft: 8 }}>
                    總距離 {plan.totalDistanceKm} km
                  </Tag>
                ) : null}
              </Typography.Title>
              {plan?.route.length ? (
                <List
                  size="small"
                  dataSource={plan.route}
                  renderItem={(stop, index) => (
                    <List.Item>
                      <Space wrap>
                        <Tag color={stop.action === "補車" ? "green" : "orange"}>
                          {index + 1}. {stop.action} 約 {stop.quantity} 台
                        </Tag>
                        <Typography.Text>{stop.station_name}</Typography.Text>
                        <Typography.Text type="secondary" className="mono">
                          本段 {stop.leg_km} km
                        </Typography.Text>
                      </Space>
                    </List.Item>
                  )}
                />
              ) : (
                <Empty
                  image={Empty.PRESENTED_IMAGE_SIMPLE}
                  description="服務半徑內沒有需要調度的站點，試著調大半徑"
                />
              )}
            </div>

            <div>
              <Typography.Title level={5}>考量因素</Typography.Title>
              <ul className="planner-factors">
                {CONSIDERED_FACTORS.map((factor) => (
                  <li key={factor}>{factor}</li>
                ))}
              </ul>
            </div>
          </div>

          <Alert
            type="info"
            showIcon
            message="示意路線，非正式最佳化"
            description="此路線由前端透明規則（缺口優先＋最近）示意產生，僅供展示；正式最佳化由後端規則引擎負責，且任何調度需經人工確認才執行，本畫面不會送出派遣指令。"
          />
        </>
      ) : (
        <Empty description="目前沒有可用載具（皆執行中或休息）" />
      )}
    </Card>
  );
}
