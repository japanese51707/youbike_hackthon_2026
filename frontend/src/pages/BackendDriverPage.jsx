import {
  CheckCircleOutlined,
  CompassOutlined,
  EnvironmentOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import {
  Alert,
  Button,
  Input,
  InputNumber,
  Modal,
  Progress,
  Segmented,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useEffect, useMemo, useState } from "react";
import useAsyncResource from "../hooks/useAsyncResource.js";
import {
  getAssignedWorkspace,
  reportStop,
  reportVehicleLoad,
  returnTask,
  setDuty,
  startTask,
} from "../api/taskApi.js";
import AsyncState from "../components/common/AsyncState.jsx";
import SharedMap from "../components/map/SharedMap.jsx";
import {
  createPlanRouteLayers,
  createVehicleLayer,
} from "../components/map/layers/planLayers.js";
import { getRoadRoute } from "../api/routingApi.js";
import { haversineKm } from "../utils/geo.js";
import "../styles/driver-workspace.css";

const ACTIVE_STATUSES = ["assigned", "in_progress"];
const DUTY_ROLES = ["driver", "depot_standby"];

// 版面預覽模式。auto = 跟著實際裝置寬度走（真的用手機開就是手機版面）；
// 其餘三個把舞台寬度鎖死，讓筆電上也能忠實預覽該裝置的版面（demo 用）。
const VIEW_KEY = "youbike.driver.view";
const VIEW_OPTIONS = [
  { value: "auto", label: "自動" },
  { value: "web", label: "網頁" },
  { value: "tablet", label: "平板" },
  { value: "phone", label: "手機" },
];
const VIEW_NOTE = {
  auto: "跟著目前視窗寬度自動切換",
  web: "桌機版面 · 最寬 1180px",
  tablet: "平板版面 · 834px",
  phone: "手機版面 · 412px",
};

function readView() {
  try {
    const saved = localStorage.getItem(VIEW_KEY);
    return VIEW_OPTIONS.some((o) => o.value === saved) ? saved : "auto";
  } catch {
    return "auto";
  }
}

// ── 小工具 ────────────────────────────────────────────────────────────

const num = (value) => {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
};

const point = (lat, lng) => {
  const a = num(lat);
  const b = num(lng);
  return a === null || b === null ? null : { lat: a, lng: b };
};

// 起點：車輛現在位置 → 司機現在位置 → 第一站（都拿不到就不畫地圖）。
function resolveStart(vehicle, operator, stops) {
  return (
    point(vehicle?.current_lat, vehicle?.current_lng) ||
    point(operator?.current_location?.lat, operator?.current_location?.lng) ||
    (stops[0] ? point(stops[0].lat, stops[0].lng) : null)
  );
}

function routeDistanceKm(start, stops) {
  if (!start || !stops.length) return null;
  let total = 0;
  let prev = start;
  for (const stop of stops) {
    const leg = haversineKm(prev, stop);
    if (!Number.isFinite(leg)) return null;
    total += leg;
    prev = stop;
  }
  return Math.round(total * 10) / 10;
}

// 整條路線導航：起點 → 途經點 → 終點，只帶公開座標。
function navUrl(from, stops) {
  if (!from || !stops.length) return null;
  const dest = stops[stops.length - 1];
  const mids = stops.slice(0, -1);
  const base =
    `https://www.google.com/maps/dir/?api=1&origin=${from.lat},${from.lng}` +
    `&destination=${dest.lat},${dest.lng}&travelmode=driving`;
  return mids.length
    ? `${base}&waypoints=${mids.map((s) => `${s.lat},${s.lng}`).join("|")}`
    : base;
}

function clockOf(iso) {
  if (typeof iso !== "string") return null;
  const match = iso.match(/T(\d{2}:\d{2})/);
  return match ? match[1] : null;
}

// 後端時間戳沒帶時區，跨時區時算出來的「已過幾分鐘」會離譜。
// 只在結果落在合理範圍（0～12 小時）才顯示，否則寧可不顯示。
function elapsedMinutes(iso, now) {
  if (typeof iso !== "string") return null;
  const started = Date.parse(iso);
  if (!Number.isFinite(started)) return null;
  const minutes = Math.round((now - started) / 60000);
  return minutes >= 0 && minutes <= 720 ? minutes : null;
}

const actionColor = (action) => (action === "取車" ? "orange" : "green");

// ── 車輛圖示（簡單的調度貨車側視圖）──────────────────────────────────

function TruckGlyph({ active }) {
  const body = active ? "var(--ct-accent)" : "var(--ct-muted)";
  return (
    <svg className="dw-truck" viewBox="0 0 96 52" role="img" aria-label="調度貨車">
      <rect x="2" y="12" width="54" height="28" rx="3" fill={body} />
      <path d="M56 20 h16 l12 12 v8 H56 Z" fill={body} opacity="0.72" />
      <rect x="60" y="23" width="12" height="9" rx="2" fill="var(--ct-panel)" opacity="0.9" />
      <rect x="8" y="18" width="42" height="4" rx="2" fill="var(--ct-panel)" opacity="0.55" />
      <rect x="8" y="26" width="30" height="4" rx="2" fill="var(--ct-panel)" opacity="0.4" />
      <circle cx="20" cy="43" r="7" fill="var(--ct-text)" />
      <circle cx="20" cy="43" r="2.6" fill="var(--ct-panel)" />
      <circle cx="72" cy="43" r="7" fill="var(--ct-text)" />
      <circle cx="72" cy="43" r="2.6" fill="var(--ct-panel)" />
      <rect x="2" y="38" width="86" height="3" rx="1.5" fill="var(--ct-border)" />
    </svg>
  );
}

// ── 閒置狀態 ─────────────────────────────────────────────────────────

function IdlePanel({ operator, busy, onToggleDuty, onReload }) {
  const offDuty = operator.status === "off_duty";
  return (
    <div className="dw-idle">
      <TruckGlyph active={false} />
      <div className="dw-idle-word">閒置</div>
      <div className="dw-idle-sub">
        {offDuty
          ? "尚未簽到值勤。簽到後後台才會把任務指派給你。"
          : "目前沒有指派給你的任務，待命中。有新任務會出現在這裡。"}
      </div>
      <Space wrap>
        {DUTY_ROLES.includes(operator.role_type) ? (
          <Button type={offDuty ? "primary" : "default"} size="large" loading={busy} onClick={onToggleDuty}>
            {offDuty ? "簽到值勤" : "下班"}
          </Button>
        ) : null}
        <Button size="large" icon={<ReloadOutlined />} disabled={busy} onClick={onReload}>
          重新整理
        </Button>
      </Space>
    </div>
  );
}

// ── 站點任務卡 ───────────────────────────────────────────────────────

function StopCard({ stop, current, canReport, busy, value, onChange, onReport, start }) {
  const done = stop.station_status === "completed" || stop.station_status === "done";
  const removed = stop.station_status === "skipped" || stop.station_status === "removed";
  const target = num(stop.target_available);
  const coords = point(stop.lat, stop.lng);
  return (
    <div className={`dw-stop${current ? " is-current" : ""}${done ? " is-done" : ""}${removed ? " is-removed" : ""}`}>
      <div className="dw-stop-head">
        <span className="dw-seq">{stop.seq}</span>
        <div className="dw-stop-title">
          <div className="dw-stop-name">{stop.station_name || stop.station_id}</div>
          <div className="dw-stop-meta mono">
            {stop.district ? `${stop.district}｜` : ""}
            {stop.station_id}
          </div>
        </div>
        <Tag color={actionColor(stop.action)} className="dw-stop-action">
          {stop.action}
          {num(stop.quantity) !== null ? ` ${num(stop.quantity)} 台` : ""}
        </Tag>
      </div>

      <div className="dw-stop-facts">
        <div><span>目標存量</span><b className="mono">{target ?? "—"}</b></div>
        <div><span>組單當下</span><b className="mono">{num(stop.current_available) ?? "—"}</b></div>
        <div><span>預計到達</span><b className="mono">{num(stop.arrival_offset_min) !== null ? `+${Math.round(num(stop.arrival_offset_min))} 分` : "—"}</b></div>
        <div><span>離站後車上</span><b className="mono">{num(stop.onboard_after) ?? "—"}</b></div>
      </div>

      {done ? (
        <Tag color="green" icon={<CheckCircleOutlined />}>已回報：{stop.actual_available} 台</Tag>
      ) : removed ? (
        <Tag>已從任務移除</Tag>
      ) : (
        <div className="dw-stop-actions">
          <Space.Compact className="dw-report">
            <InputNumber
              aria-label={`現場實際存量 ${stop.station_id}`}
              min={0}
              max={num(stop.total_docks) ?? undefined}
              precision={0}
              size="large"
              placeholder="現場實際存量"
              value={value ?? null}
              onChange={onChange}
            />
            {target !== null ? (
              <Button size="large" onClick={() => onChange(Math.round(target))}>
                帶入 {Math.round(target)}
              </Button>
            ) : null}
          </Space.Compact>
          <Space wrap>
            <Button
              type="primary"
              size="large"
              loading={busy}
              disabled={!canReport || !Number.isInteger(value)}
              onClick={onReport}
            >
              回報完成
            </Button>
            {coords ? (
              <Button
                size="large"
                icon={<CompassOutlined />}
                href={navUrl(start, [coords])}
                target="_blank"
                rel="noreferrer"
              >
                導航到這站
              </Button>
            ) : null}
          </Space>
        </div>
      )}
    </div>
  );
}

// ── 主畫面 ───────────────────────────────────────────────────────────

export default function BackendDriverPage() {
  const resource = useAsyncResource(getAssignedWorkspace);
  const [counts, setCounts] = useState({});
  const [load, setLoad] = useState(null);
  const [busy, setBusy] = useState(false);
  const [returning, setReturning] = useState(null);
  const [reason, setReason] = useState("");
  const [pickedTaskId, setPickedTaskId] = useState(null);
  const [now, setNow] = useState(() => Date.now());
  const [view, setView] = useState(readView);
  const [messageApi, contextHolder] = message.useMessage();

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(VIEW_KEY, view);
    } catch {
      /* 無痕模式等寫不進去就算了，不影響使用 */
    }
  }, [view]);

  const operator = resource.data?.operator ?? null;
  const vehicles = resource.data?.vehicles ?? {};
  const people = resource.data?.people ?? {};
  const active = useMemo(
    () =>
      (resource.data?.tasks ?? []).filter(
        (t) => ACTIVE_STATUSES.includes(t.task_status) && !t.resources_released,
      ),
    [resource.data],
  );

  const task =
    active.find((t) => t.task_id === pickedTaskId) ??
    active.find((t) => t.task_status === "in_progress") ??
    active[0] ??
    null;

  const stops = useMemo(
    () =>
      (task?.route ?? []).map((stop, index) => ({
        ...stop,
        seq: index + 1,
        quantity: stop.est_quantity ?? stop.quantity,
        station_status: stop.station_status || "pending",
      })),
    [task],
  );

  const vehicle = task?.assigned_vehicle ? vehicles[task.assigned_vehicle] : null;
  const start = useMemo(() => resolveStart(vehicle, operator, stops), [vehicle, operator, stops]);

  const mapStops = useMemo(
    () =>
      stops
        .map((stop) => ({ ...stop, ...(point(stop.lat, stop.lng) ?? {}) }))
        .filter((stop) => Number.isFinite(stop.lat) && Number.isFinite(stop.lng)),
    [stops],
  );

  // 實走道路路線：把「起點 + 各停靠點」丟給後端換沿路折線。
  // roadKey 是這組座標的指紋，座標沒變就不重打（後端也還有一層快取）。
  const roadKey = useMemo(() => {
    if (!start || !mapStops.length) return "";
    return [[start.lng, start.lat], ...mapStops.map((s) => [s.lng, s.lat])]
      .map(([lng, lat]) => `${lng.toFixed(5)},${lat.toFixed(5)}`)
      .join(";");
  }, [start, mapStops]);

  const [road, setRoad] = useState(null);

  useEffect(() => {
    if (!roadKey) {
      setRoad(null);
      return undefined;
    }
    let cancelled = false;
    const coordinates = roadKey.split(";").map((pair) => pair.split(",").map(Number));
    setRoad({ key: roadKey, loading: true });
    getRoadRoute(coordinates)
      .then((result) => {
        if (!cancelled) setRoad({ key: roadKey, ...result });
      })
      .catch(() => {
        // 後端不可用時仍要畫得出線：退回直線，並照實標示
        if (!cancelled) setRoad({ key: roadKey, mode: "straight", note: "路線服務無法連線" });
      });
    return () => {
      cancelled = true;
    };
  }, [roadKey]);

  const roadGeometry = road?.key === roadKey && road?.mode === "road" ? road.geometry : null;

  const layers = useMemo(() => {
    if (!start || !mapStops.length) return [];
    return [
      ...createPlanRouteLayers({ start, route: mapStops, geometry: roadGeometry }),
      createVehicleLayer({ start }),
    ].filter(Boolean);
  }, [start, mapStops, roadGeometry]);

  const pending = stops.filter((s) => s.station_status === "pending");
  const currentStop = pending[0] ?? null;
  const doneCount = stops.filter(
    (s) => s.station_status === "completed" || s.station_status === "done",
  ).length;
  const running = task?.task_status === "in_progress";
  const totalKm = routeDistanceKm(start, mapStops);
  const elapsed = elapsedMinutes(task?.assigned_at, now);
  // 有實走路線就用路由服務算的里程/時間，沒有才退回直線估算
  const roadKm =
    roadGeometry && Number.isFinite(road?.distance_m)
      ? Math.round(road.distance_m / 100) / 10
      : null;
  const roadMin =
    roadGeometry && Number.isFinite(road?.duration_s)
      ? Math.round(road.duration_s / 60)
      : null;
  const shownKm = roadKm ?? totalKm;

  // 執行中時盡量讓螢幕不要熄掉（司機把手機架在車上看路線）。不支援就算了。
  useEffect(() => {
    if (!running || !navigator.wakeLock?.request) return undefined;
    let sentinel = null;
    let cancelled = false;
    navigator.wakeLock
      .request("screen")
      .then((lock) => {
        if (cancelled) lock.release().catch(() => {});
        else sentinel = lock;
      })
      .catch(() => {});
    return () => {
      cancelled = true;
      sentinel?.release?.().catch(() => {});
    };
  }, [running]);

  const run = async (action) => {
    setBusy(true);
    try {
      await action();
      await resource.reload();
      messageApi.success("狀態已更新");
      return true;
    } catch (error) {
      messageApi.error(error.message);
      return false;
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dw" data-view={view}>
      {contextHolder}

      <div className="dw-toolbar">
        <Segmented
          size="small"
          value={view}
          onChange={setView}
          options={VIEW_OPTIONS}
          aria-label="切換預覽版面"
        />
        <span className="dw-toolbar-note mono">{VIEW_NOTE[view]}</span>
      </div>

      <div className="dw-stage">
      <AsyncState {...resource} onRetry={resource.reload}>
        {!operator ? (
          <Alert type="info" showIcon title="請在頁首先選擇司機身分" />
        ) : !task ? (
          <IdlePanel
            operator={operator}
            busy={busy}
            onToggleDuty={() =>
              run(() => setDuty(operator.status === "off_duty" ? "on_duty" : "off_duty"))
            }
            onReload={() => resource.reload().catch(() => {})}
          />
        ) : (
          <>
            {active.length > 1 ? (
              <Segmented
                block
                className="dw-task-switch"
                value={task.task_id}
                onChange={setPickedTaskId}
                options={active.map((t, i) => ({
                  value: t.task_id,
                  label: `任務 ${i + 1}｜${t.district || "跨區"}`,
                }))}
              />
            ) : null}

            <div className="dw-top">
              {/* 左上：車輛與人員 */}
              <section className="dw-vehicle" aria-label="車輛與人員">
                <div className="dw-vehicle-head">
                  <TruckGlyph active={running} />
                  <div>
                    <div className="dw-vehicle-id mono">{task.assigned_vehicle || "未配車"}</div>
                    <div className="dw-vehicle-sub">
                      {vehicle?.max_capacity ? `載運上限 ${vehicle.max_capacity} 台` : "調度貨車"}
                    </div>
                  </div>
                  <Tag color={running ? "processing" : "default"} className="dw-status-tag">
                    {running ? "執行中" : "待開始"}
                  </Tag>
                </div>

                <dl className="dw-crew">
                  <div>
                    <dt>駕駛</dt>
                    <dd>
                      {operator.name}
                      <span className="mono dw-dim"> · {operator.operator_id}</span>
                    </dd>
                  </div>
                  <div>
                    <dt>隨車</dt>
                    <dd>
                      {task.assigned_escort
                        ? people[task.assigned_escort]?.name ?? task.assigned_escort
                        : "單人作業"}
                    </dd>
                  </div>
                  <div>
                    <dt>責任區</dt>
                    <dd>{task.district || "跨區任務"}</dd>
                  </div>
                  <div>
                    <dt>派工</dt>
                    <dd className="mono">
                      {clockOf(task.assigned_at) ?? "—"}
                      {elapsed !== null ? ` · 已 ${elapsed} 分` : ""}
                    </dd>
                  </div>
                </dl>

                <div className="dw-onboard">
                  <div className="dw-onboard-row">
                    <span>出車車上</span>
                    <b className="mono">{num(task.onboard_start) ?? "未回報"}</b>
                    <span>預計收車</span>
                    <b className="mono">{num(task.onboard_planned_end) ?? "—"}</b>
                  </div>
                  {task.assigned_vehicle ? (
                    <Space.Compact className="dw-onboard-report">
                      <InputNumber
                        aria-label={`車上台數 ${task.assigned_vehicle}`}
                        min={0}
                        precision={0}
                        placeholder="更正車上台數"
                        value={load}
                        onChange={setLoad}
                      />
                      <Button
                        loading={busy}
                        disabled={!Number.isInteger(load)}
                        onClick={() =>
                          run(() => reportVehicleLoad(task.assigned_vehicle, load)).then((ok) => {
                            if (ok) setLoad(null);
                          })
                        }
                      >
                        回報
                      </Button>
                    </Space.Compact>
                  ) : null}
                </div>

                <div className="dw-progress">
                  <Progress
                    percent={stops.length ? Math.round((doneCount / stops.length) * 100) : 0}
                    size="small"
                    showInfo={false}
                    strokeColor="var(--ct-accent)"
                  />
                  <div className="dw-progress-label mono">
                    {doneCount} / {stops.length} 站完成
                    {shownKm !== null
                      ? `｜全程 ${shownKm} km${roadKm !== null ? "（實走）" : "（直線估算）"}`
                      : ""}
                    {roadMin !== null ? `｜約 ${roadMin} 分車程` : ""}
                  </div>
                </div>

                <Space wrap className="dw-vehicle-actions">
                  {task.task_status === "assigned" ? (
                    <Button type="primary" size="large" loading={busy} onClick={() => run(() => startTask(task.task_id))}>
                      開始任務
                    </Button>
                  ) : null}
                  {start && pending.length ? (
                    <Button
                      size="large"
                      icon={<CompassOutlined />}
                      href={navUrl(
                        start,
                        pending
                          .map((s) => point(s.lat, s.lng))
                          .filter(Boolean),
                      )}
                      target="_blank"
                      rel="noreferrer"
                    >
                      整條路線導航
                    </Button>
                  ) : null}
                  <Button size="large" icon={<ReloadOutlined />} disabled={busy} onClick={() => resource.reload().catch(() => {})}>
                    更新
                  </Button>
                  <Button
                    danger
                    size="large"
                    disabled={busy}
                    onClick={() => {
                      setReturning(task.task_id);
                      setReason("");
                    }}
                  >
                    退回任務
                  </Button>
                </Space>
              </section>

              {/* 右上：本趟路線地圖 */}
              <section className="dw-map" aria-label="本趟任務路線">
                {start && mapStops.length ? (
                  <>
                    <SharedMap
                      /* 切換版面會改變舞台寬度；重新掛載地圖，避免 canvas 停在舊尺寸 */
                      key={`${task.task_id}:${view}`}
                      ariaLabel="本趟任務路線地圖"
                      className="map-fill"
                      initialViewState={{ longitude: start.lng, latitude: start.lat, zoom: 12.4 }}
                      layers={layers}
                      getTooltip={({ object }) =>
                        object?.station_name
                          ? { text: `${object.seq}. ${object.station_name}\n${object.action} ${object.quantity ?? ""} 台` }
                          : null
                      }
                    />
                    <div className="dw-map-legend mono">
                      <span><i className="dot pickup" />取車</span>
                      <span><i className="dot dropoff" />補車</span>
                      <span><i className="dot start" />出發</span>
                      <span className={`dw-route-mode${roadGeometry ? " is-road" : ""}`}>
                        {road?.loading
                          ? "路線計算中…"
                          : roadGeometry
                            ? "實走路線"
                            : "直線示意"}
                      </span>
                    </div>
                  </>
                ) : (
                  <div className="dw-map-empty">此任務沒有可用座標，無法顯示路線</div>
                )}
              </section>
            </div>

            {/* 下方：任務卡片 */}
            {currentStop ? (
              <div className="dw-next mono">
                <EnvironmentOutlined /> 下一站 · 第 {currentStop.seq} 站 · {currentStop.station_name}
              </div>
            ) : null}

            <div className="dw-stops">
              {stops.map((stop) => {
                const key = `${task.task_id}:${stop.station_id}`;
                return (
                  <StopCard
                    key={key}
                    stop={stop}
                    start={start}
                    current={currentStop?.station_id === stop.station_id}
                    canReport={running}
                    busy={busy}
                    value={counts[key]}
                    onChange={(value) => setCounts((c) => ({ ...c, [key]: value }))}
                    onReport={() =>
                      run(() => reportStop(task.task_id, stop.station_id, counts[key])).then((ok) => {
                        if (ok) setCounts((c) => ({ ...c, [key]: undefined }));
                      })
                    }
                  />
                );
              })}
            </div>

            {!running ? (
              <Alert
                type="info"
                showIcon
                className="dw-foot"
                title="任務尚未開始，按「開始任務」後才能逐站回報"
              />
            ) : null}
          </>
        )}
      </AsyncState>

        <Typography.Text className="dw-hint">
          司機工作台｜執行中會盡量保持螢幕不熄滅
        </Typography.Text>
      </div>

      <Modal
        title="退回任務"
        open={Boolean(returning)}
        confirmLoading={busy}
        onCancel={() => !busy && setReturning(null)}
        okButtonProps={{ disabled: !reason.trim() }}
        onOk={async () => {
          if (await run(() => returnTask(returning, reason.trim()))) setReturning(null);
        }}
      >
        <Alert type="warning" title="執行中的任務退回後，需要管理者人工處理" />
        <Input.TextArea
          aria-label="退回原因"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="請說明退回原因"
          style={{ marginTop: 12 }}
        />
      </Modal>
    </div>
  );
}
