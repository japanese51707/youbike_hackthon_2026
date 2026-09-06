import { CalendarOutlined, FileSearchOutlined } from "@ant-design/icons";
import { Card, List, Space, Tag, Typography } from "antd";
import AsyncState from "../components/common/AsyncState.jsx";
import MetricCard from "../components/common/MetricCard.jsx";
import TemporalPanel from "../components/temporal/TemporalPanel.jsx";
import DispatchPlannerPanel from "../components/overview/DispatchPlannerPanel.jsx";
import OverviewCharts from "../components/overview/OverviewCharts.jsx";
import TimelinePlayback from "../components/overview/TimelinePlayback.jsx";
import useOverviewData from "../hooks/useOverviewData.js";
import { formatCurrency, formatDateTime, formatNumber } from "../utils/formatters.js";

export default function OverviewPage() {
  const operations = useOverviewData();

  return (
    <AsyncState
      loading={operations.loading}
      error={operations.error}
      data={operations.data}
      onRetry={operations.reload}
    >
      {operations.data ? (
        <div className="page-stack">
          <div className="page-heading">
            <div>
              <Typography.Title level={2}>營運成效總覽</Typography.Title>
              <Typography.Paragraph>
                聚合人力、任務、站點壓力與模擬成果，供調度中心回顧。
              </Typography.Paragraph>
            </div>
            <Tag>{formatDateTime(operations.data.overview.timestamp)}</Tag>
          </div>

          <div className="metric-grid metric-grid-five">
            <MetricCard title="今日完成任務" value={operations.data.overview.today_totals.completed_tasks} suffix="件" />
            <MetricCard title="等待任務" value={operations.data.overview.today_totals.pending_tasks} suffix="件" tone="warning" />
            <MetricCard title="移動車輛" value={operations.data.overview.today_totals.total_bikes_moved} suffix="台" />
            <MetricCard title="行駛距離" value={operations.data.overview.today_totals.total_distance_km} suffix="km" />
            <MetricCard title="預估油資" value={formatCurrency(operations.data.overview.today_totals.estimated_fuel_cost)} />
          </div>

          <div className="metric-grid metric-grid-four">
            <MetricCard title="值勤人員" value={operations.data.overview.operators.on_duty} suffix="人" />
            <MetricCard title="空站" value={operations.data.overview.station_summary.empty_stations} suffix="站" tone="danger" />
            <MetricCard title="滿站" value={operations.data.overview.station_summary.full_stations} suffix="站" tone="warning" />
            <MetricCard title="需調度" value={operations.data.overview.station_summary.need_dispatch} suffix="站" tone="danger" />
          </div>

          <OverviewCharts
            overview={operations.data.overview}
            simulation={operations.data.simulation}
          />

          <DispatchPlannerPanel
            stations={operations.data.stations}
            operators={operations.data.operators}
          />

          <TimelinePlayback
            timeline={operations.data.timeline}
            stations={operations.data.stations}
          />

          <TemporalPanel />

          <div className="two-column-grid">
            <Card title="活動影響" extra={<CalendarOutlined />}>
              <List
                dataSource={operations.data.events}
                locale={{ emptyText: "目前沒有活動" }}
                renderItem={(event) => (
                  <List.Item>
                    <List.Item.Meta
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
            </Card>

            <Card title="最近稽核紀錄" extra={<FileSearchOutlined />}>
              <List
                dataSource={operations.data.auditLogs}
                locale={{ emptyText: "目前沒有紀錄" }}
                renderItem={(log) => (
                  <List.Item>
                    <List.Item.Meta
                      title={<Space wrap><Tag color="purple">{log.type}</Tag>{log.action}</Space>}
                      description={`${log.operator}｜${log.reason}｜${formatDateTime(log.timestamp)}`}
                    />
                  </List.Item>
                )}
              />
            </Card>
          </div>
        </div>
      ) : null}
    </AsyncState>
  );
}
