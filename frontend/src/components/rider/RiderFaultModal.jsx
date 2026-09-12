import { Button, Input, InputNumber, Modal, Radio, Select, Typography, message } from "antd";
import { useEffect, useMemo, useState } from "react";
import { submitFaultReport } from "../../api/riderFaultApi.js";
import {
  FAULT_ISSUE_OPTIONS,
  clampFaultQuantity,
  emptyFaultSummary,
  formatFaultSummary,
  needsFaultQuantity,
  previewFaultAdd,
} from "../../utils/riderFaultReports.js";

export default function RiderFaultModal({ open, stations = [], defaultStationId, summaries = {}, onClose, onSubmitted }) {
  const [step, setStep] = useState("form");
  const [stationId, setStationId] = useState(null);
  const [issue, setIssue] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);

  const options = useMemo(
    () =>
      (stations || [])
        .filter((row) => row?.station_id)
        .map((row) => ({
          value: row.station_id,
          label: row.station_name || row.station_id,
        })),
    [stations],
  );
  const issueMeta = FAULT_ISSUE_OPTIONS.find((row) => row.value === issue);
  const showQuantity = needsFaultQuantity(issue);
  const current = summaries[stationId] || emptyFaultSummary(stationId);
  const preview = issue ? previewFaultAdd(current, issue, quantity) : null;
  const alreadyReported = Boolean(formatFaultSummary(current));

  useEffect(() => {
    if (!open) return;
    setStep("form");
    setIssue(null);
    setQuantity(1);
    setNote("");
    setStationId(defaultStationId && options.some((row) => row.value === defaultStationId) ? defaultStationId : options[0]?.value ?? null);
  }, [open, defaultStationId, options]);

  const askConfirm = () => {
    if (!stationId || !issue) {
      message.warning("請選站點和狀況");
      return;
    }
    if (showQuantity && !quantity) {
      message.warning("請填本次新增數量");
      return;
    }
    setStep("confirm");
  };

  const submit = async () => {
    const station = stations.find((row) => row.station_id === stationId);
    setSending(true);
    try {
      await submitFaultReport({
        stationId,
        stationName: station?.station_name || stationId,
        issue,
        addQuantity: showQuantity ? clampFaultQuantity(quantity) : 1,
        note: note.trim() || null,
      });
      message.success("已送出通報（不會派工）");
      onSubmitted?.();
      onClose?.();
    } catch (err) {
      message.error(err.message || "通報送出失敗");
    } finally {
      setSending(false);
    }
  };

  return (
    <Modal
      title="通報故障"
      open={open}
      onCancel={onClose}
      destroyOnClose
      footer={
        step === "confirm"
          ? [
              <Button key="back" onClick={() => setStep("form")}>
                返回修改
              </Button>,
              <Button key="ok" type="primary" loading={sending} onClick={submit}>
                確認送出
              </Button>,
            ]
          : [
              <Button key="cancel" onClick={onClose}>
                取消
              </Button>,
              <Button key="next" type="primary" disabled={!stationId || !issue} onClick={askConfirm}>
                下一步確認
              </Button>,
            ]
      }
    >
      {step === "form" ? (
        <div className="rider-fault-form">
          <label>
            哪一站
            <Select
              showSearch
              optionFilterProp="label"
              value={stationId}
              options={options}
              onChange={setStationId}
              placeholder="選擇站點"
            />
          </label>
          {alreadyReported ? (
            <div className="rider-fault-known">{formatFaultSummary(current)}。若是同一批車或柱，請不要再送。</div>
          ) : (
            <Typography.Text type="secondary">本站目前還沒有故障通報。</Typography.Text>
          )}
          <label>
            發生什麼
            <Radio.Group className="rider-fault-issues" value={issue} onChange={(event) => setIssue(event.target.value)}>
              {FAULT_ISSUE_OPTIONS.map((row) => (
                <Radio.Button key={row.value} value={row.value}>
                  {row.label}
                </Radio.Button>
              ))}
            </Radio.Group>
          </label>
          {showQuantity ? (
            <label>
              本次新增{issue === "bike" ? "壞車" : "壞柱"}
              <InputNumber min={1} max={10} value={quantity} onChange={setQuantity} />
            </label>
          ) : null}
          <label>
            補充說明（選填）
            <Input
              value={note}
              maxLength={40}
              placeholder="例如車號後四碼、第幾根柱"
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <Typography.Text type="secondary">不用留姓名電話。送出前會再確認本次新增與合計。不會派工。</Typography.Text>
        </div>
      ) : (
        <div className="rider-fault-confirm">
          <p>請確認這兩個數字無誤再送出。若你看到的是已經被通報的車或柱，請返回取消。</p>
          <dl>
            <div>
              <dt>本次新增</dt>
              <dd>
                {showQuantity ? `${preview.add} ${issueMeta?.unit}` : issueMeta?.label}
              </dd>
            </div>
            <div>
              <dt>本站目前已通報</dt>
              <dd>{formatFaultSummary(current) || "尚無通報"}</dd>
            </div>
            <div>
              <dt>送出後合計</dt>
              <dd>{formatFaultSummary(preview.next)}</dd>
            </div>
          </dl>
        </div>
      )}
    </Modal>
  );
}
