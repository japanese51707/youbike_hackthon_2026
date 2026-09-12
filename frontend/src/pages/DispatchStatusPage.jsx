import { ReloadOutlined, CarOutlined, UserOutlined, EnvironmentOutlined, HomeOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Modal, Progress, Space, Tabs, Tag, Tooltip, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import SharedMap from "../components/map/SharedMap.jsx";
import {
  createPlanRouteLayers,
  createVehicleLayer,
} from "../components/map/layers/planLayers.js";
import { getRoadRoute } from "../api/routingApi.js";
import useDispatchStatus from "../hooks/useDispatchStatus.js";
import { formatDateTime } from "../utils/formatters.js";

// 分派任務狀況：把調度車+調度員依行政區分組呈現狀態（閒置/任務中/未上班/總部預備），
// 並顯示進行中任務的總時間、各站已等待時間、各站目標水位與完成狀態。
// 站點完成/任務結案由後端 ADR-310 自動偵測推進（達目標水位即完成，全站完成任務完成、車人回閒置）。

// ── 狀態語意對照 ──
// 調度員 status：off_duty=未上班、on_duty=閒置待命、busy=任務中
// 車輛 status：available=閒置、dispatched=任務中、standby=預備、maintenance=維修、off_duty=停用
const OPERATOR_STATUS = {
  busy: { label: "任務中", color: "processing" },
  on_duty: { label: "閒置待命", color: "success" },
  off_duty: { label: "未上班", color: "default" },
  resting: { label: "休息中", color: "warning" },
};
const VEHICLE_STATUS = {
  dispatched: { label: "任務中", color: "processing" },
  available: { label: "閒置", color: "success" },
  standby: { label: "預備", color: "gold" },
  maintenance: { label: "維修", color: "warning" },
  off_duty: { label: "停用", color: "default" },
};
const TASK_STATUS = {
  assigned: { label: "已指派・待出發", color: "gold" },
  in_progress: { label: "執行中", color: "processing" },
  completed: { label: "已完成", color: "success" },
  manual_required: { label: "需人工處理", color: "error" },
};
const ROLE_TYPE_LABEL = {
  driver: "調度司機",
  stationed: "駐點人員",
  depot_standby: "總部預備",
  controller: "控管",
};

// 「持續多久」：從某時間點到現在的相對時長（分/時）。
function durationSince(iso, now) {
  if (!iso) return "—";
  const start = new Date(iso).getTime();
  if (Number.isNaN(start)) return "—";
  const mins = Math.max(0, Math.round((now - start) / 60000));
  if (mins < 60) return `${mins} 分`;
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return `${h} 時 ${m} 分`;
}

function StatusDot({ map, value }) {
  const meta = map[value] ?? { label: value ?? "未知", color: "default" };
  return <Tag color={meta.color}>{meta.label}</Tag>;
}

// ── 點站點卡跳出的路線地圖（ADR-324）──
// 調度員看到某站落後時，第一個想知道的是「車現在在哪、還要跑幾站才到這裡」。
// 用任務既有的停靠順序畫實走道路路線，並把被點的那站標成焦點。
function RouteMapModal({ task, focusStationId, onClose }) {
  const stops = useMemo(
    () =>
      (task?.route ?? [])
        .map((s, i) => ({
          ...s,
          seq: i + 1,
          lat: Number(s.lat),
          lng: Number(s.lng),
          quantity: s.est_quantity ?? s.quantity,
        }))
        .filter((s) => Number.isFinite(s.lat) && Number.isFinite(s.lng)),
    [task],
  );
  const start = stops[0] ? { lat: stops[0].lat, lng: stops[0].lng } : null;
  const [geometry, setGeometry] = useState(null);

  useEffect(() => {
    if (!start || !stops.length) return undefined;
    let cancelled = false;
    const coords = [[start.lng, start.lat], ...stops.map((s) => [s.lng, s.lat])];
    getRoadRoute(coords)
      .then((res) => {
        if (!cancelled && res?.mode === "road") setGeometry(res.geometry);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [task?.task_id]);

  const layers = useMemo(() => {
    if (!start || !stops.length) return [];
    return [
      ...createPlanRouteLayers({ start, route: stops, geometry }),
      createVehicleLayer({ start }),
    ].filter(Boolean);
  }, [start, stops, geometry]);

  const focus = stops.find((s) => String(s.station_id) === String(focusStationId));

  return (
    <Modal
      open={Boolean(task)}
      onCancel={onClose}
      footer={null}
      width={820}
      title={`${task?.task_id ?? ""} 路線${focus ? `｜第 ${focus.seq} 站 ${focus.station_name ?? ""}` : ""}`}
    >
      <div className="dts-route-map">
        {start && stops.length ? (
          <SharedMap
            ariaLabel="任務路線地圖"
            className="map-fill"
            initialViewState={{
              longitude: focus ? focus.lng : start.lng,
              latitude: focus ? focus.lat : start.lat,
              zoom: focus ? 14.5 : 12.5,
            }}
            layers={layers}
            getTooltip={({ object }) =>
              object?.station_name
                ? { text: `${object.seq}. ${object.station_name}\n${object.action} ${object.quantity ?? ""} 台` }
                : null
            }
          />
        ) : (
          <div className="dts-route-map-empty">此任務沒有可用座標，無法顯示路線</div>
        )}
      </div>
      {task?.depot_load ? (
        <div className="dts-depot-load">
          <HomeOutlined /> {task.depot_load.label ?? `出發前於總部裝 ${task.depot_load.quantity} 台`}
        </div>
      ) : null}
    </Modal>
  );
}

// ── B：進行中任務卡 ──
function TaskCard({ task, now, onOpenMap }) {
  const meta = TASK_STATUS[task.task_status] ?? TASK_STATUS.assigned;
  const route = task.route ?? [];
  const done = route.filter((s) => s.station_status === "completed").length;
  const active = route.filter((s) => s.station_status !== "removed");
  const pct = active.length ? Math.round((done / active.length) * 100) : 0;

  return (
    <Card size="small" className="dispatch-task-card">
      <div className="dts-task-head">
        <Space size={6} wrap>
          <Typography.Text strong className="mono">{task.task_id}</Typography.Text>
          <Tag color={meta.color}>{meta.label}</Tag>
          <Tag icon={<EnvironmentOutlined />}>{task.district ?? "—"}</Tag>
          {task.task_type === "emergency" ? <Tag color="red">緊急</Tag> : null}
        </Space>
        <Space size={16} className="dts-task-time">
          <Tooltip title={`送出時間 ${formatDateTime(task.assigned_at)}`}>
            <span>單起始至今 <b className="mono">{durationSince(task.assigned_at, now)}</b></span>
          </Tooltip>
          {Number.isFinite(Number(task.estimated_total_minutes)) ? (
            <span className="dts-muted">預估 {Math.round(task.estimated_total_minutes)} 分</span>
          ) : null}
        </Space>
      </div>

      <div className="dts-task-resources">
        <Space size={12} wrap>
          <span><CarOutlined /> 調度車 <b>{task.assigned_vehicle ?? "—"}</b></span>
          <span><UserOutlined /> 司機 <b>{task.assigned_operator ?? "—"}</b></span>
          {task.assigned_escort ? <span><UserOutlined /> 隨車 <b>{task.assigned_escort}</b></span> : null}
        </Space>
      </div>

      {task.depot_load ? (
        <div className="dts-depot-load">
          <HomeOutlined />{" "}
          {task.depot_load.label ?? `出發前於總部裝 ${task.depot_load.quantity} 台`}
          <span className="dts-muted">（本趟車源，非沿途取車）</span>
        </div>
      ) : null}

      <div className="dts-progress-row">
        <Progress percent={pct} size="small" status={pct === 100 ? "success" : "active"}
          format={() => `${done}/${active.length} 站`} />
      </div>

      <div className="dts-stops">
        {route.map((s, i) => {
          const isDone = s.station_status === "completed";
          const isRemoved = s.station_status === "removed";
            // 當下站況優先用後端補的 live_*（ADR-324）；拿不到才退回組單當下的快照
            const bikes = Number.isFinite(Number(s.live_available_bikes))
              ? Number(s.live_available_bikes)
              : Number(s.current_available);
            const total = Number.isFinite(Number(s.live_total_docks))
              ? Number(s.live_total_docks)
              : Number(s.total_docks);
            const docks = Number.isFinite(Number(s.live_available_docks))
              ? Number(s.live_available_docks)
              : (Number.isFinite(total) && Number.isFinite(bikes) ? total - bikes : NaN);
            const target = Number(s.target_available);
            const isLive = Number.isFinite(Number(s.live_available_bikes));
            return (
            <div
              key={s.station_id ?? i}
              className={`dts-stop ${isDone ? "done" : ""} ${isRemoved ? "removed" : ""} clickable`}
              role="button"
              tabIndex={0}
              onClick={() => onOpenMap?.(task, s.station_id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onOpenMap?.(task, s.station_id);
                }
              }}
              title="點擊查看路線地圖"
            >
              <span className="dts-stop-seq mono">{i + 1}</span>
              <span className="dts-stop-main">
                <span className="dts-stop-name">{s.station_name ?? s.station_id}</span>
                <span className="dts-stop-sub dts-muted mono">
                  {s.action}
                  {isDone && Number.isFinite(Number(s.actual_available)) ? `｜實際 ${s.actual_available} 台` : ""}
                </span>
                {/* 三個數字一起看才有意義：現在幾台、還剩幾個空位、要補到幾台 */}
                <span className="dts-stop-levels mono">
                  <b>現有 {Number.isFinite(bikes) ? bikes : "—"} 台</b>
                  <span>空位 {Number.isFinite(docks) ? docks : "—"}</span>
                  <span className="dts-target">目標 {Number.isFinite(target) ? target : "—"} 台</span>
                  {!isLive ? <span className="dts-muted">（組單當下）</span> : null}
                </span>
              </span>
              <span className="dts-stop-status">
                {isRemoved ? (
                  <Tag>已抽離</Tag>
                ) : isDone ? (
                  <Tooltip title={s.auto_detected ? "系統偵測達目標水位自動完成" : "調度員回報完成"}>
                    <Tag color="success">已達標{s.auto_detected ? "・自動" : ""}</Tag>
                  </Tooltip>
                ) : (
                  <Tooltip title={`該站自任務送出已等待 ${durationSince(task.assigned_at, now)}`}>
                    <Tag color="gold">待處理・已等 {durationSince(task.assigned_at, now)}</Tag>
                  </Tooltip>
                )}
              </span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

// ── A：一組（行政區或總部）內的人清單（可選車輛；車不分班，只在車輛區塊顯示）──
function ResourceGroup({ title, icon, vehicles = null, operators }) {
  const idleOps = operators.filter((o) => o.status === "on_duty").length;
  const busyOps = operators.filter((o) => o.status === "busy").length;
  const offOps = operators.filter((o) => o.status === "off_duty").length;
  return (
    <Card size="small" className="dispatch-group-card"
      title={<Space size={6}>{icon}<span>{title}</span>
        <Typography.Text type="secondary" className="dts-muted">
          {vehicles !== null ? `車 ${vehicles.length}｜` : ""}人 {operators.length}
          （閒置 {idleOps}・任務中 {busyOps}・未上班 {offOps}）
        </Typography.Text></Space>}>
      {vehicles !== null ? (
        vehicles.length ? (
          <div className="dts-chip-row">
            {vehicles.map((v) => (
              <span key={v.vehicle_id} className="dts-chip">
                <CarOutlined /> <span className="mono">{v.vehicle_id}</span>
                <StatusDot map={VEHICLE_STATUS} value={v.status} />
                {v.current_task_id ? <span className="dts-muted mono">{v.current_task_id}</span> : null}
              </span>
            ))}
          </div>
        ) : <Typography.Text type="secondary" className="dts-muted">無車輛</Typography.Text>
      ) : null}
      {operators.length ? (
        <div className="dts-chip-row">
          {operators.map((o) => (
            <span key={o.operator_id} className="dts-chip">
              <UserOutlined /> <span className="mono">{o.operator_id}</span>
              {o.role_type && o.role_type !== "driver"
                ? <span className="dts-muted">{ROLE_TYPE_LABEL[o.role_type] ?? o.role_type}</span> : null}
              <StatusDot map={OPERATOR_STATUS} value={o.status} />
              {o.current_task_id ? <span className="dts-muted mono">{o.current_task_id}</span> : null}
            </span>
          ))}
        </div>
      ) : <Typography.Text type="secondary" className="dts-muted">無人員</Typography.Text>}
    </Card>
  );
}

// 一個班別分頁的內容：該班人力依行政區分組（+ 該班的總部預備）。
function ShiftPanel({ operators, depotOperators }) {
  const districts = [...new Set(operators.map((o) => o.current_district).filter(Boolean))].sort();
  const noDist = operators.filter((o) => !o.current_district);
  if (!operators.length && !depotOperators.length) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="此班別目前無排班人力" />;
  }
  return (
    <div className="dts-group-grid">
      {depotOperators.length ? (
        <ResourceGroup title="總部預備" icon={<HomeOutlined />} operators={depotOperators} />
      ) : null}
      {districts.map((d) => (
        <ResourceGroup key={d} title={d} icon={<EnvironmentOutlined />}
          operators={operators.filter((o) => o.current_district === d)} />
      ))}
      {noDist.length ? (
        <ResourceGroup title="未指派責任區" icon={<EnvironmentOutlined />} operators={noDist} />
      ) : null}
    </div>
  );
}

export default function DispatchStatusPage() {
  // ADR-324：點站點卡開路線地圖
  const [routeMap, setRouteMap] = useState(null);
  const openRouteMap = (task, stationId) => setRouteMap({ task, stationId });
  const { data, error, loading, reload } = useDispatchStatus();
  // 每 30 秒重算一次相對時間（讓「已等待 / 至今」跟著走，不必等輪詢）。
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  const tasks = data?.tasks ?? [];
  const operators = data?.operators ?? [];
  const vehicles = data?.vehicles ?? [];

  // 進行中任務（已指派/執行中）
  const activeTasks = tasks.filter((t) => ["assigned", "in_progress"].includes(t.task_status));

  // 總部預備：depot_standby 人員 + is_depot 車
  const depotOps = operators.filter((o) => o.role_type === "depot_standby");
  const depotVehicles = vehicles.filter((v) => v.is_depot);
  // 其餘依 current_district 分組（沒有區的歸「未指派區」）
  const fieldOps = operators.filter((o) => o.role_type !== "depot_standby");
  const fieldVehicles = vehicles.filter((v) => !v.is_depot);

  const idleOps = operators.filter((o) => o.status === "on_duty").length;
  const busyOps = operators.filter((o) => o.status === "busy").length;
  const offOps = operators.filter((o) => o.status === "off_duty").length;

  // 班別分組（ADR-312）：早/晚/大夜。車不分班（隨任務移動），只在車輛區塊依行政區顯示。
  const SHIFTS = [
    { key: "morning", label: "早班", hint: "06:30–15:30・含早高峰" },
    { key: "evening", label: "晚班", hint: "15:30–22:00・含晚高峰" },
    { key: "night", label: "大夜班", hint: "22:00–06:30・跨區大宗復原" },
  ];
  const opsByShift = (shift) => fieldOps.filter((o) => o.shift === shift);
  const depotByShift = (shift) => depotOps.filter((o) => o.shift === shift);
  const noShiftOps = fieldOps.filter((o) => !o.shift);

  const shiftTabs = SHIFTS.map((s) => {
    const ops = opsByShift(s.key);
    const dep = depotByShift(s.key);
    return {
      key: s.key,
      label: `${s.label}（${ops.length + dep.length}）`,
      children: (
        <>
          <Typography.Text type="secondary" className="dts-muted">{s.hint}</Typography.Text>
          <ShiftPanel operators={ops} depotOperators={dep} />
        </>
      ),
    };
  });
  // 未排班（含未分派 shift 的總部預備）另開一個分頁，避免漏看。
  const unshiftedOps = [...noShiftOps, ...depotOps.filter((o) => !o.shift)];
  if (unshiftedOps.length) {
    shiftTabs.push({
      key: "unassigned",
      label: `未排班（${unshiftedOps.length}）`,
      children: <ShiftPanel operators={unshiftedOps.filter((o) => o.role_type !== "depot_standby")}
        depotOperators={unshiftedOps.filter((o) => o.role_type === "depot_standby")} />,
    });
  }

  return (
    <div className="page-stack">
      <div className="dashboard-toolbar">
        <Typography.Title level={2}>分派任務狀況</Typography.Title>
        <Space wrap>
          <Tag color="processing">進行中任務 {activeTasks.length}</Tag>
          <Tag color="success">閒置人力 {idleOps}</Tag>
          <Tag color="blue">任務中 {busyOps}</Tag>
          <Tag>未上班 {offOps}</Tag>
          <Button size="small" icon={<ReloadOutlined />} onClick={reload}>重新整理</Button>
        </Space>
      </div>

      <AsyncState loading={loading && !data} error={error} data={data} onRetry={reload}>
        {/* B：進行中任務 */}
        <Card size="small" title={`進行中任務（${activeTasks.length}）`}>
          <Typography.Paragraph type="secondary" className="dts-muted">
            站點完成＝系統偵測到該站可借車數達目標水位（補車回升／取車下降至安全水位）；
            全部站點完成即任務完成，該調度車與調度員自動回到閒置待命。
          </Typography.Paragraph>
          {activeTasks.length ? (
            <div className="dts-task-list">
              {activeTasks.map((t) => (
                <TaskCard key={t.task_id} task={t} now={now} onOpenMap={openRouteMap} />
              ))}
            </div>
          ) : (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="目前沒有進行中的分派任務" />
          )}
        </Card>

        {/* A-1：調度員依班別（早/晚/大夜）分組，班內再依行政區 */}
        <Card size="small" title="調度人力排班（依班別 → 行政區）">
          <Typography.Paragraph type="secondary" className="dts-muted">
            人力分早/晚/大夜三班，班內依各行政區歷史工作量分派（早班含早高峰最多、晚班次之、
            大夜離峰做跨區大宗復原）。狀態：閒置待命 / 任務中 / 未上班。
          </Typography.Paragraph>
          <Tabs size="small" items={shiftTabs} />
        </Card>

        {/* A-2：車輛依行政區（車不分班，隨任務移動） */}
        <Card size="small" title="調度車輛（依行政區）">
          <div className="dts-group-grid">
            {depotVehicles.length ? (
              <ResourceGroup title="總部預備車" icon={<HomeOutlined />}
                vehicles={depotVehicles} operators={[]} />
            ) : null}
            {[...new Set(fieldVehicles.map((v) => v.current_district).filter(Boolean))].sort().map((d) => (
              <ResourceGroup key={d} title={d} icon={<EnvironmentOutlined />}
                vehicles={fieldVehicles.filter((v) => v.current_district === d)} operators={[]} />
            ))}
            {(() => {
              const noDistVeh = fieldVehicles.filter((v) => !v.current_district);
              return noDistVeh.length ? (
                <ResourceGroup title="未指派責任區" icon={<EnvironmentOutlined />}
                  vehicles={noDistVeh} operators={[]} />
              ) : null;
            })()}
          </div>
        </Card>
      </AsyncState>

      <RouteMapModal
        task={routeMap?.task ?? null}
        focusStationId={routeMap?.stationId}
        onClose={() => setRouteMap(null)}
      />
    </div>
  );
}
