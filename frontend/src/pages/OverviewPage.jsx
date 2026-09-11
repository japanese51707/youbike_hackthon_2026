import BackendOverviewPage from "./BackendOverviewPage.jsx";
import { isApiMode } from "../api/httpClient.js";
import {
  CalendarOutlined,
  CheckCircleFilled,
  DollarOutlined,
  EnvironmentOutlined,
  FallOutlined,
  FileSearchOutlined,
  RiseOutlined,
  TeamOutlined,
  WarningFilled,
} from "@ant-design/icons";
import {
  Card,
  Descriptions,
  List,
  Modal,
  Space,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from "antd";
import { useMemo, useState } from "react";
import AsyncState from "../components/common/AsyncState.jsx";
import OverviewAssistant from "../components/overview/OverviewAssistant.jsx";
import { OperatorPieChart, SimulationChart } from "../components/overview/OverviewCharts.jsx";
import useOverviewData from "../hooks/useOverviewData.js";
import {
  aggregateDistricts,
  SERVICE_TARGETS as TARGETS,
} from "../utils/overviewAssistant.js";
import {
  formatCurrency,
  formatDateTime,
  formatNumber,
  stationStatusLabels,
} from "../utils/formatters.js";

function ServiceStat({ label, value, suffix, target, onClick }) {
  const hasTarget = Number.isFinite(target);
  const ok = hasTarget ? value <= target : true;
  return (
    <button type="button" className="service-stat" onClick={onClick}>
      <div className="service-stat-label">{label}</div>
      <div className="service-stat-value mono">
        {value}
        <span className="service-stat-suffix">{suffix}</span>
      </div>
      {hasTarget ? (
        <div className={`service-badge ${ok ? "ok" : "warn"}`}>
          {ok ? <CheckCircleFilled /> : <WarningFilled />}
          {ok ? "達標" : "超標"}｜目標 &lt;{target}
          {suffix}
        </div>
      ) : (
        <div className="service-stat-label">需即時處理</div>
      )}
    </button>
  );
}

function MockOverviewPage() {
  const operations = useOverviewData();
  const data = operations.data;
  const [modal, setModal] = useState(null);

  const districts = useMemo(() => (data ? aggregateDistricts(data) : []), [data]);

  const improvements = useMemo(() => {
    if (!data) return [];
    const sim = data.simulation;
    return sim["指標"].map((label, i) => {
      const actual = Number(sim["實際歷史"][i]);
      const model = Number(sim["本系統模擬"][i]);
      const pct = actual ? Math.round(((actual - model) / actual) * 100) : 0;
      return { label, actual, model, pct };
    });
  }, [data]);

  if (!data) {
    return (
      <AsyncState loading={operations.loading} error={operations.error} data={data} onRetry={operations.reload}>
        {null}
      </AsyncState>
    );
  }

  const { kpi, overview } = data;
  const serviceOk = kpi.empty_rate <= TARGETS.empty_rate && kpi.full_rate <= TARGETS.full_rate;

  const openMetric = (title, rows) =>
    setModal({
      title,
      content: (
        <Descriptions column={1} size="small" bordered>
          {rows.map(([label, value]) => (
            <Descriptions.Item key={label} label={label}>
              <span className="mono">{value}</span>
            </Descriptions.Item>
          ))}
        </Descriptions>
      ),
    });

  const openDistrict = (row) =>
    setModal({
      title: `${row.district}｜站點（${row.count}）`,
      content: (
        <List
          size="small"
          dataSource={row.stations}
          renderItem={(s) => (
            <List.Item>
              <List.Item.Meta
                title={s.station_name}
                description={`${stationStatusLabels[s.status] ?? s.status}｜可借 ${s.available_bikes}／可還 ${s.available_docks}｜使用率 ${s.usage_rate}%`}
              />
            </List.Item>
          )}
        />
      ),
    });

  return (
    <AsyncState loading={operations.loading} error={operations.error} data={data} onRetry={operations.reload}>
      <div className="fixed-page">
        <div className="dashboard-toolbar">
          <Space align="center" size={10}>
            <Typography.Title level={2}>營運成效總覽</Typography.Title>
            <Tag color={serviceOk ? "green" : "orange"} icon={serviceOk ? <CheckCircleFilled /> : <WarningFilled />}>
              {serviceOk ? "整體服務水準：達標" : "整體服務水準：需注意"}
            </Tag>
          </Space>
          <Tag>{formatDateTime(overview.timestamp)}</Tag>
        </div>

        {/* Zone 1：服務水準頭條（達標燈號） */}
        <div className="service-headline dashboard-kpis">
          <ServiceStat
            label="空站率（借不到車）"
            value={kpi.empty_rate}
            suffix="%"
            target={TARGETS.empty_rate}
            onClick={() =>
              openMetric("空站率", [
                ["目前空站率", `${kpi.empty_rate}%`],
                ["Demo 目標", `< ${TARGETS.empty_rate}%`],
                ["空站數", `${overview.station_summary.empty_stations} 站`],
                ["說明", "空站代表民眾借不到車，是服務水準核心指標"],
              ])
            }
          />
          <ServiceStat
            label="滿站率（還不到位）"
            value={kpi.full_rate}
            suffix="%"
            target={TARGETS.full_rate}
            onClick={() =>
              openMetric("滿站率", [
                ["目前滿站率", `${kpi.full_rate}%`],
                ["Demo 目標", `< ${TARGETS.full_rate}%`],
                ["滿站數", `${overview.station_summary.full_stations} 站`],
                ["說明", "滿站代表民眾還不了車，是服務水準核心指標"],
              ])
            }
          />
          <ServiceStat
            label="需調度站點"
            value={overview.station_summary.need_dispatch}
            suffix=" 站"
            onClick={() =>
              openMetric("需調度站點", [
                ["需調度", `${overview.station_summary.need_dispatch} 站`],
                ["空站", `${overview.station_summary.empty_stations} 站`],
                ["滿站", `${overview.station_summary.full_stations} 站`],
              ])
            }
          />
          <ServiceStat
            label="平均使用率"
            value={kpi.avg_usage_rate}
            suffix="%"
            onClick={() =>
              openMetric("平均使用率", [
                ["平均使用率", `${kpi.avg_usage_rate}%`],
                ["全系統站點", `${kpi.total_stations} 站`],
              ])
            }
          />
        </div>

        {/* Zone 2/3/4：成效圖 / 熱點分頁 / AI 助理 三欄並排 */}
        <div className="overview-main">
          <Card
            className="overview-hero"
            title="Before / After 模擬成果"
            extra={
              <Space size={6} wrap>
                {improvements.map((row) => {
                  const improved = row.pct >= 0;
                  return (
                    <Tooltip key={row.label} title={`實際 ${row.actual}% → 模擬 ${row.model}%`}>
                      <Tag color={improved ? "green" : "red"} icon={improved ? <FallOutlined /> : <RiseOutlined />}>
                        {row.label.replace("(%)", "")} {improved ? "↓" : "↑"}
                        {Math.abs(row.pct)}%
                      </Tag>
                    </Tooltip>
                  );
                })}
              </Space>
            }
          >
            <SimulationChart simulation={data.simulation} />
          </Card>

          <div className="dashboard-side">
            <Card size="small">
              <Tabs
                defaultActiveKey="hotspot"
                items={[
                  {
                    key: "hotspot",
                    label: (
                      <span>
                        <EnvironmentOutlined /> 熱點
                      </span>
                    ),
                    children: (
                      <List
                        size="small"
                        dataSource={districts}
                        renderItem={(row) => (
                          <List.Item
                            className="task-item"
                            onClick={() => openDistrict(row)}
                          >
                            <List.Item.Meta
                              title={
                                <Space wrap>
                                  <Typography.Text strong>{row.district}</Typography.Text>
                                  {row.problems ? (
                                    <Tag color="red">問題 {row.problems}</Tag>
                                  ) : (
                                    <Tag color="green">正常</Tag>
                                  )}
                                </Space>
                              }
                              description={
                                <span className="mono">
                                  {row.count} 站｜空 {row.empty}／滿 {row.full}｜使用率 {row.avg}%
                                </span>
                              }
                            />
                          </List.Item>
                        )}
                      />
                    ),
                  },
                  {
                    key: "fleet",
                    label: (
                      <span>
                        <TeamOutlined /> 人力與成本
                      </span>
                    ),
                    children: (
                      <div>
                        <div className="overview-pie">
                          <OperatorPieChart overview={overview} />
                        </div>
                        <Descriptions column={1} size="small">
                          <Descriptions.Item label={<><DollarOutlined /> 行駛距離</>}>
                            <span className="mono">{overview.today_totals.total_distance_km} km</span>
                          </Descriptions.Item>
                          <Descriptions.Item label="預估油資">
                            <span className="mono">{formatCurrency(overview.today_totals.estimated_fuel_cost)}</span>
                          </Descriptions.Item>
                          <Descriptions.Item label="每台移動油資">
                            <span className="mono">
                              {overview.today_totals.total_bikes_moved
                                ? formatCurrency(overview.today_totals.estimated_fuel_cost / overview.today_totals.total_bikes_moved)
                                : "—"}
                            </span>
                          </Descriptions.Item>
                          <Descriptions.Item label="移動車輛">
                            <span className="mono">{overview.today_totals.total_bikes_moved} 台</span>
                          </Descriptions.Item>
                        </Descriptions>
                      </div>
                    ),
                  },
                  {
                    key: "events",
                    label: (
                      <span>
                        <CalendarOutlined /> 活動 {data.events.length}
                      </span>
                    ),
                    children: (
                      <List
                        dataSource={data.events}
                        locale={{ emptyText: "目前沒有活動" }}
                        renderItem={(event) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<CalendarOutlined />}
                              title={event.event_name}
                              description={
                                <Space direction="vertical" size={2}>
                                  <Typography.Text>預估 {formatNumber(event.expected_attendance)} 人</Typography.Text>
                                  <Typography.Text type="secondary">
                                    影響半徑 {event.influence_radius_km} km｜{formatDateTime(event.start_time)} 起
                                  </Typography.Text>
                                </Space>
                              }
                            />
                            <Tag color={event.dispatch_requested ? "red" : "default"}>
                              {event.dispatch_requested ? "已要求調度" : "觀察中"}
                            </Tag>
                          </List.Item>
                        )}
                      />
                    ),
                  },
                  {
                    key: "audit",
                    label: (
                      <span>
                        <FileSearchOutlined /> 稽核 {data.auditLogs.length}
                      </span>
                    ),
                    children: (
                      <List
                        dataSource={data.auditLogs}
                        locale={{ emptyText: "目前沒有紀錄" }}
                        renderItem={(log) => (
                          <List.Item>
                            <List.Item.Meta
                              avatar={<FileSearchOutlined />}
                              title={<Space wrap><Tag color="purple">{log.type}</Tag>{log.action}</Space>}
                              description={`${log.operator}｜${log.reason}｜${formatDateTime(log.timestamp)}`}
                            />
                          </List.Item>
                        )}
                      />
                    ),
                  },
                ]}
              />
            </Card>
          </div>
        </div>

        <OverviewAssistant data={data} />

        <Modal title={modal?.title} open={Boolean(modal)} footer={null} onCancel={() => setModal(null)}>
          {modal?.content}
        </Modal>
      </div>
    </AsyncState>
  );
}

export default function OverviewPage() {
  return isApiMode ? <BackendOverviewPage /> : <MockOverviewPage />;
}
