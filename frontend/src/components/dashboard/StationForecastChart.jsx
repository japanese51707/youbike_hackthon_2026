import { Alert, Tag, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { useMemo } from "react";
import { loadTemporalPresentation } from "../../api/temporalMockAdapter.js";

// 站點未來預測（ADR-013）：以 frontend-local Mock 的 Live → +30 → +60 畫可借車輛預測曲線，
// 含固定展示的信賴區間。缺站或缺展示值時顯示不可用，不插值、不捏造，也不進派遣 payload。

const AXIS_COLOR = "#8ea0b5";
const GRID_COLOR = "rgba(148,163,184,0.15)";

function buildOption(station) {
  const f30 = station.forecasts.find((f) => f.offsetMinutes === 30);
  const f60 = station.forecasts.find((f) => f.offsetMinutes === 60);

  const point = (forecast, key) =>
    forecast?.isAvailable ? forecast[key] : null;

  const lineData = [
    station.live.availableBikes,
    point(f30, "availableBikes"),
    point(f60, "availableBikes"),
  ];
  const lowerBase = [null, point(f30, "lowerBound"), point(f60, "lowerBound")];
  const bandHeight = [
    null,
    f30?.isAvailable ? f30.upperBound - f30.lowerBound : null,
    f60?.isAvailable ? f60.upperBound - f60.lowerBound : null,
  ];

  return {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1" },
    tooltip: {
      trigger: "axis",
      backgroundColor: "#0e1626",
      borderColor: "#243149",
      textStyle: { color: "#e5ecf5" },
    },
    grid: { left: 40, right: 18, top: 20, bottom: 28, containLabel: true },
    xAxis: {
      type: "category",
      data: ["現在", "+30 分", "+60 分"],
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisLabel: { color: AXIS_COLOR },
    },
    yAxis: {
      type: "value",
      name: "可借車輛",
      nameTextStyle: { color: AXIS_COLOR },
      axisLabel: { color: AXIS_COLOR },
      splitLine: { lineStyle: { color: GRID_COLOR } },
    },
    series: [
      {
        name: "區間下界",
        type: "line",
        stack: "ci",
        data: lowerBase,
        lineStyle: { opacity: 0 },
        showSymbol: false,
        areaStyle: { color: "transparent" },
        tooltip: { show: false },
      },
      {
        name: "信賴區間",
        type: "line",
        stack: "ci",
        data: bandHeight,
        lineStyle: { opacity: 0 },
        showSymbol: false,
        areaStyle: { color: "rgba(56,217,169,0.18)" },
      },
      {
        name: "預測可借",
        type: "line",
        data: lineData,
        connectNulls: false,
        smooth: true,
        symbolSize: 8,
        itemStyle: { color: "#38d9a9" },
        lineStyle: { color: "#38d9a9", width: 2 },
      },
    ],
  };
}

export default function StationForecastChart({ stationId }) {
  const station = useMemo(() => {
    try {
      const temporal = loadTemporalPresentation();
      return temporal.stations.find((item) => item.stationId === stationId) ?? null;
    } catch {
      return null;
    }
  }, [stationId]);

  return (
    <div>
      <Typography.Title level={5}>
        未來預測{" "}
        <Tag color="gold">Frontend-local Mock</Tag>
        <Tag color="purple">固定 +30／+60</Tag>
      </Typography.Title>

      {station ? (
        <>
          <ReactECharts option={buildOption(station)} style={{ height: 220 }} />
          <div className="forecast-slot-notes">
            {station.forecasts.map((forecast) => (
              <Typography.Text
                key={forecast.offsetMinutes}
                type="secondary"
                className="mono"
              >
                +{forecast.offsetMinutes}：
                {forecast.isAvailable
                  ? `${forecast.availableBikes} 台（區間 ${forecast.lowerBound}–${forecast.upperBound}）`
                  : `不可用（${forecast.reason}）`}
              </Typography.Text>
            ))}
          </div>
          <Alert
            type="info"
            showIcon
            message="此為固定 +30／+60 展示預測，非 Dispatch ETA，且不會送入派遣操作。"
          />
        </>
      ) : (
        <Alert
          type="info"
          showIcon
          message="此站無 frontend-local 預測 Mock（不可用）"
          description="目前僅少數站點提供固定 +30／+60 展示資料，其餘站點待真實預測接入後補齊。"
        />
      )}
    </div>
  );
}
