import { ReloadOutlined } from "@ant-design/icons";
import { Button, Card, Empty, Space, Table, Tag, Typography } from "antd";
import { useCallback, useEffect, useState } from "react";
import { peekResource, rememberResource } from "../api/resourceCache.js";
import AsyncState from "../components/common/AsyncState.jsx";
import {
  ACTION_LABELS,
  CLOSE_LABELS,
  STAGE_LABELS,
  formatWaited,
  getEscalationHistory,
  nextChaseCopy,
  waitedSince,
} from "../api/escalationApi.js";
import useEscalations from "../hooks/useEscalations.js";
import { formatDateTime } from "../utils/formatters.js";

// ADR-309：管理後台的警示追蹤。未結案在上（含階段與已等待時間），
// 歷史案件在下（含每一次人為動作的稽核軌跡）。

const stageTag = (stage) => (
  <Tag color={stage >= 2 ? "red" : stage === 1 ? "orange" : "default"}>
    L{stage}・{STAGE_LABELS[Math.min(stage, 2)]}
  </Tag>
);

export default function AlertTrackingPage() {
  const live = useEscalations();
  const [history, setHistory] = useState(() => peekResource("escalation-history"));
  const [error, setError] = useState(null);

  const loadHistory = useCallback(() => {
    getEscalationHistory(100)
      .then((rows) => {
        rememberResource("escalation-history", rows);
        setHistory(rows);
      })
      .catch(setError);
  }, []);
  useEffect(loadHistory, [loadHistory]);

  const openColumns = [
    { title: "階段", dataIndex: "stage", width: 130, render: stageTag },
    { title: "站點", dataIndex: "station_name",
      render: (name, row) => (
        <Space orientation="vertical" size={0}>
          <span>{name}</span>
          <Typography.Text type="secondary">{row.district}｜{row.trigger_reason}</Typography.Text>
        </Space>
      ) },
    { title: "已等待", dataIndex: "waited_minutes", width: 110,
      render: (v, row) => <b className="mono">{formatWaited(v ?? waitedSince(row.opened_at))}</b> },
    { title: "開案時間", dataIndex: "opened_at", width: 140, render: formatDateTime },
    { title: "下次催辦", dataIndex: "next_stage_at", width: 180,
      render: (_v, row) => nextChaseCopy(row) },
    { title: "狀態", dataIndex: "muted", width: 120,
      render: (muted) => (muted
        ? <Tag>靜音中（時鐘照走）</Tag>
        : <Tag color="red">待處理</Tag>) },
  ];

  const historyRows = Array.isArray(history) ? history : [];
  const closedHistory = historyRows.filter((row) => row.closed_at);
  const openFromHistory = historyRows
    .filter((row) => !row.closed_at)
    .map((row) => ({ ...row, stage: row.stage ?? row.highest_stage ?? 0 }));
  const openCases = live.cases.length ? live.cases : openFromHistory;

  const historyColumns = [
    { title: "站點", dataIndex: "station_name",
      render: (name, row) => <Space orientation="vertical" size={0}>
        <span>{name}</span>
        <Typography.Text type="secondary">{row.district}</Typography.Text>
      </Space> },
    { title: "開案", dataIndex: "opened_at", width: 140, render: formatDateTime },
    { title: "結果", dataIndex: "close_reason", width: 130,
      render: (reason, row) => (row.closed_at
        ? <Tag color={reason === "dispatched" ? "green" : "default"}>{CLOSE_LABELS[reason] ?? reason}</Tag>
        : <Tag color="red">未結案</Tag>) },
    { title: "最高階段", dataIndex: "highest_stage", width: 120, render: (s) => stageTag(s ?? 0) },
    { title: "處理軌跡", dataIndex: "actions",
      render: (actions) => (actions?.length
        ? <Space orientation="vertical" size={2}>
            {actions.map((a) => (
              <Typography.Text key={a.action_id} type="secondary">
                {formatDateTime(a.created_at)}　{a.actor}　{ACTION_LABELS[a.action] ?? a.action}
                {a.contact ? `（${a.contact}）` : ""}{a.note ? `：${a.note}` : ""}
              </Typography.Text>
            ))}
          </Space>
        : <Typography.Text type="secondary">無人為動作</Typography.Text>) },
  ];

  return (
    <div className="fixed-page alert-tracking-page">
      <div className="dashboard-toolbar">
        <Typography.Title level={2}>警示追蹤</Typography.Title>
        <Space>
          <Tag color="red">待處理 {openCases.length}</Tag>
          <Tag color="orange">需再提示 {live.counts.banner}</Tag>
          <Tag color="red">需電話聯絡 {live.counts.prompt}</Tag>
          <Button size="small" icon={<ReloadOutlined />}
            onClick={() => { live.reload(); loadHistory(); }}>重新整理</Button>
        </Space>
      </div>

      <Card size="small" className="alert-tracking-card alert-tracking-open" title="未結案案件">
        <Typography.Paragraph type="secondary" className="escalation-rule-note">
          空／滿站一出現就開案計時。未滿 30 分是「已開案」；滿 30 分「需再提示」；滿 45 分「需電話聯絡」。
          站況恢復才關案，派工或已讀都不關。
        </Typography.Paragraph>
        {live.error && !openCases.length ? (
          <Typography.Text type="danger">{live.error}</Typography.Text>
        ) : live.error ? (
          <Typography.Text type="secondary">即時狀態暫時讀不到，先顯示資料庫裡尚未關閉的案件。</Typography.Text>
        ) : null}
        <div className="alert-tracking-scroll">
          <Table rowKey="case_id" size="small" pagination={false}
            dataSource={openCases} columns={openColumns} loading={live.loading && openCases.length === 0}
            locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="目前沒有未結案的緊急案件" /> }} />
        </div>
      </Card>

      <Card size="small" className="alert-tracking-card alert-tracking-history" title="案件歷史與稽核軌跡">
        <div className="alert-tracking-scroll">
          <AsyncState loading={history === null && !error} error={error} data={history} onRetry={loadHistory}>
            <Table rowKey="case_id" size="small" pagination={{ pageSize: 10 }}
              dataSource={closedHistory} columns={historyColumns}
              locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚無案件紀錄" /> }} />
          </AsyncState>
        </div>
      </Card>
    </div>
  );
}
