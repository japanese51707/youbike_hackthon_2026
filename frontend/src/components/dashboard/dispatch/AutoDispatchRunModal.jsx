import { CarOutlined, CheckCircleOutlined, EnvironmentOutlined, UserOutlined } from "@ant-design/icons";
import { Empty, Modal, Progress, Steps, Tag } from "antd";

// ADR-331：自動配單執行視窗。用「流動圖（Steps）+ 資源遞減 + 逐筆清單」把一輪自動配單
// 的過程視覺化：選取清單 → 逐筆配置（車/人/站遞減）→ 完成/停止。手動按「立即配單」跳出，
// 背景輪偵測到新一輪也跳出；完成（phase=done）後由呼叫端自動關閉。
//
// progress 由後端 GET /dispatch/auto-dispatch/progress 提供：
//   { phase, run_id, trigger, queue_total, processed, placed[], resources, stopped_because }

const PHASE_STEP = { selecting: 0, dispatching: 1, done: 2, idle: 0 };

function ResourceStat({ icon, label, value, accent }) {
  return (
    <div className="adr-run-stat" style={{ "--adr-accent": accent }}>
      <span className="adr-run-stat-icon">{icon}</span>
      <span className="adr-run-stat-val mono">{value ?? "—"}</span>
      <span className="adr-run-stat-label">{label}</span>
    </div>
  );
}

export default function AutoDispatchRunModal({ open, progress, onClose }) {
  const p = progress || {};
  const phase = p.phase || "idle";
  const stepCurrent = PHASE_STEP[phase] ?? 0;
  const res = p.resources || {};
  const placed = p.placed || [];
  const total = p.queue_total || 0;
  const processed = p.processed || 0;
  const pct = total ? Math.min(100, Math.round((processed / total) * 100)) : (phase === "done" ? 100 : 0);
  const isDone = phase === "done";

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      maskClosable={isDone}
      title={
        <span>
          自動配單執行中
          {p.trigger === "auto" ? <Tag color="blue" style={{ marginLeft: 8 }}>背景輪</Tag>
            : p.trigger === "manual" ? <Tag color="green" style={{ marginLeft: 8 }}>手動觸發</Tag> : null}
        </span>
      }
    >
      {/* 流動圖：選取清單 → 逐筆配置 → 完成 */}
      <Steps
        size="small"
        current={stepCurrent}
        status={isDone ? "finish" : "process"}
        items={[
          { title: "選取清單", description: total ? `${total} 個緊急站` : "讀取中" },
          { title: "逐筆配置", description: `已處理 ${processed}/${total}` },
          { title: "完成", description: isDone ? `配出 ${placed.length} 張` : "—" },
        ]}
      />

      {/* 即時剩餘資源（隨配置遞減） */}
      <div className="adr-run-resources">
        <ResourceStat icon={<CarOutlined />} label="可用調度車" value={res.vehicles_available} accent="#22c55e" />
        <ResourceStat icon={<CarOutlined />} label="總部待命車" value={res.vehicles_depot} accent="#a855f7" />
        <ResourceStat icon={<UserOutlined />} label="可派調度員" value={res.operators_assignable} accent="#3b82f6" />
        <ResourceStat icon={<UserOutlined />} label="總部待命人" value={res.operators_depot} accent="#a855f7" />
      </div>

      <Progress percent={pct} status={isDone ? "success" : "active"}
        format={() => `${processed}/${total || "?"}`} />

      {/* 逐筆配出的單（流動清單，最新在最上） */}
      <div className="adr-run-list">
        {placed.length ? (
          [...placed].reverse().map((it, i) => (
            <div key={it.trip_id ?? i} className="adr-run-item">
              <CheckCircleOutlined className="adr-run-item-ok" />
              <span className="adr-run-item-seq mono">#{placed.length - i}</span>
              <span className="adr-run-item-main">
                <b>{it.seed_station_name ?? it.seed_station}</b>
                {it.district ? <span className="adr-run-item-dist"><EnvironmentOutlined /> {it.district}</span> : null}
                <span className="adr-run-item-res mono">
                  <CarOutlined /> {it.vehicle ?? "—"}　<UserOutlined /> {it.operator ?? "—"}
                  {it.stations?.length > 1 ? `　(${it.stations.length} 站)` : ""}
                </span>
              </span>
              <span className="mono adr-run-item-id">{it.trip_id}</span>
            </div>
          ))
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={isDone ? (p.stopped_because || "本輪沒有配出派工單") : "配置中…"} />
        )}
      </div>

      {/* 停止/完成原因 */}
      {isDone && p.stopped_because ? (
        <div className="adr-run-stop">結束：{p.stopped_because}</div>
      ) : null}
    </Modal>
  );
}
