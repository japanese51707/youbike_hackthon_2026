import { AimOutlined, CheckCircleOutlined, EyeOutlined } from "@ant-design/icons";
import {
  Button,
  Card,
  Descriptions,
  List,
  Modal,
  Space,
  Tag,
  Typography,
  message,
} from "antd";
import { useState } from "react";

const priorityColors = { high: "red", medium: "orange", low: "blue" };

export default function RecommendationPanel({
  recommendations,
  onConfirm,
  onFocus,
  embedded = false,
}) {
  const [preview, setPreview] = useState(null);
  const [confirming, setConfirming] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();

  const handleConfirm = async () => {
    if (!preview) return;
    setConfirming(true);
    try {
      await onConfirm(preview.recommendation_id);
      messageApi.success("已在本次 Mock 工作階段確認建議");
      setPreview(null);
    } catch (error) {
      messageApi.error(error.message || "確認失敗");
    } finally {
      setConfirming(false);
    }
  };

  const body = (
    <>
      {contextHolder}
      <List
        dataSource={recommendations}
        renderItem={(item) => (
          <List.Item
            actions={[
              onFocus ? (
                <Button
                  key="focus"
                  size="small"
                  type="text"
                  icon={<AimOutlined />}
                  onClick={() => onFocus(item)}
                >
                  定位
                </Button>
              ) : null,
              <Button
                key="preview"
                size="small"
                icon={<EyeOutlined />}
                onClick={() => setPreview(item)}
              >
                預覽
              </Button>,
            ].filter(Boolean)}
          >
            <List.Item.Meta
              title={
                <Space wrap>
                  <Typography.Text>{item.station_name}</Typography.Text>
                  <Tag color={priorityColors[item.priority_level]}>{item.priority_level}</Tag>
                  {item.demo_status === "confirmed" ? (
                    <Tag color="green" icon={<CheckCircleOutlined />}>已確認</Tag>
                  ) : null}
                </Space>
              }
              description={`${item.action} ${item.quantity} 台｜${item.reason}`}
            />
          </List.Item>
        )}
      />
      <Modal
        title="確認調度建議"
        open={Boolean(preview)}
        onCancel={() => setPreview(null)}
        onOk={handleConfirm}
        okText="確認（僅 Mock）"
        cancelText="返回"
        confirmLoading={confirming}
        okButtonProps={{ disabled: preview?.demo_status === "confirmed" }}
      >
        {preview ? (
          <Descriptions bordered column={1} size="small">
            <Descriptions.Item label="站點">{preview.station_name}</Descriptions.Item>
            <Descriptions.Item label="動作">{preview.action} {preview.quantity} 台</Descriptions.Item>
            <Descriptions.Item label="目前可借">{preview.current_available} 台</Descriptions.Item>
            <Descriptions.Item label="到達時預測">{preview.predicted_at_arrival} 台</Descriptions.Item>
            <Descriptions.Item label="原因">{preview.reason}</Descriptions.Item>
          </Descriptions>
        ) : null}
      </Modal>
    </>
  );

  if (embedded) return body;
  return (
    <Card title="調度建議" extra={<Tag>{recommendations.length} 筆</Tag>}>
      {body}
    </Card>
  );
}
