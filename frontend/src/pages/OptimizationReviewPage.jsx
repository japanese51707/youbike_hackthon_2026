import { Alert, Button, Card, Descriptions, Empty, InputNumber, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useState } from "react";
import {
  approveReview, decideStation, EFFECT_LABELS, getDailyReview, rejectReview, STATUS_LABELS,
} from "../api/optimizationApi.js";
import { getActorId, isApiMode } from "../api/httpClient.js";
import AsyncState from "../components/common/AsyncState.jsx";
import useAsyncResource from "../hooks/useAsyncResource.js";

const DECISIONS = [
  { key: "accept", label: "接受", type: "primary" },
  { key: "keep", label: "維持原值", type: "default" },
];

export default function OptimizationReviewPage() {
  const resource = useAsyncResource(getDailyReview);
  const [busy, setBusy] = useState(false);
  const [decisions, setDecisions] = useState({});
  const [overrides, setOverrides] = useState({});
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [messageApi, contextHolder] = message.useMessage();

  const review = resource.data;
  const status = review?.status;
  const statusLabel = STATUS_LABELS[status] || { text: status || "—", color: "default" };
  const effect = EFFECT_LABELS[review?.coefficient_mode] || EFFECT_LABELS.off;
  const changes = review?.station_changes || [];

  const run = useCallback(async (action, okMessage) => {
    setBusy(true); setError("");
    try {
      const outcome = await action();
      messageApi.success(okMessage);
      return outcome;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }, [messageApi]);

  const decide = async (stationId, decision) => {
    const params = decision === "re_adjust" ? overrides[stationId] : undefined;
    const done = await run(
      () => decideStation(review.review_id, stationId, decision, params),
      `已記錄 ${stationId}：${decision}`);
    if (done) setDecisions(d => ({ ...d, [stationId]: decision }));
  };

  const approve = async () => {
    const outcome = await run(() => approveReview(review.review_id), "已套用並存版本");
    if (outcome) setResult(outcome);
  };

  const reject = async () => {
    const outcome = await run(() => rejectReview(review.review_id), "已退回，未存版本");
    if (outcome) { setResult(null); resource.reload().catch(() => {}); }
  };

  const columns = [
    { title: "站點", dataIndex: "station_name", key: "station",
      render: (name, row) => <Space orientation="vertical" size={0}>
        <Typography.Text>{name}</Typography.Text>
        <Typography.Text type="secondary">{row.station_id}</Typography.Text>
      </Space> },
    { title: "建議調整", dataIndex: "params", key: "params",
      render: params => <Space orientation="vertical" size={0}>
        {(params || []).map(p => <Typography.Text key={p.param}>
          {p.param}：{p.old} → <b>{p.new}</b>（{p.change_pct > 0 ? "+" : ""}{p.change_pct}%）
          <Typography.Text type="secondary"> · {p.scenario}／{p.samples} 筆</Typography.Text>
        </Typography.Text>)}
      </Space> },
    { title: "理由", dataIndex: "params", key: "reason",
      render: params => <Typography.Text type="secondary">
        {(params || []).map(p => p.reason).join("；")}
      </Typography.Text> },
    { title: "顯著", dataIndex: "is_significant", key: "significant",
      render: v => v ? <Tag color="orange">顯著</Tag> : <Tag>一般</Tag> },
    { title: "決定", key: "decision", render: (_, row) => <Space wrap>
      {DECISIONS.map(d => <Button key={d.key} size="small"
        type={decisions[row.station_id] === d.key ? "primary" : "default"}
        disabled={busy || Boolean(result)} onClick={() => decide(row.station_id, d.key)}>
        {d.label}
      </Button>)}
      <InputNumber size="small" step={0.01} min={0.5} max={2} placeholder="人工改值"
        aria-label={`人工調整 ${row.station_id}`}
        disabled={busy || Boolean(result)}
        onChange={value => setOverrides(o => ({
          ...o,
          [row.station_id]: value === null ? undefined
            : (row.params || []).map(p => ({ ...p, new: value })),
        }))} />
      <Button size="small" disabled={busy || Boolean(result) || !overrides[row.station_id]}
        onClick={() => decide(row.station_id, "re_adjust")}>套用改值</Button>
    </Space> },
  ];

  if (!isApiMode) {
    return <div style={{ padding: 24 }}>
      <Alert type="info" showIcon title="此頁只在後端連線模式下運作"
        description="每日最適化需要後端實際計算偏差，Mock 模式沒有對應資料。" />
    </div>;
  }

  return <div style={{ height: "100%", overflowY: "auto", padding: 16 }}>
    {contextHolder}
    <Typography.Title level={2}>② 每日最適化審核</Typography.Title>

    {/* ADR-304 §7：核准後到底會不會改變調度，由後端的 coefficient_mode 決定，不由前端自己講 */}
    <Alert type={review?.coefficient_mode === "on" ? "warning" : "info"} showIcon
      style={{ marginBottom: 16 }}
      title={<Space>係數生效狀態<Tag color={effect.color}>{effect.tag}</Tag></Space>}
      description={effect.text} />

    <AsyncState {...resource} onRetry={resource.reload}>
      {!review ? <Empty description="尚未取得建議" /> : <Space orientation="vertical" style={{ width: "100%" }}>
        {error && <Alert type="error" showIcon title={error} />}
        {result && <Alert type="success" showIcon title={result.message}
          description={`已存版本的站：${(result.committed_stations || []).join("、") || "—"}｜${result.effective_note || ""}`} />}

        <Card size="small" title={<Space>本次建議<Tag color={statusLabel.color}>{statusLabel.text}</Tag></Space>}
          extra={<Button disabled={busy} onClick={() => { setResult(null); setDecisions({}); resource.reload().catch(() => {}); }}>
            重新取得
          </Button>}>
          <Descriptions column={2} size="small">
            <Descriptions.Item label="review_id">{review.review_id}</Descriptions.Item>
            <Descriptions.Item label="日期">{review.review_date}</Descriptions.Item>
            <Descriptions.Item label="回看天數">{review.lookback_days} 天</Descriptions.Item>
            <Descriptions.Item label="建議調整站數">{review.summary?.total_stations_adjusted ?? 0}</Descriptions.Item>
            <Descriptions.Item label="平均調幅">{review.summary?.avg_change_pct ?? 0}%</Descriptions.Item>
            <Descriptions.Item label="顯著站數">{review.summary?.significant_count ?? 0}</Descriptions.Item>
            <Descriptions.Item label="狀態說明" span={2}>{review.reason || "—"}</Descriptions.Item>
          </Descriptions>
          {review.diagnostics?.skipped_insufficient > 0 && <Typography.Text type="secondary">
            樣本不足而跳過 {review.diagnostics.skipped_insufficient} 站
            （門檻 {review.diagnostics.skipped_stations?.[0]?.min_samples ?? "—"} 筆）
          </Typography.Text>}
        </Card>

        {status !== "ok" && <Alert type="warning" showIcon
          title={`目前狀態為「${statusLabel.text}」，不可套用`}
          description="只有狀態為「可套用」的建議能核准；請先確認資料來源與樣本數。" />}

        {changes.length === 0
          ? <Empty description="這次沒有需要調整的站點" />
          : <Table rowKey="station_id" size="small" dataSource={changes} columns={columns}
              pagination={{ pageSize: 20, showSizeChanger: false }} />}

        <Space>
          <Popconfirm title="確認套用？" description="會把未選「維持原值」的站存成 ai_optimized 版本（全成或全退）"
            onConfirm={approve} okText="套用" cancelText="取消"
            disabled={busy || status !== "ok" || Boolean(result) || !getActorId()}>
            <Button type="primary" loading={busy}
              disabled={status !== "ok" || Boolean(result) || !getActorId()}>
              核准並套用
            </Button>
          </Popconfirm>
          <Button danger disabled={busy || Boolean(result)} onClick={reject}>退回，不存版本</Button>
          {!getActorId() && <Typography.Text type="warning">請先在頁首選擇 maintainer 身分</Typography.Text>}
        </Space>
      </Space>}
    </AsyncState>
  </div>;
}
