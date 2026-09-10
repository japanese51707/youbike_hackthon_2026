import {
  ArrowLeftOutlined,
  CarOutlined,
  EnvironmentOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import { Alert, Button, Empty, Select, Steps, Tag, Typography } from "antd";

// 調度面板・組單態（ADR-206，右欄接管）：三入口共用的「選資源 → 路線預估 → 預覽確認」精靈。
// 先載後放路線由 tripPlanner 產出（示意，真正最優組單在後端 dispatch_builder）。

const MODE_META = {
  vehicle: { label: "車找站", icon: <CarOutlined />, hint: "以這台車的位置排出最適出車站點" },
  station: { label: "站找車", icon: <EnvironmentOutlined />, hint: "為這個站點找可用車並組單" },
  emergency: { label: "緊急出車", icon: <ThunderboltOutlined />, hint: "優先就近閒置車，其次動用預備車" },
};

const ACTION_COLOR = { 取車: "orange", 補車: "green" };

export default function OrderBuilder({
  draft,
  districts = [],
  onChangeVehicle,
  onChangeDistrict,
  onConfirm,
  onCancel,
}) {
  if (!draft) return null;
  const meta = MODE_META[draft.mode] ?? MODE_META.station;
  const { stops = [], estimate = {}, vehicle, candidates = [] } = draft;
  const canConfirm = stops.length > 0 && Boolean(vehicle);

  return (
    <div className="order-builder">
      <div className="ob-head">
        <Button type="text" size="small" icon={<ArrowLeftOutlined />} onClick={onCancel}>
          返回待命
        </Button>
        <Tag color="green" icon={meta.icon}>
          {meta.label}
        </Tag>
      </div>

      <Steps
        size="small"
        current={1}
        items={[{ title: "選資源" }, { title: "路線預估" }, { title: "預覽確認" }]}
      />

      {/* 步驟一：資源 */}
      <section className="ob-section">
        <div className="ob-section-title">資源</div>
        {draft.seedStation ? (
          <div className="ob-seed mono">
            目標站：{draft.seedStation.station_name}（{draft.seedStation.district}）
          </div>
        ) : null}

        {draft.mode === "vehicle" ? (
          <div className="ob-field">
            <span className="ob-label">出車：{vehicle?.vehicle_id}｜載運上限 {estimate.capacity} 台</span>
            <Select
              size="small"
              value={draft.district ?? undefined}
              placeholder="選擇行政區重算"
              style={{ minWidth: 140 }}
              onChange={onChangeDistrict}
              options={districts.map((d) => ({ value: d, label: `${d}（改區重算）` }))}
              allowClear
            />
          </div>
        ) : (
          <div className="ob-field">
            <span className="ob-label">可用車候選（該區 → 鄰近 → 總站待命）</span>
            <Select
              size="small"
              value={vehicle?.vehicle_id}
              style={{ minWidth: 220 }}
              onChange={onChangeVehicle}
              options={candidates.map((c) => ({
                value: c.vehicle.vehicle_id,
                label: `${c.vehicle.vehicle_id}｜${c.tier}｜${c.km.toFixed(1)}km${c.vehicle.is_reserve ? "（預備車）" : ""}`,
              }))}
              notFoundContent="無可用車"
            />
          </div>
        )}
        {draft.crossDistrict ? (
          <Alert
            type="warning"
            showIcon
            banner
            message="此草稿跨行政區（示意）。實際一趟不跨區的約束由後端組單處理。"
          />
        ) : null}
      </section>

      {/* 步驟二：路線（先載後放） */}
      <section className="ob-section">
        <div className="ob-section-title">路線（先載後放）</div>
        {stops.length ? (
          <div className="ob-route">
            {stops.map((s) => (
              <div key={s.seq} className="ob-stop">
                <span className="ob-stop-seq">{s.seq}</span>
                <span className="ob-stop-main">
                  <span className="ob-stop-name">{s.station_name}</span>
                  <span className="ob-stop-sub mono">{s.district}｜{s.leg_km} km</span>
                </span>
                <Tag color={ACTION_COLOR[s.action]}>{s.action} {s.quantity}</Tag>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="這台車附近無可組的取/補站（試著改車或改區）"
          />
        )}
      </section>

      {/* 步驟三：預估 + 確認 */}
      <section className="ob-section">
        <div className="ob-section-title">預估</div>
        <div className="ob-estimate">
          <div className="ob-metric">
            <span className="ob-metric-val mono">{estimate.distanceKm ?? 0}</span>
            <span className="ob-metric-label">總距離 km</span>
          </div>
          <div className="ob-metric">
            <span className="ob-metric-val mono">{estimate.totalMin ?? 0}</span>
            <span className="ob-metric-label">總時間 分</span>
          </div>
          <div className="ob-metric">
            <span className="ob-metric-val mono">
              {estimate.capacityUsed ?? 0}/{estimate.capacity ?? 0}
            </span>
            <span className="ob-metric-label">載運量 台</span>
          </div>
          <div className="ob-metric">
            <span className="ob-metric-val mono">{Math.round(estimate.urgencySum ?? 0)}</span>
            <span className="ob-metric-label">緊急度加總</span>
          </div>
        </div>
        <div className="ob-estimate-note mono">
          交通約 {estimate.travelMin ?? 0} 分＋作業約 {estimate.workMin ?? 0} 分
          {estimate.unplacedBikes > 0
            ? `｜尚有 ${estimate.unplacedBikes} 台未找到補車站`
            : ""}
        </div>
      </section>

      <div className="ob-foot">
        <Typography.Text type="secondary" className="ob-foot-note">
          預覽 → 確認才成立（人在迴圈）。確認僅本機示意，不送後端、不寫 DB。
        </Typography.Text>
        <div className="ob-foot-actions">
          <Button onClick={onCancel}>取消</Button>
          <Button type="primary" disabled={!canConfirm} onClick={onConfirm}>
            確認派發（示意）
          </Button>
        </div>
      </div>
    </div>
  );
}
