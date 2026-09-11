import { Alert, Button, Card, List, Space, Statistic, Tag, Typography } from "antd";
import { request } from "../api/httpClient.js";
import useAsyncResource from "../hooks/useAsyncResource.js";
import AsyncState from "../components/common/AsyncState.jsx";

async function loadOverview() {
  const [overview, kpi, source] = await Promise.all([request("/dispatch/overview"), request("/kpi"), request("/data/status")]);
  return { ...overview, kpi, source };
}
const labels = { assigned: "已指派", in_progress: "執行中", completed: "已完成", cancelled: "已取消", manual_required: "待人工處理" };
export default function BackendOverviewPage() {
  const resource = useAsyncResource(loadOverview);
  const data = resource.data;
  return <div style={{ height: "100%", overflowY: "auto", padding: 20 }}>
    <Space><Typography.Title level={2}>營運總覽</Typography.Title><Button onClick={() => resource.reload().catch(() => {})}>重新整理</Button></Space>
    <AsyncState {...resource} onRetry={resource.reload}>
      {data && <Space orientation="vertical" style={{ width: "100%" }}>
        <Alert type="info" title={`站況來源：${data.kpi.source}；任務統計來自後端，包含目前保留的所有任務。`} />
        <Space wrap>
          <Card><Statistic title="營運中站點" value={data.kpi.in_service_stations} /></Card>
          <Card><Statistic title="空站／滿站" value={`${data.kpi.empty_stations}／${data.kpi.full_stations}`} /></Card>
          {Object.entries(data.task_counts).map(([key, count]) => <Card key={key}><Statistic title={labels[key]} value={count} /></Card>)}
        </Space>
        <Card title="派工紀錄"><List dataSource={data.tasks} renderItem={task => <List.Item>
          <List.Item.Meta title={`${task.district || "跨區"} · ${task.assigned_operator || "—"} · ${task.assigned_vehicle || "—"}`}
            description={`${task.task_id} · ${(task.route || []).length} 站`} />
          <Tag>{labels[task.task_status] || task.task_status}</Tag>
        </List.Item>} /></Card>
        <Alert type="info" title="模擬成效尚未接入實際評估資料，此頁不顯示估計節省金額或改善百分比。" />
      </Space>}
    </AsyncState>
  </div>;
}
