import {
  AlertOutlined,
  CarOutlined,
  CheckCircleOutlined,
  DashboardOutlined,
  DisconnectOutlined,
  FieldTimeOutlined,
  HeartOutlined,
  EnvironmentOutlined,
  HeatMapOutlined,
  InboxOutlined,
  SoundOutlined,
  StopOutlined,
  SyncOutlined,
  TeamOutlined,
} from "@ant-design/icons";
import { Card, Collapse, List, Modal, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";
import DistrictPressureMap from "../components/overview/DistrictPressureMap.jsx";
import AsyncState from "../components/common/AsyncState.jsx";
import useServiceBoard from "../hooks/useServiceBoard.js";
import { formatDateTime, stationStatusLabels } from "../utils/formatters.js";
import {
  SERVICE_REF_THRESHOLDS as THRESHOLDS,
  buildHeadline,
  districtLongestOpen,
  districtServiceRows,
  dutyCounts,
  elapsedMinutesSince,
  formatDurationMinutes,
  longestOpenOfKind,
  openProblemsByStation,
  resolveCardCopy,
  rankDistrictPressure,
  ratesFromKpi,
} from "../utils/serviceBoard.js";

const KIND_LABEL = { empty: "空", full: "滿" };

function Light({ icon, label, value, suffix, ok, hint, timer, onClick }) {
  return (
    <button type="button" className={`service-stat slb-light${ok ? " is-ok" : " is-warn"}`} onClick={onClick}>
      <div className="slb-light-head">
        <span className="slb-light-icon">{icon}</span>
        <div className="service-stat-label">{label}</div>
      </div>
      <div className="slb-metric">
        <span className="slb-metric-num mono">{value}</span>
        <span className="slb-metric-suffix">{suffix}</span>
      </div>
      {timer ? <div className="slb-timer mono">{timer}</div> : null}
      <div className={`service-badge ${ok ? "ok" : "warn"}`}>{hint}</div>
    </button>
  );
}

function CardTitle({ icon, children }) {
  return (
    <span className="slb-card-title">
      {icon}
      {children}
    </span>
  );
}

function stationLine(s, elapsedMinutes) {
  const status = `${stationStatusLabels[s.status] ?? s.status}｜可借 ${s.available_bikes}／可還 ${s.available_docks}`;
  if (elapsedMinutes == null) return status;
  return `${status}｜已持續 ${formatDurationMinutes(elapsedMinutes)}`;
}

function StationGroupCollapse({ rows, stationsKey, countKey, rateKey, countLabel, denomKey = "inService", denomLabel = "營運中", openById, nowMs }) {
  const items = rows.map((row) => ({
    key: row.district,
    label: `${row.district}　${countLabel} ${row[countKey]}／${denomLabel} ${row[denomKey]}（${row[rateKey]}%）`,
    children: (
      <List
        size="small"
        dataSource={row[stationsKey]}
        renderItem={(s) => (
          <List.Item>
            <List.Item.Meta
              title={s.station_name}
              description={stationLine(s, elapsedMinutesSince(openById.get(s.station_id)?.opened_at, nowMs))}
            />
          </List.Item>
        )}
      />
    ),
  }));
  return <Collapse size="small" items={items} />;
}

function ResolutionModal({ problems, nowMs, onClose }) {
  if (!problems) return null;
  const city = problems.city ?? {};
  const items = (problems.districts ?? []).map((row) => ({
    key: row.district,
    label: `${row.district}　平均排除 ${formatDurationMinutes(row.avg_resolved_minutes)}　近 24 時 ${row.resolved_count} 件｜進行中 ${row.open_count}`,
    children: (
      <List
        size="small"
        locale={{ emptyText: "此區近 24 小時尚無排除紀錄，也沒有進行中的空／滿站" }}
        dataSource={row.worst_stations ?? []}
        renderItem={(s) => {
          const minutes = s.open ? elapsedMinutesSince(s.opened_at, nowMs) ?? s.minutes : s.minutes;
          return (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Typography.Text strong>{s.station_name}</Typography.Text>
                    <Tag color={s.kind === "empty" ? "red" : "orange"}>{KIND_LABEL[s.kind] ?? s.kind}</Tag>
                    <Tag color={s.open ? "volcano" : "default"}>{s.open ? "進行中" : "已排除"}</Tag>
                  </Space>
                }
                description={`${s.open ? "已持續" : "排除耗時"} ${formatDurationMinutes(minutes)}`}
              />
            </List.Item>
          );
        }}
      />
    ),
  }));

  return (
    <Modal title={<CardTitle icon={<FieldTimeOutlined />}>近 24 小時各區平均問題排除時間</CardTitle>} open footer={null} onCancel={onClose} width={760}>
      <Typography.Paragraph type="secondary">
        看的是「現在往回最多 24 小時」裡已經有的資料，不必等滿 24 小時。
        站況恢復才算排除。全市平均 {formatDurationMinutes(city.avg_resolved_minutes)}（{city.resolved_count ?? 0} 件），
        進行中 {city.open_count ?? 0} 站。
      </Typography.Paragraph>
      <Collapse size="small" items={items} />
    </Modal>
  );
}

function MetricModal({ metric, districts, rates, problems, nowMs, onClose }) {
  if (!metric) return null;
  const openById = openProblemsByStation(problems);

  if (metric === "empty") {
    const rows = districts.filter((row) => row.empty > 0).sort((a, b) => b.emptyRate - a.emptyRate || b.empty - a.empty);
    return (
      <Modal title={<CardTitle icon={<InboxOutlined />}>空站｜各區借不到車的站</CardTitle>} open footer={null} onCancel={onClose} width={720}>
        <Typography.Paragraph type="secondary">
          比例＝該區空站 ÷ 該區營運中站（不含離線）。全市 {rates.empty} 站、{rates.emptyRate}%。
          空站一出現即開始計時。
        </Typography.Paragraph>
        <StationGroupCollapse
          rows={rows}
          stationsKey="emptyStations"
          countKey="empty"
          rateKey="emptyRate"
          countLabel="空"
          openById={openById}
          nowMs={nowMs}
        />
      </Modal>
    );
  }

  if (metric === "full") {
    const rows = districts.filter((row) => row.full > 0).sort((a, b) => b.fullRate - a.fullRate || b.full - a.full);
    return (
      <Modal title={<CardTitle icon={<StopOutlined />}>滿站｜各區還不到位的站</CardTitle>} open footer={null} onCancel={onClose} width={720}>
        <Typography.Paragraph type="secondary">
          比例＝該區滿站 ÷ 該區營運中站（不含離線）。全市 {rates.full} 站、{rates.fullRate}%。
          滿站一出現即開始計時。
        </Typography.Paragraph>
        <StationGroupCollapse
          rows={rows}
          stationsKey="fullStations"
          countKey="full"
          rateKey="fullRate"
          countLabel="滿"
          openById={openById}
          nowMs={nowMs}
        />
      </Modal>
    );
  }

  if (metric === "health") {
    const rows = [...districts].sort((a, b) => a.healthRate - b.healthRate || a.district.localeCompare(b.district, "zh-Hant"));
    const weak = rows.filter((row) => row.inService > 0 && row.healthRate < rates.healthRate);
    return (
      <Modal title={<CardTitle icon={<HeartOutlined />}>健康率｜哪些區低於全市</CardTitle>} open footer={null} onCancel={onClose} width={720}>
        <Typography.Paragraph type="secondary">
          健康＝營運中且非空非滿（有車也有位）。全市 {rates.healthy}／{rates.inService}（{rates.healthRate}%）。
          下列依健康率由低到高；低於全市的區是處長該先看的。
        </Typography.Paragraph>
        <List
          size="small"
          dataSource={rows.filter((row) => row.inService > 0)}
          renderItem={(row) => (
            <List.Item>
              <List.Item.Meta
                title={
                  <Space wrap>
                    <Typography.Text strong>{row.district}</Typography.Text>
                    {row.healthRate < rates.healthRate ? <Tag color="orange">低於全市</Tag> : <Tag color="green">達全市</Tag>}
                  </Space>
                }
                description={`健康 ${row.healthy}／營運中 ${row.inService}（${row.healthRate}%）${row.healthRate < rates.healthRate ? `｜比全市低 ${(rates.healthRate - row.healthRate).toFixed(1)} 個百分點` : ""}`}
              />
            </List.Item>
          )}
        />
        <Typography.Paragraph type="secondary" style={{ marginTop: 12, marginBottom: 0 }}>
          {weak.length ? `${weak.length} 個行政區低於全市健康率。` : "沒有行政區低於全市。"}
        </Typography.Paragraph>
      </Modal>
    );
  }

  const rows = districts.filter((row) => row.offline > 0).sort((a, b) => b.offlineRate - a.offlineRate || b.offline - a.offline);
  return (
    <Modal title={<CardTitle icon={<DisconnectOutlined />}>離線站｜目前沒在提供服務的站</CardTitle>} open footer={null} onCancel={onClose} width={720}>
      <Typography.Paragraph type="secondary">
        離線＝可借與可還同時為 0（故障／未啟用），不計入空站或滿站。全市 {rates.offline}／{rates.total}（{rates.offlineRate}%）。
        這些站市民直接用不到，和「暫時沒車」不是同一件事。
      </Typography.Paragraph>
      <StationGroupCollapse
        rows={rows}
        stationsKey="offlineStations"
        countKey="offline"
        rateKey="offlineRate"
        countLabel="離線"
        denomKey="count"
        denomLabel="全區"
        openById={openById}
        nowMs={nowMs}
      />
    </Modal>
  );
}

export default function OverviewPage() {
  const board = useServiceBoard();
  const data = board.data;
  const [openDistrict, setOpenDistrict] = useState(null);
  const [focusDistrict, setFocusDistrict] = useState(null);
  const [metric, setMetric] = useState(null);
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const timer = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const view = useMemo(() => {
    if (!data) return null;
    const rates = ratesFromKpi(data.kpi);
    const districts = rankDistrictPressure(data.stations);
    const serviceDistricts = districtServiceRows(data.stations);
    const hot = districts.filter((row) => row.problems > 0).slice(0, 2).map((row) => row.district);
    const counts = data.overview?.task_counts ?? {};
    const openTasks = (counts.assigned || 0) + (counts.in_progress || 0) + (counts.manual_required || 0);
    const duty = dutyCounts(data.overview?.operators);
    const problems = data.problems ?? { city: {}, open: [], districts: [] };
    const city = problems.city ?? {};
    return {
      rates,
      districts,
      serviceDistricts,
      problems,
      city,
      headline: buildHeadline({ empty: rates.empty, full: rates.full, hotDistricts: hot }),
      remaining: rates.empty + rates.full,
      completed: counts.completed || 0,
      inProgress: counts.in_progress || 0,
      openTasks,
      duty,
      source: data.kpi?.source,
      fetchedAt: data.fetchedAt,
    };
  }, [data]);

  const openById = useMemo(() => openProblemsByStation(view?.problems), [view]);
  const longestEmpty = longestOpenOfKind(view?.problems, "empty", nowMs);
  const longestFull = longestOpenOfKind(view?.problems, "full", nowMs);
  const longestOpen = longestOpenOfKind(view?.problems, null, nowMs);
  const resolveCard = view
    ? resolveCardCopy({
      city: view.city,
      history: view.problems?.history,
      longestOpen,
      liveProblems: (view.rates.empty || 0) + (view.rates.full || 0),
    })
    : null;

  return (
    <div className="fixed-page slb-page">
      <div className="dashboard-toolbar">
        <Space align="center" size={10} wrap>
          <Typography.Title level={2}>
            <span className="slb-page-title">
              <DashboardOutlined />
              服務水準看板
            </span>
          </Typography.Title>
          <Tag color="blue">自動更新 60 秒</Tag>
          {view?.source ? <Tag>{view.source}</Tag> : null}
        </Space>
        <Tag>{view?.fetchedAt ? formatDateTime(new Date(view.fetchedAt).toISOString()) : "—"}</Tag>
      </div>

      <AsyncState loading={board.loading} error={board.error} data={data} onRetry={board.reload}>
        {view && (
          <>
            <div className="slb-headline">
              <span className="slb-headline-icon"><SoundOutlined /></span>
              <p>{view.headline}</p>
            </div>

            <div className="service-headline slb-lights">
              <Light
                icon={<InboxOutlined />}
                label="空站（借不到車）"
                value={view.rates.emptyRate}
                suffix="%"
                ok={view.rates.emptyRate <= THRESHOLDS.empty_rate}
                timer={longestEmpty == null ? "目前沒有空站時計" : `最長已空 ${formatDurationMinutes(longestEmpty)}`}
                hint={`${view.rates.empty} 站｜參考 <${THRESHOLDS.empty_rate}%`}
                onClick={() => setMetric("empty")}
              />
              <Light
                icon={<StopOutlined />}
                label="滿站（還不到位）"
                value={view.rates.fullRate}
                suffix="%"
                ok={view.rates.fullRate <= THRESHOLDS.full_rate}
                timer={longestFull == null ? "目前沒有滿站時計" : `最長已滿 ${formatDurationMinutes(longestFull)}`}
                hint={`${view.rates.full} 站｜參考 <${THRESHOLDS.full_rate}%`}
                onClick={() => setMetric("full")}
              />
              <Light
                icon={<HeartOutlined />}
                label="健康率（有車也有位）"
                value={view.rates.healthRate}
                suffix="%"
                ok={view.rates.healthRate >= THRESHOLDS.health_rate}
                hint={`${view.rates.healthy}／${view.rates.inService} 站｜參考 ≥${THRESHOLDS.health_rate}%`}
                onClick={() => setMetric("health")}
              />
              <Light
                icon={<DisconnectOutlined />}
                label="離線站（沒在服務）"
                value={view.rates.offlineRate}
                suffix="%"
                ok={view.rates.offlineRate <= THRESHOLDS.offline_rate}
                hint={`${view.rates.offline}／${view.rates.total} 站｜參考 <${THRESHOLDS.offline_rate}%`}
                onClick={() => setMetric("offline")}
              />
              <Light
                icon={<FieldTimeOutlined />}
                label="近 24 小時平均排除時間"
                value={resolveCard.value}
                suffix=""
                ok={(view.city.open_count ?? 0) === 0 || (longestOpen ?? 0) < 30}
                timer={resolveCard.timer}
                hint={resolveCard.hint}
                onClick={() => setMetric("resolve")}
              />
            </div>

            <div className="overview-main slb-main">
              <Card
                className="slb-card slb-map-card"
                title={<CardTitle icon={<HeatMapOutlined />}>行政區壓力</CardTitle>}
                extra={<Typography.Text type="secondary">綠穩定／黃留意／紅加壓｜問題站＝空＋滿</Typography.Text>}
                styles={{ body: { flex: 1, minHeight: 0, overflow: "hidden", display: "flex", flexDirection: "column" } }}
              >
                <div className="slb-pressure">
                  <DistrictPressureMap
                    districts={view.districts}
                    highlight={focusDistrict}
                    onHover={setFocusDistrict}
                    onSelect={setOpenDistrict}
                  />
                  <div className="slb-scroll">
                    <List
                      size="small"
                      dataSource={view.districts.filter((row) => row.problems > 0)}
                      locale={{ emptyText: "目前沒有空站或滿站集中的行政區" }}
                      renderItem={(row) => {
                        const longest = districtLongestOpen(row.district, view.problems, nowMs);
                        return (
                          <List.Item
                            className={`task-item slb-district-item${focusDistrict === row.district ? " is-focus" : ""}`}
                            onMouseEnter={() => setFocusDistrict(row.district)}
                            onMouseLeave={() => setFocusDistrict((cur) => (cur === row.district ? null : cur))}
                            onClick={() => setOpenDistrict(row)}
                          >
                            <span className={`slb-district-icon is-${row.pressure || "none"}`}><EnvironmentOutlined /></span>
                            <List.Item.Meta
                              title={
                                <Space wrap>
                                  <Typography.Text strong>{row.district}</Typography.Text>
                                  <Tag color="red">問題 {row.problems}</Tag>
                                  {longest != null ? <Tag color="volcano">最長 {formatDurationMinutes(longest)}</Tag> : null}
                                </Space>
                              }
                              description={`${row.count} 站｜空 ${row.empty}／滿 ${row.full}`}
                            />
                          </List.Item>
                        );
                      }}
                    />
                  </div>
                </div>
              </Card>

              <Card
                className="slb-card"
                title={<CardTitle icon={<CarOutlined />}>今日調度結果</CardTitle>}
              >
                <div className="slb-outcome">
                  <div className="slb-outcome-tile">
                    <div className="slb-outcome-head">
                      <CheckCircleOutlined />
                      <div className="service-stat-label">已完成</div>
                    </div>
                    <div className="slb-metric-num mono">{view.completed}</div>
                  </div>
                  <div className="slb-outcome-tile">
                    <div className="slb-outcome-head">
                      <SyncOutlined />
                      <div className="service-stat-label">進行中／未結</div>
                    </div>
                    <div className="slb-metric-num mono">{view.openTasks}</div>
                  </div>
                  <div className="slb-outcome-tile is-warn">
                    <div className="slb-outcome-head">
                      <AlertOutlined />
                      <div className="service-stat-label">仍空或仍滿</div>
                    </div>
                    <div className="slb-metric-num mono">{view.remaining}</div>
                  </div>
                </div>
                <div className="slb-notes">
                  <p>
                    <TeamOutlined /> 當班可派 {view.duty.onDuty} 人（執行中 {view.duty.busy}）。
                    此頁不派工；要出車請到調度面板。
                  </p>
                  <p>
                    <CarOutlined /> 進行中任務 {view.inProgress} 件。
                  </p>
                </div>
              </Card>
            </div>
          </>
        )}
      </AsyncState>

      <MetricModal
        metric={metric === "resolve" ? null : metric}
        districts={view?.serviceDistricts ?? []}
        rates={view?.rates}
        problems={view?.problems}
        nowMs={nowMs}
        onClose={() => setMetric(null)}
      />

      <ResolutionModal
        problems={metric === "resolve" ? view?.problems : null}
        nowMs={nowMs}
        onClose={() => setMetric(null)}
      />

      <Modal
        title={openDistrict ? <CardTitle icon={<HeatMapOutlined />}>{`${openDistrict.district}｜空／滿站（${openDistrict.stations.length}）`}</CardTitle> : ""}
        open={Boolean(openDistrict)}
        footer={null}
        onCancel={() => setOpenDistrict(null)}
      >
        <List
          size="small"
          dataSource={openDistrict?.stations ?? []}
          renderItem={(s) => (
            <List.Item>
              <List.Item.Meta
                title={s.station_name}
                description={stationLine(s, elapsedMinutesSince(openById.get(s.station_id)?.opened_at, nowMs))}
              />
            </List.Item>
          )}
        />
      </Modal>
    </div>
  );
}
