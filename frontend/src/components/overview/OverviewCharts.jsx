import { Card } from "antd";
import ReactECharts from "echarts-for-react";

export default function OverviewCharts({ overview, simulation }) {
  const operatorOption = {
    tooltip: { trigger: "item" },
    legend: { bottom: 0 },
    series: [
      {
        name: "人力狀態",
        type: "pie",
        radius: ["42%", "70%"],
        center: ["50%", "44%"],
        data: [
          { name: "執行中", value: overview.operators.busy },
          { name: "休息", value: overview.operators.resting },
          { name: "離勤", value: overview.operators.off_duty },
        ],
        color: ["#087f5b", "#fcc419", "#adb5bd"],
      },
    ],
  };

  const simulationOption = {
    tooltip: { trigger: "axis" },
    legend: { data: ["實際歷史", "本系統模擬"] },
    grid: { left: 48, right: 16, top: 44, bottom: 45 },
    xAxis: { type: "category", data: simulation["指標"], axisLabel: { interval: 0, rotate: 12 } },
    yAxis: { type: "value", name: "%" },
    series: [
      { name: "實際歷史", type: "bar", data: simulation["實際歷史"], itemStyle: { color: "#868e96" } },
      { name: "本系統模擬", type: "bar", data: simulation["本系統模擬"], itemStyle: { color: "#087f5b" } },
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
