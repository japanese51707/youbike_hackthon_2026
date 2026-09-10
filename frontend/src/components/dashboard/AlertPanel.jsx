import { CheckOutlined } from "@ant-design/icons";
import { Button, Card, List, Space, Tag, Typography, message } from "antd";
import { formatDateTime } from "../../utils/formatters.js";

const levelColors = { critical: "red", warning: "orange", info: "blue" };

export default function AlertPanel({ alerts, onAcknowledge, embedded = false }) {
  const [messageApi, contextHolder] = message.useMessage();

  const handleAcknowledge = async (alertId) => {
    try {
      await onAcknowledge(alertId);
      messageApi.success("警示已確認（僅 Mock）");
    } catch (error) {
      messageApi.error(error.message || "警示確認失敗");
    }
  };

  const body = (
    <>
      {contextHolder}
      <List
        dataSource={alerts}
        renderItem={(item) => (
          <List.Item
            actions={[
              <Button
                key="ack"
                size="small"
                icon={<CheckOutlined />}
                disabled={item.acknowledged}
                onClick={() => handleAcknowledge(item.alert_id)}
              >
                {item.acknowledged ? "已確認" : "確認"}
              </Button>,
            ]}
          >
            <List.Item.Meta
              title={
                <Space wrap>
                  <Tag color={levelColors[item.level]}>{item.level}</Tag>
                  <Typography.Text>{item.station_name}</Typography.Text>
                </Space>
              }
              description={`${item.message}｜${formatDateTime(item.triggered_at)}`}
            />
          </List.Item>
        )}
      />
    </>
  );

  if (embedded) return body;
  return (
    <Card title="即時警示" extra={<Tag color="red">{alerts.filter((item) => !item.acknowledged).length} 未確認</Tag>}>
      {body}
    </Card>
  );
}
