import { CheckOutlined, ClockCircleOutlined, CompassOutlined } from "@ant-design/icons";
import {
  Alert,
  Button,
  Card,
  Empty,
  List,
  Progress,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import AsyncState from "../components/common/AsyncState.jsx";
import MetricCard from "../components/common/MetricCard.jsx";
import RouteMap from "../components/operator/RouteMap.jsx";
import TaskQueue from "../components/operator/TaskQueue.jsx";
import useOperatorData from "../hooks/useOperatorData.js";
import { formatNumber, taskStatusLabels } from "../utils/formatters.js";

export default function OperatorPage() {
  const workspace = useOperatorData();
  const [messageApi, contextHolder] = message.useMessage();
  const operator = workspace.data?.operators?.find((item) => item.role === "operator") || workspace.data?.operators?.[0];
  const task = workspace.selectedTask;
  const completedStops = task?.route?.filter((stop) => stop.stop_status === "completed").length || 0;
  const routeLength = task?.route?.length || 0;
  const progress = routeLength ? Math.round((completedStops / routeLength) * 100) : 0;
  const nextPending = task?.route?.find((stop) => stop.stop_status !== "completed");

  const handleComplete = async (sequence) => {
    try {
      await workspace.completeStop(task.task_id, sequence);
      messageApi.success("停靠點已完成（僅保存在本次 Mock 工作階段）");
    } catch (error) {
      messageApi.error(error.message || "更新任務失敗");
    }
  };

  return (
    <AsyncState
      loading={workspace.loading}
      error={workspace.error}
      data={workspace.data}
      onRetry={workspace.reload}
    >
      {workspace.data ? (
        <div className="page-stack">
          {contextHolder}
          <div className="page-heading">
            <div>
              <Typography.Title level={2}>調度員任務台</Typography.Title>
              <Typography.Paragraph>
                依站序完成取車與補車，任務狀態只在本機記憶體更新。
              </Typography.Paragraph>
            </div>
            {operator ? (
              <Space wrap>
                <Tag color="green">{operator.name}</Tag>
                <Tag>{operator.status}</Tag>
                <Tag>{operator.operator_id}</Tag>
              </Space>
            ) : null}
          </div>

          {operator ? (
            <div className="metric-grid metric-grid-four">
              <MetricCard title="今日完成" value={operator.today_stats.completed_tasks} suffix="件" />
              <MetricCard title="移動車輛" value={operator.today_stats.total_bikes_moved} suffix="台" />
              <MetricCard title="工作時間" value={operator.today_stats.total_work_minutes} suffix="分鐘" />
              <MetricCard title="待辦任務" value={operator.task_queue.length} suffix="件" tone="warning" />
            </div>
          ) : null}

          <Alert
            type="warning"
            showIcon
            message="Demo 身分不是正式登入"
            description="此頁以 OP-001 視角展示。正式操作仍須由後端 token 與角色驗證，不能依賴前端頁面或按鈕。"
          />

          <div className="operator-grid">
            <TaskQueue
              tasks={workspace.data.tasks}
              selectedTaskId={workspace.selectedTaskId}
              onSelectTask={workspace.selectTask}
            />

            {task ? (
              <Card
                title="任務執行"
                extra={<Tag color={task.task_status === "completed" ? "green" : "blue"}>{taskStatusLabels[task.task_status] || task.task_status}</Tag>}
              >
                <div className="task-summary">
                  <div>
                    <Typography.Title level={4}>{task.task_id}</Typography.Title>
                    <Space wrap>
                      <Tag icon={<ClockCircleOutlined />}>約 {task.estimated_total_minutes} 分鐘</Tag>
                      <Tag>{task.estimated_distance_km} km</Tag>
                      <Tag>預估油資 NT$ {formatNumber(task.estimated_fuel_cost)}</Tag>
                    </Space>
                  </div>
                  <Progress type="circle" percent={progress} size={84} />
                </div>

                <List
                  className="route-stop-list"
                  dataSource={task.route}
                  renderItem={(stop) => {
                    const completed = stop.stop_status === "completed";
                    const isNext = nextPending?.seq === stop.seq;
                    return (
                      <List.Item
                        actions={[
                          <Button
                            key="complete"
                            type={isNext ? "primary" : "default"}
                            icon={<CheckOutlined />}
                            disabled={completed || !isNext}
                            onClick={() => handleComplete(stop.seq)}
                          >
                            {completed ? "已完成" : "完成此站"}
                          </Button>,
                        ]}
                      >
                        <List.Item.Meta
                          avatar={<span className={completed ? "stop-number complete" : "stop-number"}>{stop.seq}</span>}
                          title={
                            <Space wrap>
                              <Typography.Text strong>{stop.station_name}</Typography.Text>
                              <Tag color={stop.action === "補車" ? "green" : "blue"}>{stop.action} {stop.quantity} 台</Tag>
                            </Space>
                          }
                          description={completed ? "本站作業完成" : isNext ? "下一個停靠點" : "等待前一站完成"}
                        />
                      </List.Item>
                    );
                  }}
                />

                <Button
                  type="link"
                  icon={<CompassOutlined />}
                  href={task.route_map_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  使用 Google Maps 開啟路線
                </Button>
              </Card>
            ) : (
              <Card><Empty description="請選擇任務" /></Card>
            )}
          </div>

          {task ? <RouteMap route={task.route} /> : null}
        </div>
      ) : null}
    </AsyncState>
  );
}
