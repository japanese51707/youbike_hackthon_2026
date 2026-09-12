import {
  ArrowLeftOutlined,
  CarOutlined,
  EnvironmentOutlined,
  ThunderboltOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Empty,
  InputNumber,
  Select,
  Space,
  Steps,
  Tag,
  Typography,
} from "antd";
import { useState } from "react";
import {
  blockingReasonsOf,
  canConfirm,
  nextStepFor,
  onboardBlocking,
} from "../../../utils/dispatchGating.js";

// 調度面板・組單態（ADR-206/119）：三入口共用「選資源 → 路線預估 → 預覽確認」精靈。
// API 模式：草稿（含 draft_id）由後端 dispatch_builder 計算，前端只呈現 + 依 blocking_reasons 決定可否確認。
// mock 模式：草稿由前端 tripPlanner 產出（示意），保留原顯示。

const MODE_META = {
  vehicle: { label: "車找站", icon: <CarOutlined />, hint: "以這台車的位置排出最適出車站點" },
  station: { label: "站找車", icon: <EnvironmentOutlined />, hint: "為這個站點找可用車並組單" },
  emergency: { label: "緊急出車", icon: <ThunderboltOutlined />, hint: "優先就近閒置車，其次動用預備車" },
};

const ACTION_COLOR = { 取車: "orange", 補車: "green" };

// 把後端 vehicle_candidates（{in_district, nearby, depot_standby} 皆為 ID 陣列）
// 攤平成下拉選項，標明來源層級。
function candidateOptions(vc) {
  if (!vc) return [];
  const tiers = [
    ["in_district", "該區"],
    ["nearby", "鄰近"],
    ["depot_standby", "總站待命"],
  ];
  const out = [];
  for (const [key, label] of tiers) {
    for (const id of vc[key] ?? []) {
      out.push({ value: id, label: `${id}｜${label}` });
    }
  }
  return out;
}

// 把後端 operator_candidates（{in_district, nearby, depot_standby} 皆為物件陣列）
// 攤平成下拉選項。後端已排優先序（同區在前）；同層級（同分）時調派員可自行改選。
function operatorOptions(oc) {
  if (!oc) return [];
  const tiers = [oc.in_district ?? [], oc.nearby ?? [], oc.depot_standby ?? []];
  const out = [];
  for (const list of tiers) {
    for (const o of list) {
      out.push({
        value: o.operator_id,
        label: `${o.operator_id}｜${o.tier}${o.current_district ? `｜${o.current_district}` : ""}`,
      });
    }
  }
  // 只保留前 60 筆，避免 347 名一次塞爆下拉（已排序，最優在前）。
  return out.slice(0, 60);
}

// 後端草稿的逐站清單：優先用 load_plan（有序、含到達偏移），否則用 stations。
function backendStops(draft) {
  if (Array.isArray(draft.load_plan) && draft.load_plan.length) {
    return draft.load_plan.map((s) => ({
      seq: s.seq,
      station_name: s.station_name,
      action: s.action,
      quantity: s.quantity,
      target_available: s.target_available,
      available_bikes: s.available_bikes,   // 當下可借車數
      available_docks: s.available_docks,   // 當下可還位數
      total_docks: s.total_docks,
      arrival_offset_min: s.arrival_offset_min,
      onboard_after: s.onboard_after,
    }));
  }
  return (draft.stations ?? []).map((s, i) => ({
    seq: i + 1,
    station_name: s.station_name,
    action: s.action,
    quantity: s.quantity,
    target_available: s.target_available,
    available_bikes: s.available_bikes ?? s.current_available,
    available_docks: s.available_docks
      ?? (s.total_docks != null && (s.available_bikes ?? s.current_available) != null
        ? Number(s.total_docks) - Number(s.available_bikes ?? s.current_available)
        : undefined),
    total_docks: s.total_docks,
  }));
}

// ── 後端草稿版（真實接線）──
function BackendBuilder({
  draft,
  onChangeVehicle,
  onChangeOperator,
  onChangeEscort,
  onConfirm,
  onCancel,
  onReportOnboard,
}) {
  const meta = MODE_META[draft.mode_key] ?? MODE_META.station;
  const stops = backendStops(draft);
  const estimate = draft.estimate ?? {};
  const reasons = blockingReasonsOf(draft);
  const needsOnboard = onboardBlocking(draft);
  const confirmable = canConfirm(draft);
  const [onboardValue, setOnboardValue] = useState(0);

  return (
    <div className="order-builder">
      <div className="ob-head">
        <Button type="text" size="small" icon={<ArrowLeftOutlined />} onClick={onCancel}>
          返回待命
        </Button>
        <Tag color="green" icon={meta.icon}>
          {meta.label}
        </Tag>
        <Tag color="blue">後端組單</Tag>
      </div>

      <Steps
        size="small"
        current={reasons.length ? 1 : 2}
        items={[{ title: "選資源" }, { title: "路線預估" }, { title: "預覽確認" }]}
      />

      {/* 步驟一：資源 */}
      <section className="ob-section">
        <div className="ob-section-title">資源</div>
        {draft.note ? <div className="ob-seed mono">{draft.note}</div> : null}
        <div className="ob-field">
          <span className="ob-label">
            出車：{draft.assigned_vehicle ?? "待指派"}｜載運上限 {draft.vehicle_capacity ?? "—"} 台
          </span>
          <Select
            size="small"
            showSearch
            optionFilterProp="label"
            value={draft.assigned_vehicle ?? undefined}
            style={{ minWidth: 200 }}
            onChange={onChangeVehicle}
            options={candidateOptions(draft.vehicle_candidates)}
            notFoundContent="無可用車"
            placeholder="選擇調度車"
          />
        </div>
        <div className="ob-field">
          <span className="ob-label">
            執行司機：{draft.assigned_operator ?? "待指派"}（後端排序，同分可改選）
          </span>
          <Select
            size="small"
            showSearch
            optionFilterProp="label"
            value={draft.assigned_operator ?? undefined}
            style={{ minWidth: 200 }}
            onChange={onChangeOperator}
            options={operatorOptions(draft.operator_candidates)}
            notFoundContent="無可派司機"
            placeholder="選擇執行司機"
          />
        </div>
        <div className="ob-field">
          <span className="ob-label">
            隨車人員：{draft.assigned_escort ?? "未指派（可選）"}（第二名，選填）
          </span>
          <Select
            size="small"
            showSearch
            allowClear
            optionFilterProp="label"
            value={draft.assigned_escort ?? undefined}
            style={{ minWidth: 200 }}
            onChange={(v) => onChangeEscort?.(v ?? null)}
            // 隨車候選沿用同一份人員池，但排除已選為司機的人（一人不可兼兩角）。
            options={operatorOptions(draft.operator_candidates).filter(
              (o) => o.value !== draft.assigned_operator,
            )}
            notFoundContent="無可派人員"
            placeholder="選擇隨車人員（可不選）"
          />
        </div>
        <div className="ob-field">
          <span className="ob-label">
            班別 {draft.shift ?? "—"}｜模式 {draft.mode ?? "—"}｜資料源 {draft.data_mode ?? "—"}
          </span>
        </div>
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
                  <span className="ob-stop-sub mono">
                    {/* 當下站況：可借車數 / 可還位數（現況 → 目標，一眼看出缺口）*/}
                    {Number.isFinite(Number(s.available_bikes))
                      ? `現況 可借 ${s.available_bikes}${Number.isFinite(Number(s.available_docks)) ? `／可還 ${s.available_docks}` : ""}`
                      : ""}
                    {Number.isFinite(Number(s.target_available))
                      ? `｜目標 ${s.target_available} 台`
                      : ""}
                    {Number.isFinite(Number(s.arrival_offset_min))
                      ? `｜約 ${Math.round(s.arrival_offset_min)} 分到達`
                      : ""}
                  </span>
                </span>
                <Tag color={ACTION_COLOR[s.action]}>
                  {s.action} {s.quantity}
                </Tag>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="後端未組出可派站點（試著換車或改走緊急出車）"
          />
        )}
      </section>

      {/* 步驟三：預估 */}
      <section className="ob-section">
        <div className="ob-section-title">預估</div>
        <div className="ob-estimate">
          <div className="ob-metric">
            <span className="ob-metric-val mono">{estimate.est_distance_km ?? 0}</span>
            <span className="ob-metric-label">總距離 km</span>
          </div>
          <div className="ob-metric">
            <span className="ob-metric-val mono">{Math.round(estimate.est_total_min ?? 0)}</span>
            <span className="ob-metric-label">總時間 分</span>
          </div>
          <div className="ob-metric">
            <span className="ob-metric-val mono">
              {estimate.total_quantity ?? 0}/{draft.vehicle_capacity ?? 0}
            </span>
            <span className="ob-metric-label">搬運量 台</span>
          </div>
          <div className="ob-metric">
            <span className="ob-metric-val mono">{Math.round(estimate.urgency_sum ?? 0)}</span>
            <span className="ob-metric-label">緊急度加總</span>
          </div>
        </div>
        <div className="ob-estimate-note mono">
          交通約 {Math.round(estimate.est_travel_min ?? 0)} 分＋作業約{" "}
          {Math.round(estimate.est_work_min ?? 0)} 分｜{estimate.stop_count ?? stops.length} 站
        </div>
      </section>

      {/* 阻擋原因（非空就不能確認，且在按之前就講清楚）*/}
      {reasons.length ? (
        <section className="ob-section">
          <Alert
            type="warning"
            showIcon
            message="這張草稿還不能確認"
            description={
              <ul style={{ margin: 0, paddingLeft: 18 }}>
                {reasons.map((r) => (
                  <li key={r.code}>
                    {r.message}
                    {nextStepFor(r.code) ? (
                      <div style={{ opacity: 0.8 }}>→ {nextStepFor(r.code)}</div>
                    ) : null}
                  </li>
                ))}
              </ul>
            }
          />
          {/* 車上台數未知/過期：就地回報即可解除，不用重挑站 */}
          {needsOnboard && draft.assigned_vehicle ? (
            <div className="ob-field" style={{ marginTop: 8 }}>
              <span className="ob-label">回報 {draft.assigned_vehicle} 車上台數</span>
              <Space.Compact>
                <InputNumber
                  size="small"
                  min={0}
                  max={draft.vehicle_capacity ?? 15}
                  value={onboardValue}
                  onChange={(v) => setOnboardValue(v ?? 0)}
                />
                <Button
                  size="small"
                  type="primary"
                  onClick={() => onReportOnboard?.(draft.assigned_vehicle, onboardValue)}
                >
                  回報並重算
                </Button>
              </Space.Compact>
            </div>
          ) : null}
        </section>
      ) : null}

      <div className="ob-foot">
        <Typography.Text type="secondary" className="ob-foot-note">
          預覽 → 確認才成立（人在迴圈）。確認會送後端寫入派工，需調派員權限。
        </Typography.Text>
        <div className="ob-foot-actions">
          <Button onClick={onCancel}>取消</Button>
          <Button type="primary" disabled={!confirmable} onClick={onConfirm}>
            確認派發
          </Button>
        </div>
      </div>
    </div>
  );
}

// ── 前端示意版（mock 模式，保留原行為）──
function MockBuilder({
  draft,
  districts,
  onChangeVehicle,
  onChangeDistrict,
  onConfirm,
  onCancel,
}) {
  const meta = MODE_META[draft.mode] ?? MODE_META.station;
  const { stops = [], estimate = {}, vehicle, candidates = [] } = draft;
  const canConfirmMock = stops.length > 0 && Boolean(vehicle);

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
          預覽 → 確認才成立（人在迴圈）。此為本機 Mock 示意，不送後端、不寫 DB。
        </Typography.Text>
        <div className="ob-foot-actions">
          <Button onClick={onCancel}>取消</Button>
          <Button type="primary" disabled={!canConfirmMock} onClick={onConfirm}>
            確認派發（示意）
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function OrderBuilder(props) {
  const { draft } = props;
  if (!draft) return null;
  // 後端草稿以 draft_id 辨識；沒有就是前端 tripPlanner 的 mock 示意草稿。
  return draft.draft_id ? <BackendBuilder {...props} /> : <MockBuilder {...props} />;
}
