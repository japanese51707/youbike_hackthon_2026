import { Card } from "antd";
import ReactECharts from "echarts-for-react";

const AXIS_COLOR = "#8ea0b5";
const GRID_COLOR = "rgba(148,163,184,0.15)";
const darkTooltip = {
  backgroundColor: "#0e1626",
  borderColor: "#243149",
  textStyle: { color: "#e5ecf5" },
};

export default function OverviewCharts({ overview, simulation }) {
  const operatorOption = {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1" },
    tooltip: { trigger: "item", ...darkTooltip },
    legend: { bottom: 0, textStyle: { color: AXIS_COLOR } },
    series: [
      {
        name: "人力狀態",
        type: "pie",
        radius: ["42%", "70%"],
        center: ["50%", "44%"],
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

  const simulationOption = {
    backgroundColor: "transparent",
    textStyle: { color: "#cbd5e1" },
    tooltip: { trigger: "axis", ...darkTooltip },
    legend: {
      data: ["實際歷史", "本系統模擬"],
      top: 6,
      textStyle: { color: AXIS_COLOR },
    },
    grid: { left: 52, right: 18, top: 48, bottom: 72, containLabel: true },
    xAxis: {
      type: "category",
      data: simulation["指標"],
      axisLine: { lineStyle: { color: GRID_COLOR } },
      axisLabel: {
        interval: 0,
        rotate: 18,
        color: AXIS_COLOR,
        fontSize: 11,
        margin: 14,
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

  return (
    <div className="chart-grid">
      <Card title="調度人力狀態">
        <ReactECharts option={operatorOption} style={{ height: 300 }} />
      </Card>
      <Card title="Before / After 模擬成果">
        <ReactECharts option={simulationOption} style={{ height: 300 }} />
      </Card>
    </div>
  );
}
