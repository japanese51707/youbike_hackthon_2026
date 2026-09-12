import {
  AimOutlined,
  AlertOutlined,
  CheckCircleOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Badge, Button, Empty, Tabs, Tag, Typography } from "antd";

// 調度面板・待命態（ADR-206）：警報區 / 需調度清單（緊急站排行，缺口榜併入）/ 執行追蹤。
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
function alertUrgency(a) {
  if (a.level === "critical") return 100;
  if (Number.isFinite(Number(a.priority_score))) return Math.round(Number(a.priority_score));
  return null;
}

function AlertsSection({ alerts, onAcknowledge, onEmergency, onFocusAlert }) {
  const sorted = [...(alerts ?? [])].sort((a, b) => {
    const rank = { critical: 0, warning: 1, info: 2 };
    return (rank[a.level] ?? 3) - (rank[b.level] ?? 3);
  });

  return (
    <section className="deck-section">
      <div className="deck-section-title">
        <AlertOutlined /> 警報區
        <span className="deck-count">{sorted.filter((a) => !a.acknowledged).length} 未讀</span>
      </div>
      {sorted.length ? (
        <div className="deck-alert-list">
          {sorted.map((a) => {
            const meta = ALERT_LEVEL[a.level] ?? ALERT_LEVEL.info;
            const urgency = alertUrgency(a);
            return (
              <div
                key={a.alert_id}
                className={`deck-alert deck-alert-${a.level}`}
                role="button"
                tabIndex={0}
                title="點擊定位到此站"
                onClick={() => onFocusAlert?.(a)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onFocusAlert?.(a);
                }}
              >
                <div className="deck-alert-head">
                  <span className="deck-alert-dot" style={{ background: meta.color }} />
                  <Typography.Text className="deck-alert-name">{a.station_name}</Typography.Text>
                  {urgency != null ? (
                    <span className="deck-alert-urgency mono" style={{ color: meta.color }}>
                      緊急度 {urgency}
                    </span>
                  ) : null}
                  <Tag color={a.level === "critical" ? "red" : a.level === "warning" ? "orange" : "blue"}>
                    {meta.label}
                  </Tag>
                  {a.acknowledged ? <Tag color="default">已讀</Tag> : null}
                </div>
                <div className="deck-alert-msg">{a.message}</div>
                <div className="deck-alert-actions">
                  {a.level === "critical" ? (
                    <Button
                      size="small"
                      danger
                      icon={<ThunderboltOutlined />}
                      onClick={(e) => {
                        e.stopPropagation();
                        onEmergency?.(a);
                      }}
                    >
                      緊急出車
                    </Button>
                  ) : null}
                  {!a.acknowledged ? (
                    <Button
                      size="small"
                      type="text"
                      onClick={(e) => {
                        e.stopPropagation();
                        onAcknowledge?.(a.alert_id);
                      }}
                    >
                      標記已讀
                    </Button>
                  ) : null}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="目前無警報" />
      )}
    </section>
  );
}

function UrgencySection({ items, onPickStation, onFocus }) {
  return (
    <section className="deck-section">
      <div className="deck-section-title">
        需調度清單
        <span className="deck-count">{items.length} 站</span>
      </div>
      {items.length ? (
        <div className="deck-urgency-list">
          {items.map((item) => {
            const tone = STATUS_TONE[item.station.status] ?? STATUS_TONE.normal;
            return (
              <button
                type="button"
                key={item.station.station_id}
                className="deck-urgency-row"
                onClick={() => onPickStation?.(item.station)}
                title={item.reason || "點擊以此站組單（站找車）"}
              >
                <span className="deck-urgency-score mono" style={{ color: tone.color }}>
                  {item.urgencyTier === "censored" ? 100 : Math.round(item.urgency)}
                </span>
                <span className="deck-urgency-main">
                  <span className="deck-urgency-name">
                    {item.station.station_name}
                    {item.predictionStatus === "degraded" ? (
                      <Tag color="default" style={{ marginLeft: 6, fontSize: 11 }}>
                        緊急度：即時降級
                      </Tag>
                    ) : null}
                  </span>
                  <span className="deck-urgency-sub mono">
                    {item.station.district}｜{tone.label}｜{item.action} {item.quantity} 台
                    {Number.isFinite(Number(item.targetAvailable))
                      ? `｜補到 ${item.targetAvailable} 台`
                      : Number.isFinite(Number(item.predicted))
                        ? `｜到達時 ${item.predicted} 台`
                        : ""}
                  </span>
                  {item.reason ? (
                    <span className="deck-urgency-reason">{item.reason}</span>
                  ) : null}
                </span>
                <span
                  className="deck-icon-btn"
                  role="button"
                  tabIndex={-1}
                  title="定位"
                  onClick={(e) => {
                    e.stopPropagation();
                    onFocus?.(item.station);
                  }}
                >
                  <AimOutlined />
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="目前無待調度站點" />
      )}
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
  onFocusAlert,
  urgencyItems,
  onPickStation,
  onFocus,
  orders,
  apiMode = false,
}) {
  const unreadAlerts = (alerts ?? []).filter((a) => !a.acknowledged).length;
  const criticalCount = (alerts ?? []).filter((a) => a.level === "critical").length;

  const tabItems = [
    {
      key: "alerts",
      label: <TabLabel text="警報區" count={unreadAlerts} dot={criticalCount > 0 ? "danger" : undefined} />,
      children: (
        <AlertsSection
          alerts={alerts}
          onAcknowledge={onAcknowledge}
          onEmergency={onEmergency}
          onFocusAlert={onFocusAlert}
        />
      ),
    },
    {
      key: "urgency",
      label: <TabLabel text="需調度清單" count={urgencyItems?.length ?? 0} dot="danger" />,
      children: (
        <UrgencySection items={urgencyItems} onPickStation={onPickStation} onFocus={onFocus} />
      ),
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
        defaultActiveKey="alerts"
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
