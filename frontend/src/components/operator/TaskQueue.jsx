import { Card, List, Progress, Space, Tag, Typography } from "antd";
import { taskStatusLabels } from "../../utils/formatters.js";

function taskProgress(task) {
  const route = task.route || [];
  if (!route.length) return 0;
  const complete = route.filter((stop) => stop.stop_status === "completed").length;
  return Math.round((complete / route.length) * 100);
}

export default function TaskQueue({ tasks, selectedTaskId, onSelectTask }) {
  return (
    <Card title="今日任務佇列" extra={<Tag>{tasks.length} 件</Tag>}>
      <List
        dataSource={tasks}
        locale={{ emptyText: "目前沒有任務" }}
        renderItem={(task) => (
          <List.Item
            className={task.task_id === selectedTaskId ? "task-item active" : "task-item"}
            onClick={() => onSelectTask(task.task_id)}
          >
            <List.Item.Meta
              title={
                <Space wrap>
                  <Typography.Text strong>{task.task_id}</Typography.Text>
                  <Tag color={task.task_type === "emergency" ? "red" : "blue"}>{task.task_type}</Tag>
                  <Tag>{taskStatusLabels[task.task_status] || task.task_status}</Tag>
                </Space>
              }
              description={
                <div>
                  <Typography.Text type="secondary">
                    {task.route?.length || 0} 站｜約 {task.estimated_total_minutes} 分鐘
                  </Typography.Text>
                  <Progress percent={taskProgress(task)} size="small" />
                </div>
              }
            />
          </List.Item>
        )}
      />
    </Card>
  );
}
