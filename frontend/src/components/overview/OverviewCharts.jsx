import { useAppearance } from "../../theme/ThemeProvider.jsx";
import ReactECharts from "echarts-for-react";

const chartTooltip = (colors) => ({
  backgroundColor: colors.panel,
  borderColor: colors.border,
  textStyle: { color: colors.text },
});

const FILL = { height: "100%", width: "100%" };

// 調度人力狀態圓餅（bare chart，填滿容器）
export function OperatorPieChart({ overview }) {
  const { colors } = useAppearance();
  const option = {
    backgroundColor: "transparent",
    textStyle: { color: colors.text },
    tooltip: { trigger: "item", ...chartTooltip(colors) },
    legend: { bottom: 0, textStyle: { color: colors.muted } },
    series: [
      {
        name: "人力狀態",
        type: "pie",
        radius: ["42%", "70%"],
        center: ["50%", "45%"],
        label: { color: colors.text },
        data: [
          { name: "執行中", value: overview.operators.busy },
          { name: "休息", value: overview.operators.resting },
          { name: "離勤", value: overview.operators.off_duty },
        ],
        color: [colors.line, colors.info, colors.muted],
      },
    ],
  };
  return <ReactECharts option={option} style={FILL} />;
}

// Before / After 模擬成果長條（bare chart，填滿容器）
export function SimulationChart({ simulation }) {
  const { colors } = useAppearance();
  const option = {
    backgroundColor: "transparent",
    textStyle: { color: colors.text },
    tooltip: { trigger: "axis", ...chartTooltip(colors) },
    legend: {
      data: ["實際歷史", "本系統模擬"],
      top: 6,
      textStyle: { color: colors.muted },
    },
    grid: { left: 52, right: 18, top: 48, bottom: 24, containLabel: true },
    xAxis: {
      type: "category",
      data: simulation["指標"],
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: {
        interval: 0,
        rotate: 0,
        color: colors.muted,
        fontSize: 11,
        margin: 12,
      },
    },
    yAxis: {
      type: "value",
      name: "%",
      nameTextStyle: { color: colors.muted },
      axisLabel: { color: colors.muted },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    series: [
      { name: "實際歷史", type: "bar", data: simulation["實際歷史"], itemStyle: { color: colors.muted } },
      { name: "本系統模擬", type: "bar", data: simulation["本系統模擬"], itemStyle: { color: colors.line } },
    ],
  };
  return <ReactECharts option={option} style={FILL} />;
}
