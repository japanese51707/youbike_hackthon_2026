import {
  AimOutlined,
  AlertOutlined,
  CheckCircleOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Badge, Button, Empty, Tabs, Tag, Typography } from "antd";
import DistrictNav from "./DistrictNav.jsx";
import { isSameMessage, stripStationName } from "../../../utils/dispatchMessage.js";
import {
  SCHEDULED,
  TRIAGE_HINTS,
  TRIAGE_LABELS,
  URGENT,
} from "../../../utils/dispatchTriage.js";

// 調度面板・待命態（ADR-206）：緊急調度 / 次安排調度（警報與缺口榜併入）/ 執行追蹤。
// 兩桶的分法在 utils/dispatchTriage.js，依後端 urgency_tier 與 priority_level 判定。
// 純呈現元件，資料與動作由 DashboardPage 提供；不進後端 payload。

const ALERT_LEVEL = {
  critical: { color: "var(--ct-danger)", label: "緊急" },
  warning: { color: "var(--ct-warning)", label: "警告" },
  info: { color: "var(--ct-info)", label: "提示" },
};

const STATUS_TONE = {
  empty: { color: "var(--ct-danger)", label: "無車可借" },
  low: { color: "var(--ct-warning)", label: "偏低" },
  normal: { color: "var(--ct-success)", label: "正常" },
  high: { color: "var(--ct-warning)", label: "偏高" },
  full: { color: "var(--ct-danger)", label: "車位滿載" },
};

// 任務狀態生命週期（送出後可見的狀態改變，owner 第 3 點）。
export const TRACK_STATUS = {
  assigned: { color: "gold", label: "已送出・待接單" },
  accepted: { color: "cyan", label: "司機已接" },
  in_progress: { color: "blue", label: "執行中" },
  completed: { color: "green", label: "完成" },
};

// critical（含截斷 censored）＝最高緊急，緊急度直接呈現 100；warning 顯示其分數（若有）。
// 合併卡片：一張卡同時呈現「站況警語（警報）」＋「該調度什麼（建議）」，最緊急排前。
function UrgencySection({ bucket, items, hint, nav, onPickStation, onFocus, onAcknowledge, onEmergency }) {
  return (
    <section className="deck-section deck-dispatch-body">
      {nav}
      <div className="deck-dispatch-list">
      {hint ? <div className="deck-section-hint">{hint}</div> : null}
      {items.length ? (
        <div className="deck-urgency-list">
          {items.map((item) => {
            const tone = STATUS_TONE[item.station.status] ?? STATUS_TONE.normal;
            const score = item.urgencyTier === "censored" ? 100 : Math.round(item.urgency);
            // 站況警語等級：優先用警報等級；沒警報但 censored/critical 也視為 critical。
            const level =
              item.alertLevel ||
              (item.urgencyTier === "censored" ? "critical" : score >= 60 ? "warning" : null);
            const levelMeta = level ? ALERT_LEVEL[level] : null;
            // 站名只在標題出現一次；警報與原因講同一件事時只留警報（它含「該做什麼」）。
            const alertText = stripStationName(item.alertMessage, item.station.station_name);
            const reasonText = stripStationName(item.reason, item.station.station_name);
            const sameThing = isSameMessage(alertText, reasonText);
            return (
              <div
                key={item.station.station_id}
                className={`deck-urgency-card${level ? ` deck-urgency-${level}` : ""}`}
                role="button"
                tabIndex={0}
                title="點擊定位並以此站組單"
                onClick={() => onPickStation?.(item.station)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onPickStation?.(item.station);
                }}
              >
                {/* 上排：緊急度分數 + 站名 + 警報等級徽章 + 定位鈕 */}
                <div className="deck-urgency-top">
                  <span className="deck-urgency-score mono" style={{ color: tone.color }}>
                    {score}
                  </span>
                  <span className="deck-urgency-name">{item.station.station_name}</span>
                  {levelMeta ? (
                    <Tag color={level === "critical" ? "red" : level === "warning" ? "orange" : "blue"}>
                      {levelMeta.label}
                    </Tag>
                  ) : null}
                  <span
                    className="deck-icon-btn"
                    role="button"
                    tabIndex={-1}
                    title="定位地圖"
                    onClick={(e) => {
                      e.stopPropagation();
                      onFocus?.(item.station);
                    }}
                  >
                    <AimOutlined />
                  </span>
                </div>

                {/* 站況警語（來自警報，若有）：已空站/已滿站/即將… */}
                {alertText ? (
                  <div className="deck-urgency-alert" style={{ color: levelMeta?.color }}>
                    <AlertOutlined /> {alertText}
                  </div>
                ) : null}

                {/* 調度指令：該站在哪個區、該補/取多少、補到幾台 */}
                <div className="deck-urgency-sub mono">
                  {item.station.district}｜{tone.label}｜
                  <b>{item.action} {item.quantity} 台</b>
                  {Number.isFinite(Number(item.targetAvailable))
                    ? `｜目標 ${item.targetAvailable} 台`
                    : ""}
                </div>

                {/* 建議原因（可解釋）；與警報重複時不再講第二次 */}
                {reasonText && !sameThing ? (
                  <div className="deck-urgency-reason">{reasonText}</div>
                ) : null}

                {/* 動作：緊急出車（critical）/ 標記已讀（有未讀警報）*/}
                {level === "critical" || item.alertId ? (
                  <div className="deck-urgency-actions">
                    {level === "critical" ? (
                      <Button
                        size="small"
                        danger
                        icon={<ThunderboltOutlined />}
                        onClick={(e) => {
                          e.stopPropagation();
                          onEmergency?.({ station_id: item.station.station_id });
                        }}
                      >
                        緊急出車
                      </Button>
                    ) : null}
                    {item.alertId && !item.alertAcknowledged ? (
                      <Button
                        size="small"
                        type="text"
                        onClick={(e) => {
                          e.stopPropagation();
                          onAcknowledge?.(item.alertId);
                        }}
                      >
                        標記已讀
                      </Button>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <Empty
          image={Empty.PRESENTED_IMAGE_SIMPLE}
          description={
            bucket === URGENT ? "目前沒有需要立刻出車的站" : "目前沒有可以慢慢安排的站"
          }
        />
      )}
      </div>
    </section>
  );
}

function TrackSection({ orders }) {
  return (
    <section className="deck-section">
      <div className="deck-section-title">
        進行中任務追蹤
        <span className="deck-count">{orders.length} 單</span>
      </div>
      {orders.length ? (
        <div className="deck-track-list">
          {orders.map((o) => {
            const meta = TRACK_STATUS[o.status] ?? TRACK_STATUS.assigned;
            const done = o.stops.filter((s) => s.stop_status === "completed").length;
            return (
              <div key={o.order_id} className="deck-track-card">
                <div className="deck-track-head">
                  <Typography.Text className="deck-track-id mono">{o.order_id}</Typography.Text>
                  <Tag color={meta.color}>{meta.label}</Tag>
                </div>
                <div className="deck-track-sub mono">
                  {o.vehicle?.vehicle_id ?? "待指派車"}｜{o.stops.length} 站｜
                  約 {o.estimate.totalMin} 分｜{o.estimate.distanceKm} km
                </div>
                <div className="deck-track-progress">
                  {o.stops.map((s) => (
                    <span
                      key={s.seq}
                      className={`deck-track-dot ${s.stop_status === "completed" ? "done" : ""}`}
                      title={`${s.seq}. ${s.station_name}（${s.action} ${s.quantity}）`}
                    />
                  ))}
                  <span className="deck-track-count mono">
                    {done}/{o.stops.length}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚無送出的調度單" />
      )}
    </section>
  );
}

// tab 標題：文字 + 數量 badge。
function TabLabel({ text, count, dot }) {
  return (
    <span className="deck-tab-label">
      {text}
      {count > 0 ? (
        <Badge
          count={count}
          size="small"
          color={dot === "danger" ? "var(--ct-danger)" : undefined}
          style={dot === "danger" ? undefined : { backgroundColor: "#4a5568" }}
        />
      ) : null}
    </span>
  );
}

export default function DispatchSidePanel({
  alerts,
  onAcknowledge,
  onEmergency,
  urgent = [],
  scheduled = [],
  visibleItems = [],
  activeTab = URGENT,
  onTabChange,
  districtCounts = [],
  district = "all",
  bucketTotal = 0,
  onDistrictChange,
  onPickStation,
  onFocus,
  orders,
  apiMode = false,
}) {
  const section = (bucket) => (
    <UrgencySection
      bucket={bucket}
      items={visibleItems}
      hint={TRIAGE_HINTS[bucket]}
      nav={
        <DistrictNav
          counts={districtCounts}
          value={district}
          total={bucketTotal}
          onChange={onDistrictChange}
        />
      }
      onPickStation={onPickStation}
      onFocus={onFocus}
      onAcknowledge={onAcknowledge}
      onEmergency={onEmergency}
    />
  );

  const tabItems = [
    {
      key: URGENT,
      label: <TabLabel text={TRIAGE_LABELS[URGENT]} count={urgent.length} dot="danger" />,
      children: section(URGENT),
    },
    {
      key: SCHEDULED,
      label: <TabLabel text={TRIAGE_LABELS[SCHEDULED]} count={scheduled.length} />,
      children: section(SCHEDULED),
    },
    {
      key: "track",
      label: <TabLabel text="任務追蹤" count={orders?.length ?? 0} />,
      children: <TrackSection orders={orders} />,
    },
  ];

  return (
    <div className="dispatch-deck">
      <Tabs
        className="deck-tabs"
        activeKey={activeTab}
        onChange={onTabChange}
        size="small"
        items={tabItems}
      />
      <div className="deck-foot">
        <CheckCircleOutlined />{" "}
        {apiMode
          ? "站況、建議、警示與任務皆來自後端；確認派發會寫入後端派工。"
          : "調度車位置與執行進度為 Mock 示意；送出僅本機展示，不寫入後端。"}
      </div>
    </div>
  );
}
