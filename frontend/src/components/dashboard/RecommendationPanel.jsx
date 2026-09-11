import { AimOutlined, EyeOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Descriptions, InputNumber, List, Modal, Select, Space, Tag, Typography, message } from "antd";
import { useState } from "react";
import { getDispatchResources, previewRecommendation, reportVehicleOnboard } from "../../api/dispatchApi.js";
import { getActorId, isApiMode } from "../../api/httpClient.js";
import { blockingReasonsOf, canConfirm, nextStepFor, onboardBlocking } from "../../utils/dispatchGating.js";
import { formatDateTime, freshnessLabels } from "../../utils/formatters.js";

const vehicleLabel = v => {
  const load = v.onboard_bikes === null || v.onboard_bikes === undefined
    ? "車上未回報" : `車上 ${v.onboard_bikes} 台`;
  return `${v.vehicle_id} · 容量 ${v.max_capacity} · ${load}`;
};

export default function RecommendationPanel({ recommendations, onConfirm, onFocus, embedded = false }) {
  const [selected, setSelected] = useState(null);
  const [draft, setDraft] = useState(null);
  const [resources, setResources] = useState({ operators: [], vehicles: [] });
  const [choices, setChoices] = useState({});
  const [onboard, setOnboard] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [messageApi, contextHolder] = message.useMessage();

  const blocking = blockingReasonsOf(draft);
  const needsOnboard = onboardBlocking(draft);

  const open = async item => {
    setSelected(item); setDraft(isApiMode ? null : item); setChoices({}); setError(""); setOnboard(null);
    if (!isApiMode) return;
    setBusy(true);
    try { setResources(await getDispatchResources()); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const build = async () => {
    setBusy(true); setError(""); setDraft(null);
    try { setDraft(await previewRecommendation(selected, choices)); }
    catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  // ADR-123：就地回報車上台數後重新組單（草稿不可就地修改，一律重新 build）。
  const reportLoad = async () => {
    setBusy(true); setError("");
    try {
      await reportVehicleOnboard(choices.vehicle_id, onboard);
      messageApi.success("已回報車上台數，重新產生預覽");
      setResources(await getDispatchResources());
      setDraft(await previewRecommendation(selected, choices));
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };
  const confirm = async () => {
    setBusy(true); setError("");
    try {
      await onConfirm(draft);
      messageApi.success(isApiMode ? "派工已確認，可至司機頁查看任務" : "Mock 建議已確認");
      setSelected(null); setDraft(null);
    } catch (e) { setError(e.message); }
    finally { setBusy(false); }
  };

  const body = <>
    {contextHolder}
    <List dataSource={recommendations} renderItem={item => <List.Item actions={[
      onFocus && <Button key="focus" size="small" icon={<AimOutlined />} onClick={() => onFocus(item)}>定位</Button>,
      <Button key="preview" size="small" icon={<EyeOutlined />} onClick={() => open(item)}>預覽</Button>,
    ].filter(Boolean)}>
      <List.Item.Meta title={<Space wrap><Typography.Text>{item.station_name}</Typography.Text>
        <Tag>{item.priority_level}</Tag>{item.data_freshness && <Tag>{freshnessLabels[item.data_freshness]}</Tag>}
        {item.prediction_status === "degraded" && <Tag color="orange">預測特徵不完整</Tag>}
        {item.prediction_status === "unavailable" && <Tag color="orange">依現況門檻</Tag>}
      </Space>} description={`${item.action} ${item.quantity} 台｜${item.reason}`} />
    </List.Item>} />
    <Modal title="派工預覽與確認" open={Boolean(selected)} onCancel={() => !busy && setSelected(null)}
      onOk={confirm} okText={isApiMode ? "確認派工" : "確認 Mock"} cancelText="關閉" confirmLoading={busy}
      okButtonProps={{ disabled: isApiMode
        ? (!getActorId() || !canConfirm(draft))
        : !draft }}>
      {error && <Alert type="error" showIcon title={error} />}
      {isApiMode && <Space orientation="vertical" style={{ width: "100%", marginBottom: 16 }}>
        {!getActorId() && <Alert type="warning" title="請先在頁首選擇調度管理身分" />}
        <Select aria-label="執行司機" placeholder="選擇已簽到司機" style={{ width: "100%" }} value={choices.operator_id}
          options={resources.operators.map(o => ({ value: o.operator_id, label: `${o.operator_id} · ${o.name}` }))}
          onChange={id => { setChoices(c => ({ ...c, operator_id: id })); setDraft(null); }} />
        <Select aria-label="調度車輛" placeholder="選擇可用車輛" style={{ width: "100%" }} value={choices.vehicle_id}
          options={resources.vehicles.map(v => ({ value: v.vehicle_id, label: vehicleLabel(v) }))}
          onChange={id => { setChoices(c => ({ ...c, vehicle_id: id })); setDraft(null); setOnboard(null); }} />
        {!busy && !resources.operators.length && <Alert type="info" title="目前沒有可用司機，請由司機先簽到" />}
        <Button onClick={build} loading={busy} disabled={!getActorId() || !choices.operator_id || !choices.vehicle_id}>產生後端預覽</Button>
      </Space>}

      {/* ADR-304：阻擋原因在預覽就顯示，確認鈕同時失效——不讓使用者按了才吃 409 */}
      {isApiMode && draft && blocking.length > 0 && <Alert type="error" showIcon style={{ marginBottom: 12 }}
        title="這張派工單目前無法送出" description={<List size="small" dataSource={blocking}
          renderItem={r => <List.Item><Space orientation="vertical" size={0}>
            <Typography.Text>{r.message}</Typography.Text>
            {nextStepFor(r.code) && <Typography.Text type="secondary">{nextStepFor(r.code)}</Typography.Text>}
          </Space></List.Item>} />} />}

      {/* ADR-123：載量未知／過期可以就地回報後重新組單 */}
      {isApiMode && needsOnboard && <Space wrap style={{ marginBottom: 12 }}>
        <InputNumber aria-label="車上台數" min={0} precision={0} placeholder="車上目前幾台"
          max={resources.vehicles.find(v => v.vehicle_id === choices.vehicle_id)?.max_capacity}
          value={onboard} onChange={setOnboard} />
        <Button type="primary" loading={busy} disabled={!Number.isInteger(onboard)} onClick={reportLoad}>
          回報並重新預覽
        </Button>
      </Space>}

      {draft && (isApiMode ? <>
        {blocking.length === 0 && <Alert type="success" showIcon style={{ marginBottom: 12 }} title="載量、時間與工時檢查皆通過，可以確認派工" />}
        <Descriptions column={1} size="small" bordered>
          <Descriptions.Item label="執行人員／車輛">{draft.assigned_operator}／{draft.assigned_vehicle}</Descriptions.Item>
          <Descriptions.Item label="草稿有效至">{formatDateTime(draft.expires_at)}</Descriptions.Item>
          <Descriptions.Item label="站數／總搬運量">{draft.estimate?.stop_count} 站／{draft.estimate?.total_quantity} 台</Descriptions.Item>
          <Descriptions.Item label="車上台數（出車→收車）">
            {draft.onboard_start ?? "未回報"} → {draft.onboard_end ?? "—"} 台
          </Descriptions.Item>
        </Descriptions>
        <List dataSource={draft.stations}
          renderItem={(s, i) => <List.Item>
            <Space orientation="vertical" size={0}>
              <Typography.Text>
                {i + 1}. {s.station_name || s.station_id} · {s.action} {s.quantity} 台
                {s.target_available !== undefined && s.target_available !== null && ` · 目標 ${s.target_available} 台`}
              </Typography.Text>
              <Typography.Text type="secondary">
                {/* ADR-123：逐站到達時間與該站採用的預測視野，不是整趟共用一個 */}
                {s.arrival_offset_min !== undefined && s.arrival_offset_min !== null
                  && `約 ${Math.round(s.arrival_offset_min)} 分後到達`}
                {s.horizon_used_min ? `｜採用 ${s.horizon_used_min} 分視野預測` : ""}
                {"horizon_used_min" in s && s.horizon_used_min === null ? "｜超出預測視野，不以外推派工" : ""}
                {s.onboard_after !== undefined && s.onboard_after !== null ? `｜完成後車上 ${s.onboard_after} 台` : ""}
                {s.observed_at ? `｜觀測 ${formatDateTime(s.observed_at)}` : ""}
              </Typography.Text>
            </Space>
          </List.Item>} />
      </> : <Descriptions column={1}><Descriptions.Item label="站點">{draft.station_name}</Descriptions.Item>
        <Descriptions.Item label="動作">{draft.action} {draft.quantity} 台</Descriptions.Item></Descriptions>)}
    </Modal>
  </>;
  return embedded ? body : <Card title="調度建議">{body}</Card>;
}
