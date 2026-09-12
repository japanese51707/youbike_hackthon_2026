import { useAppearance } from "../../theme/ThemeProvider.jsx";
import { InfoCircleOutlined } from "@ant-design/icons";
import { Alert, Tag, Tooltip, Typography } from "antd";
import ReactECharts from "echarts-for-react";
import { useMemo } from "react";

// 預測方式說明（依 lag 來源）：放進標題旁的 icon tooltip，不佔版面。
const PROXY_NOTE =
  "即時站況帶入 LightGBM 模型；因比賽階段僅有 1–6 月歷史，lag 特徵以「同站、同星期幾、同時段」的歷史中位數代理（週期性近似，非絕對前一天/前一週真值）。";
const DEGRADED_NOTE =
  "即時資料源尚無足夠歷史序列（lag）與天氣特徵，模型仍以現有特徵推估；區間會較寬，僅供參考。";

// 站點未來預測：用後端 LightGBM 的多視野預測（30/60/90/120 分鐘）畫可借車輛預測曲線。
// - 起點「現在」＝當前可借車數（current.available_bikes）。
// - 中線＝各視野 predicted_available（P50）；區間帶＝lower_bound(P10)~upper_bound(P90)。
// - y 軸固定 0 ~ 總柱數（total_docks）：最少 0 台、最多滿柱。
// 即時源缺歷史 lag / 天氣特徵時，後端仍以模型出預測但標 status=degraded，這裡誠實標示。


function buildOption(current, horizons, colors) {
  const capacity = Number(current.total_docks) || 0;
  const now = Number(current.available_bikes) || 0;

  const sorted = [...horizons].sort((a, b) => a.horizon_minutes - b.horizon_minutes);
  const labels = ["現在", ...sorted.map((h) => `+${h.horizon_minutes} 分`)];

  // 真實（未夾）區間邊界：可能 <0（空站悲觀情境仍在流出）或 >總柱數（滿站樂觀情境仍在流入）。
  const rawLo = (h) =>
    Number.isFinite(Number(h.raw_lower_bound)) ? Number(h.raw_lower_bound) : Number(h.lower_bound);
  const rawHi = (h) =>
    Number.isFinite(Number(h.raw_upper_bound)) ? Number(h.raw_upper_bound) : Number(h.upper_bound);

  // 物理可行線（實線，P50 夾在 0~總柱數）：起點放當前值。
  const clipped = [now, ...sorted.map((h) => Number(h.predicted_available))];
  // 被壓抑＝真實區間穿透物理界線（下界<0 或 上界>總柱數）：代表需求被空/滿站壓抑，殘量是假象。
  const hasSuppressed = sorted.some((h) => rawLo(h) < -0.05 || rawHi(h) > capacity + 0.05);
  // 真實趨勢虛線：畫「未夾的真實區間邊界」——下界穿透 0 就顯示缺口，上界超過柱數就顯示溢出。
  const rawLower = [now, ...sorted.map(rawLo)];
  const rawUpper = [now, ...sorted.map(rawHi)];

  // 區間帶（堆疊面積）：下界(透明) + (上界-下界)(填色)。起點無區間（現在是確定值）。
  const lowerBase = [null, ...sorted.map((h) => Number(h.lower_bound))];
  const bandHeight = [
    null,
    ...sorted.map((h) => Number(h.upper_bound) - Number(h.lower_bound)),
  ];

  // y 軸範圍：讓被壓抑的真實邊界（<0 或 >柱數）也畫得出來，上下各留一點。
  const yMin = hasSuppressed ? Math.floor(Math.min(0, ...rawLower) - 1) : 0;
  const yMax = hasSuppressed ? Math.ceil(Math.max(capacity, ...rawUpper) + 1) : capacity || null;

  const series = [
    {
      name: "區間下界",
      type: "line",
      stack: "ci",
      data: lowerBase,
      lineStyle: { opacity: 0 },
      showSymbol: false,
      areaStyle: { color: "transparent" },
      tooltip: { show: false },
      connectNulls: false,
    },
    {
      name: "安全區間 P10–P90",
      type: "line",
      stack: "ci",
      data: bandHeight,
      lineStyle: { opacity: 0 },
      showSymbol: false,
      areaStyle: { color: colors.band },
      connectNulls: false,
    },
    {
      name: "預測可借（實際會發生）",
      type: "line",
      data: clipped,
      smooth: true,
      symbolSize: 8,
      itemStyle: { color: colors.line },
      lineStyle: { color: colors.line, width: 2 },
      markLine: capacity
        ? {
            silent: true,
            symbol: "none",
            lineStyle: { color: colors.border, type: "dashed" },
            data: [
              { yAxis: capacity, name: "滿柱" },
              { yAxis: 0, name: "空站" },
            ],
            label: { color: colors.muted, formatter: (p) => (p.value === 0 ? "空站 0" : `滿柱 ${capacity}`) },
          }
        : undefined,
    },
  ];

  // 只有出現被壓抑需求時才畫「真實趨勢」虛線，避免正常站多一條重疊線干擾。
  // 空站畫真實下界（穿透 0 的缺口）、滿站畫真實上界（超過柱數的溢出），哪個穿透畫哪個。
  const suppressedLow = sorted.some((h) => rawLo(h) < -0.05);
  const suppressedHigh = sorted.some((h) => rawHi(h) > capacity + 0.05);
  if (hasSuppressed) {
    series.push({
      name: "真實趨勢（被壓抑需求）",
      type: "line",
      data: suppressedLow ? rawLower : rawUpper,
      smooth: true,
      showSymbol: false,
      lineStyle: { color: colors.danger || "#ff6b6b", width: 2, type: "dashed", opacity: 0.6 },
      itemStyle: { color: colors.danger || "#ff6b6b", opacity: 0.6 },
      z: 1,
    });
  }

  return {
    backgroundColor: "transparent",
    textStyle: { color: colors.text },
    legend: {
      data: hasSuppressed
        ? ["安全區間 P10–P90", "預測可借（實際會發生）", "真實趨勢（被壓抑需求）"]
        : ["安全區間 P10–P90", "預測可借（實際會發生）"],
      textStyle: { color: colors.muted, fontSize: 11 },
      top: 0,
      itemWidth: 18,
      itemHeight: 8,
    },
    tooltip: {
      trigger: "axis",
      backgroundColor: colors.panel,
      borderColor: colors.border,
      textStyle: { color: colors.text },
      formatter: (params) => {
        const idx = params[0].dataIndex;
        if (idx === 0) return `現在：${now} 台（實際）`;
        const h = sorted[idx - 1];
        const lo = rawLo(h);
        const hi = rawHi(h);
        let html = `+${h.horizon_minutes} 分<br/>實際會發生 ${h.predicted_available} 台<br/>安全區間 ${h.lower_bound}–${h.upper_bound} 台`;
        if (lo < -0.05) {
          html += `<br/><span style="opacity:.85">真實需求下界 ${lo.toFixed(1)} 台（穿透空站底，實際持續缺車，殘量是假象）</span>`;
        } else if (hi > capacity + 0.05) {
          html += `<br/><span style="opacity:.85">真實需求上界 ${hi.toFixed(1)} 台（穿透滿站頂，實際持續爆滿）</span>`;
        }
        return html;
      },
    },
    grid: { left: 40, right: 18, top: 30, bottom: 28, containLabel: true },
    xAxis: {
      type: "category",
      data: labels,
      boundaryGap: false,
      axisLine: { lineStyle: { color: colors.grid } },
      axisLabel: { color: colors.muted },
    },
    yAxis: {
      type: "value",
      name: "可借車輛",
      min: yMin,
      max: yMax,
      nameTextStyle: { color: colors.muted },
      axisLabel: { color: colors.muted },
      splitLine: { lineStyle: { color: colors.grid } },
    },
    series,
  };
}

export default function StationForecastChart({ current, prediction }) {
  const { colors } = useAppearance();
  const horizons = useMemo(
    () => (Array.isArray(prediction?.horizons) ? prediction.horizons : []),
    [prediction],
  );

  const available = prediction?.source && prediction.source !== "unavailable" && horizons.length > 0;

  return (
    <div>
      <Typography.Title level={5}>
        未來預測{" "}
        {available ? (
          <>
            {prediction.lag_source === "historical_proxy" ? (
              <Tag color="geekblue">歷史同時段代理</Tag>
            ) : prediction.status === "degraded" ? (
              <Tag color="gold">降級</Tag>
            ) : (
              <Tag color="cyan">完整特徵</Tag>
            )}
            {/* 說明改成 icon，游標經過才顯示，不佔版面 */}
            <Tooltip
              title={
                prediction.lag_source === "historical_proxy"
                  ? PROXY_NOTE
                  : prediction.status === "degraded"
                    ? DEGRADED_NOTE
                    : "即時站況帶入 LightGBM 模型；特徵完整。"
              }
            >
              <InfoCircleOutlined
                style={{ marginLeft: 6, color: "var(--ct-text-dim)", cursor: "help", fontSize: 14 }}
              />
            </Tooltip>
          </>
        ) : null}
      </Typography.Title>

      {available && current ? (
        <>
          <ReactECharts
            option={buildOption(current, horizons, colors)}
            style={{ height: 240 }}
            notMerge
          />
          <div className="forecast-slot-notes">
            {[...horizons]
              .sort((a, b) => a.horizon_minutes - b.horizon_minutes)
              .map((h) => (
                <Typography.Text key={h.horizon_minutes} type="secondary" className="mono">
                  +{h.horizon_minutes} 分：{h.predicted_available} 台（區間{" "}
                  {h.lower_bound}–{h.upper_bound}）
                </Typography.Text>
              ))}
          </div>
        </>
      ) : (
        <Alert
          type="info"
          showIcon
          message="此站目前無法提供預測"
          description={
            prediction?.reason ||
            "站點資料過期、停用，或預測所需特徵尚未就緒。"
          }
        />
      )}
    </div>
  );
}
