import { CheckCircleFilled } from "@ant-design/icons";
import { Alert, Button, Modal, Segmented, Space, Tag, message } from "antd";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  approveReview,
  decideStation,
  rejectReview,
} from "../../api/optimizationApi.js";
import {
  createMockReview,
  DECISION_LABELS,
  describeParamChange,
  summarizeReviewDecisions,
} from "../../utils/optimizationReview.js";

function StationReviewCard({ row, locked, busy, onDecide, onSelect }) {
  const decision = row.decision || "accept";
  return (
    <article className={`twin-opt-card${row.is_significant ? " is-significant" : ""}`}>
      <header className="twin-opt-card-head">
        <div>
          <Button type="link" className="twin-opt-station" onClick={() => onSelect?.(row.station_id)}>
            {row.station_name}
          </Button>
          <div className="twin-opt-card-meta">
            {row.district || "—"}
            <span className="mono"> · {row.station_id}</span>
          </div>
        </div>
        {row.is_significant ? <Tag color="orange">顯著</Tag> : <Tag>一般</Tag>}
      </header>
      {row.why ? <p className="twin-opt-why">{row.why}</p> : null}
      <ul className="twin-opt-changes">
        {(row.params || []).map((item) => (
          <li key={item.param}>
            <span>{describeParamChange(item)}</span>
            {item.reason ? <small>{item.reason}</small> : null}
          </li>
        ))}
      </ul>
      <Segmented
        block
        size="middle"
        value={decision}
        disabled={busy || locked}
        options={[
          { value: "accept", label: DECISION_LABELS.accept },
          { value: "keep", label: DECISION_LABELS.keep },
        ]}
        onChange={(value) => onDecide(row.station_id, value)}
      />
    </article>
  );
}

export default function TwinOptimizationPane({ onSelectStation, onHighlightStations }) {
  const [review, setReview] = useState(() => createMockReview());
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  const changes = review.station_changes || [];
  const summary = useMemo(() => summarizeReviewDecisions(changes), [changes]);
  const locked = done;

  useEffect(() => {
    if (done) {
      onHighlightStations?.([]);
      return undefined;
    }
    const ids = changes.map((row) => row.station_id).filter(Boolean);
    onHighlightStations?.(ids);
    return () => onHighlightStations?.([]);
  }, [changes, done, onHighlightStations]);

  const run = useCallback(
    async (action, okMessage) => {
      setBusy(true);
      setError("");
      try {
        const outcome = await action();
        if (okMessage) messageApi.success(okMessage);
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
    const done = await run(
      () => decideStation(review.review_id, stationId, decision),
      `${DECISION_LABELS[decision]}：${changes.find((row) => row.station_id === stationId)?.station_name || stationId}`,
    );
    if (!done) return;
    setReview((current) => ({
      ...current,
      station_changes: (current.station_changes || []).map((row) => (
        row.station_id === stationId ? { ...row, decision } : row
      )),
    }));
  };

  const approve = async () => {
    const outcome = await run(() => approveReview(review.review_id));
    if (outcome) {
      setDone(true);
      setConfirmOpen(false);
    }
  };

  const reject = async () => {
    const outcome = await run(() => rejectReview(review.review_id), "已退回，未存版本");
    if (!outcome) return;
    setDone(false);
    setConfirmOpen(false);
    setReview(createMockReview());
  };

  if (done) {
    return (
      <div className="twin-opt twin-opt-done">
        {contextHolder}
        <div className="twin-opt-done-card">
          <CheckCircleFilled className="twin-opt-done-icon" />
          <h2>今日已完成最適化參數調整</h2>
        </div>
      </div>
    );
  }

  return (
    <div className="twin-opt">
      {contextHolder}

      <div className="twin-opt-body">
        {error ? <Alert type="error" showIcon title={error} /> : null}

        <div className="twin-opt-meta">
          <div className="twin-opt-kicker">
            <Tag color="green">可套用</Tag>
            <span>{review.review_date}</span>
            <span>回看 {review.lookback_days} 天</span>
          </div>
          <p className="twin-opt-lead">
            {review.reason}
            {` 共 ${review.summary?.total_stations_adjusted ?? 0} 站、平均調幅 ${review.summary?.avg_change_pct ?? 0}%、其中 ${review.summary?.significant_count ?? 0} 站較顯著。`}
          </p>
        </div>

        <div className="twin-opt-cards">
          {changes.map((row) => (
            <StationReviewCard
              key={row.station_id}
              row={row}
              locked={locked}
              busy={busy}
              onDecide={decide}
              onSelect={onSelectStation}
            />
          ))}
        </div>

        <div className="twin-opt-foot">
          <p className="twin-opt-foot-sum">
            將接受 <b>{summary.acceptCount}</b> 站，維持原值 <b>{summary.keepCount}</b> 站。
          </p>
          <Space wrap>
            <Button type="primary" size="large" loading={busy} disabled={locked} onClick={() => setConfirmOpen(true)}>
              核准並套用
            </Button>
            <Button danger size="large" disabled={busy || locked} onClick={reject}>
              退回，不存版本
            </Button>
          </Space>
        </div>
      </div>

      <Modal
        title="確認套用這份建議？"
        open={confirmOpen}
        onCancel={() => !busy && setConfirmOpen(false)}
        onOk={approve}
        okText="確認套用"
        cancelText="再看看"
        confirmLoading={busy}
      >
        <div className="twin-opt-confirm">
          {summary.acceptNames.length ? (
            <p><b>接受：</b>{summary.acceptNames.join("、")}</p>
          ) : (
            <p>沒有站要套用建議，全部維持原值。</p>
          )}
          {summary.keepNames.length ? <p><b>維持原值：</b>{summary.keepNames.join("、")}</p> : null}
          <p className="twin-opt-confirm-note">{review.effective_note}</p>
        </div>
      </Modal>
    </div>
  );
}
