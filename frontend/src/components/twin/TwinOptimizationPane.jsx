import { Alert, Button, Descriptions, Empty, InputNumber, Popconfirm, Space, Table, Tag, Typography, message } from "antd";
import { useCallback, useEffect, useState } from "react";
import {
  approveReview,
  decideStation,
  EFFECT_LABELS,
  getDailyReview,
  rejectReview,
  STATUS_LABELS,
} from "../../api/optimizationApi.js";
import { getActorId, isApiMode } from "../../api/httpClient.js";
import AsyncState from "../common/AsyncState.jsx";
import useAsyncResource from "../../hooks/useAsyncResource.js";

const DECISIONS = [
  { key: "accept", label: "接受", type: "primary" },
  { key: "keep", label: "維持原值", type: "default" },
];

export default function TwinOptimizationPane({ onSelectStation, onHighlightStations }) {
  const resource = useAsyncResource(getDailyReview, { cacheKey: "daily-review" });
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

  useEffect(() => {
    const ids = (review?.station_changes || []).map((row) => row.station_id).filter(Boolean);
    onHighlightStations?.(ids);
    return () => onHighlightStations?.([]);
  }, [review, onHighlightStations]);

  const run = useCallback(
    async (action, okMessage) => {
      setBusy(true);
      setError("");
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
    },
    [messageApi],
  );

  const decide = async (stationId, decision) => {
    const params = decision === "re_adjust" ? overrides[stationId] : undefined;
    const done = await run(
      () => decideStation(review.review_id, stationId, decision, params),
      `已記錄 ${stationId}：${decision}`,
    );
    if (done) setDecisions((d) => ({ ...d, [stationId]: decision }));
  };

  const approve = async () => {
    const outcome = await run(() => approveReview(review.review_id), "已套用並存版本");
    if (outcome) setResult(outcome);
  };

  const reject = async () => {
    const outcome = await run(() => rejectReview(review.review_id), "已退回，未存版本");
    if (outcome) {
      setResult(null);
      resource.reload().catch(() => {});
    }
  };

  const columns = [
    {
      title: "站點",
      dataIndex: "station_name",
      key: "station",
      width: 140,
      render: (name, row) => (
        <Space orientation="vertical" size={0}>
          <Button type="link" className="twin-opt-station" onClick={() => onSelectStation?.(row.station_id)}>
            {name}
          </Button>
          <Typography.Text type="secondary">{row.station_id}</Typography.Text>
        </Space>
      ),
    },
    {
      title: "建議調整",
      dataIndex: "params",
      key: "params",
      render: (params) => (
        <Space orientation="vertical" size={0}>
          {(params || []).map((p) => (
            <Typography.Text key={p.param}>
              {p.param}：{p.old} → <b>{p.new}</b>（{p.change_pct > 0 ? "+" : ""}
              {p.change_pct}%）
            </Typography.Text>
          ))}
        </Space>
      ),
    },
    {
      title: "顯著",
      dataIndex: "is_significant",
      key: "significant",
      width: 64,
      render: (v) => (v ? <Tag color="orange">顯著</Tag> : <Tag>一般</Tag>),
    },
    {
      title: "決定",
      key: "decision",
      width: 200,
      render: (_, row) => (
        <Space wrap size={4}>
          {DECISIONS.map((d) => (
            <Button
              key={d.key}
              size="small"
              type={decisions[row.station_id] === d.key ? "primary" : "default"}
              disabled={busy || Boolean(result)}
              onClick={() => decide(row.station_id, d.key)}
            >
              {d.label}
            </Button>
          ))}
          <InputNumber
            size="small"
            step={0.01}
            min={0.5}
            max={2}
            placeholder="改值"
            aria-label={`人工調整 ${row.station_id}`}
            disabled={busy || Boolean(result)}
            onChange={(value) =>
              setOverrides((o) => ({
                ...o,
                [row.station_id]:
                  value === null ? undefined : (row.params || []).map((p) => ({ ...p, new: value })),
              }))
            }
          />
          <Button
            size="small"
            disabled={busy || Boolean(result) || !overrides[row.station_id]}
            onClick={() => decide(row.station_id, "re_adjust")}
          >
            套用改值
          </Button>
        </Space>
      ),
    },
  ];

  if (!isApiMode) {
    return (
      <div className="twin-opt">
        <Alert
          type="info"
          showIcon
          title="最適化審核只在後端連線模式下運作"
          description="每日最適化需要後端實際計算偏差，Mock 模式沒有對應資料。"
        />
      </div>
    );
  }

  return (
    <div className="twin-opt">
      {contextHolder}
      <Alert
        type={review?.coefficient_mode === "on" ? "warning" : "info"}
        showIcon
        className="twin-opt-banner"
        title={
          <Space size={6}>
            係數生效
            <Tag color={effect.color}>{effect.tag}</Tag>
          </Space>
        }
        description={effect.text}
      />

      <AsyncState {...resource} onRetry={resource.reload}>
        {!review ? (
          <Empty description="尚未取得建議" />
        ) : (
          <Space orientation="vertical" size={10} style={{ width: "100%" }}>
            {error ? <Alert type="error" showIcon title={error} /> : null}
            {result ? (
              <Alert
                type="success"
                showIcon
                title={result.message}
                description={`已存版本的站：${(result.committed_stations || []).join("、") || "—"}｜${result.effective_note || ""}`}
              />
            ) : null}

            <div className="twin-opt-meta">
              <Space wrap size={6}>
                <Tag color={statusLabel.color}>{statusLabel.text}</Tag>
                <Typography.Text type="secondary">{review.review_date}</Typography.Text>
                <Typography.Text type="secondary">回看 {review.lookback_days} 天</Typography.Text>
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() => {
                    setResult(null);
                    setDecisions({});
                    resource.reload().catch(() => {});
                  }}
                >
                  重新取得
                </Button>
              </Space>
              <Descriptions column={1} size="small" className="twin-opt-desc">
                <Descriptions.Item label="建議調整">{review.summary?.total_stations_adjusted ?? 0} 站</Descriptions.Item>
                <Descriptions.Item label="平均調幅">{review.summary?.avg_change_pct ?? 0}%</Descriptions.Item>
                <Descriptions.Item label="顯著站數">{review.summary?.significant_count ?? 0}</Descriptions.Item>
                <Descriptions.Item label="說明">{review.reason || "—"}</Descriptions.Item>
              </Descriptions>
              {review.diagnostics?.skipped_insufficient > 0 ? (
                <Typography.Text type="secondary">
                  樣本不足而跳過 {review.diagnostics.skipped_insufficient} 站
                </Typography.Text>
              ) : null}
            </div>

            {status !== "ok" ? (
              <Alert
                type="warning"
                showIcon
                title={`目前狀態為「${statusLabel.text}」，不可套用`}
                description="只有狀態為「可套用」的建議能核准；請先確認資料來源與樣本數。"
              />
            ) : null}

            {changes.length === 0 ? (
              <Empty description="這次沒有需要調整的站點" />
            ) : (
              <Table
                rowKey="station_id"
                size="small"
                dataSource={changes}
                columns={columns}
                pagination={{ pageSize: 8, showSizeChanger: false }}
                scroll={{ x: 520 }}
                onRow={(row) => ({
                  onDoubleClick: () => onSelectStation?.(row.station_id),
                })}
              />
            )}

            <Space wrap>
              <Popconfirm
                title="確認套用？"
                description="會把未選「維持原值」的站存成 ai_optimized 版本（全成或全退）"
                onConfirm={approve}
                okText="套用"
                cancelText="取消"
                disabled={busy || status !== "ok" || Boolean(result) || !getActorId()}
              >
                <Button
                  type="primary"
                  loading={busy}
                  disabled={status !== "ok" || Boolean(result) || !getActorId()}
                >
                  核准並套用
                </Button>
              </Popconfirm>
              <Button danger disabled={busy || Boolean(result)} onClick={reject}>
                退回，不存版本
              </Button>
              {!getActorId() ? (
                <Typography.Text type="warning">請先在頁首選擇 maintainer 身分</Typography.Text>
              ) : null}
            </Space>
          </Space>
        )}
      </AsyncState>
    </div>
  );
}
