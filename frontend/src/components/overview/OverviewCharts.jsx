import ReactECharts from "echarts-for-react";

const AXIS_COLOR = "#8ea0b5";
const GRID_COLOR = "rgba(148,163,184,0.15)";
const darkTooltip = {
  backgroundColor: "#0e1626",
  borderColor: "#243149",
  textStyle: { color: "#e5ecf5" },
};

const FILL = { height: "100%", width: "100%" };

// 調度人力狀態圓餅（bare chart，填滿容器）
export function OperatorPieChart({ overview }) {
  const option = {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1" },
    tooltip: { trigger: "item", ...darkTooltip },
    legend: { bottom: 0, textStyle: { color: AXIS_COLOR } },
    series: [
      {
        name: "人力狀態",
        type: "pie",
        radius: ["42%", "70%"],
        center: ["50%", "45%"],
        label: { color: "#cbd5e1" },
        data: [
          { name: "執行中", value: overview.operators.busy },
          { name: "休息", value: overview.operators.resting },
          { name: "離勤", value: overview.operators.off_duty },
        ],
        color: ["#38d9a9", "#ffa94d", "#4b5563"],
      },
    ],
  };
  return <ReactECharts option={option} style={FILL} />;
}

// Before / After 模擬成果長條（bare chart，填滿容器）
export function SimulationChart({ simulation }) {
  const option = {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1" },
    tooltip: { trigger: "axis", ...darkTooltip },
    legend: {
      data: ["實際歷史", "本系統模擬"],
      top: 6,
      textStyle: { color: AXIS_COLOR },
    },
    grid: { left: 52, right: 18, top: 48, bottom: 24, containLabel: true },
    xAxis: {
      type: "category",
      data: simulation["指標"],
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisLabel: {
        interval: 0,
        rotate: 0,
        color: AXIS_COLOR,
        fontSize: 11,
        margin: 12,
      },
    },
    yAxis: {
      type: "value",
      name: "%",
      nameTextStyle: { color: AXIS_COLOR },
      axisLabel: { color: AXIS_COLOR },
      splitLine: { lineStyle: { color: GRID_COLOR } },
    },
    series: [
      { name: "實際歷史", type: "bar", data: simulation["實際歷史"], itemStyle: { color: "#868e96" } },
      { name: "本系統模擬", type: "bar", data: simulation["本系統模擬"], itemStyle: { color: "#38d9a9" } },
    ],
  };
  return <ReactECharts option={option} style={FILL} />;
}
