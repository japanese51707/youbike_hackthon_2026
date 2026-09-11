import { Alert, Button, Card, Empty, Input, InputNumber, Modal, Space, Tag, Typography, message } from "antd";
import { useState } from "react";
import useAsyncResource from "../hooks/useAsyncResource.js";
import { getAssignedWorkspace, reportStop, reportVehicleLoad, returnTask, setDuty, startTask } from "../api/taskApi.js";
import AsyncState from "../components/common/AsyncState.jsx";

export default function BackendDriverPage() {
  const resource = useAsyncResource(getAssignedWorkspace);
  const [counts, setCounts] = useState({});
  const [loads, setLoads] = useState({});
  const [busy, setBusy] = useState(false);
  const [returning, setReturning] = useState(null);
  const [reason, setReason] = useState("");
  const [messageApi, contextHolder] = message.useMessage();
  const run = async action => {
    setBusy(true);
    try { await action(); await resource.reload(); messageApi.success("狀態已更新"); return true; }
    catch (error) { messageApi.error(error.message); return false; }
    finally { setBusy(false); }
  };
  const operator = resource.data?.operator;
  const active = (resource.data?.tasks || []).filter(t => ["assigned", "in_progress"].includes(t.task_status) && !t.resources_released);
  return <div style={{ height: "100%", overflowY: "auto", padding: 16, maxWidth: 650, margin: "0 auto" }}>
    {contextHolder}
    <Typography.Title level={2}>司機工作台</Typography.Title>
    <AsyncState {...resource} onRetry={resource.reload}>
      {!operator ? <Alert type="info" title="請在頁首先選擇司機身分" /> : <Space orientation="vertical" style={{ width: "100%" }}>
        <Card size="small" title={`${operator.operator_id} · ${operator.name}`} extra={<Tag>{operator.status}</Tag>}>
          <Space wrap>
            <Button loading={busy} disabled={active.length > 0 || !["driver", "depot_standby"].includes(operator.role_type)}
              onClick={() => run(() => setDuty(operator.status === "off_duty" ? "on_duty" : "off_duty"))}>
              {operator.status === "off_duty" ? "簽到值勤" : "下班"}
            </Button>
            <Button disabled={busy} onClick={() => resource.reload().catch(() => {})}>更新任務</Button>
          </Space>
        </Card>
        {!active.length && <Empty description="目前沒有指派給你的待執行任務" />}
        {active.map(task => <Card key={task.task_id} title={`${task.district || "跨區"} · ${task.assigned_vehicle || "—"}`}
          extra={<Tag>{task.task_status === "assigned" ? "待開始" : "執行中"}</Tag>}>
          <Space wrap style={{ marginBottom: 12 }}>
            {task.task_status === "assigned" && <Button type="primary" loading={busy} onClick={() => run(() => startTask(task.task_id))}>開始任務</Button>}
            <Button danger disabled={busy} onClick={() => { setReturning(task.task_id); setReason(""); }}>退回任務</Button>
          </Space>
          {/* ADR-123：車上台數。出車時後端已算定，實際不同時由司機更正；結案會自動推算寫回。 */}
          {task.assigned_vehicle && <Space wrap style={{ marginBottom: 12 }}>
            <Typography.Text type="secondary">
              出車時車上 {task.onboard_start ?? "未回報"} 台{task.onboard_planned_end !== null
                && task.onboard_planned_end !== undefined ? `，預計收車剩 ${task.onboard_planned_end} 台` : ""}
            </Typography.Text>
            <InputNumber aria-label={`車上台數 ${task.assigned_vehicle}`} min={0} precision={0}
              placeholder="更正車上台數" value={loads[task.task_id] ?? null}
              onChange={value => setLoads(l => ({ ...l, [task.task_id]: value }))} />
            <Button size="small" loading={busy} disabled={!Number.isInteger(loads[task.task_id])}
              onClick={() => run(() => reportVehicleLoad(task.assigned_vehicle, loads[task.task_id]))}>
              回報車上台數
            </Button>
          </Space>}
          {(task.route || []).map((stop, index) => {
            const key = `${task.task_id}:${stop.station_id}`;
            const pending = (stop.station_status || "pending") === "pending";
            return <Card key={key} size="small" style={{ marginBottom: 12 }} title={`${index + 1}. ${stop.station_name || stop.station_id}`}>
              <p>{stop.action} · 目標站內存量 {stop.target_available ?? "—"} 台</p>
              {pending ? <Space wrap>
                <InputNumber aria-label={`現場存量 ${stop.station_id}`} min={0} max={stop.total_docks ?? undefined} precision={0}
                  placeholder="現場實際存量" value={counts[key] ?? null}
                  onChange={value => setCounts(c => ({ ...c, [key]: value }))} />
                <Button loading={busy} disabled={task.task_status !== "in_progress" || !Number.isInteger(counts[key])}
                  onClick={() => run(() => reportStop(task.task_id, stop.station_id, counts[key]))}>回報完成</Button>
              </Space> : <Tag color="green">{stop.station_status === "completed" ? `已回報：${stop.actual_available} 台` : "已移除"}</Tag>}
            </Card>;
          })}
        </Card>)}
      </Space>}
    </AsyncState>
    <Modal title="退回任務" open={Boolean(returning)} confirmLoading={busy} onCancel={() => !busy && setReturning(null)}
      okButtonProps={{ disabled: !reason.trim() }} onOk={async () => {
        if (await run(() => returnTask(returning, reason.trim()))) setReturning(null);
      }}>
      <Alert type="warning" title="執行中的任務退回後，需要管理者人工處理" />
      <Input.TextArea aria-label="退回原因" value={reason} onChange={e => setReason(e.target.value)} placeholder="請說明退回原因" />
    </Modal>
  </div>;
}
