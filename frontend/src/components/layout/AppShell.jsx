import {
  BarChartOutlined,
  CarOutlined,
  DashboardOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Space, Tag, Typography, message } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { resetDemoData } from "../../api/operationsApi.js";

const navigation = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "調度面板" },
  { key: "/operator", icon: <CarOutlined />, label: "司機面板" },
  { key: "/overview", icon: <BarChartOutlined />, label: "長官導覽面板" },
];

export default function AppShell({ children }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [messageApi, contextHolder] = message.useMessage();

  const handleReset = async () => {
    await resetDemoData();
    messageApi.success("Mock 資料已重置");
    window.location.reload();
  };

  return (
    <Layout className="app-shell">
      {contextHolder}
      <header className="topbar">
        <Space className="brand" size={10}>
          <span className="brand-mark">Ub</span>
          <div>
            <Typography.Title level={4}>YouBike 智慧調度</Typography.Title>
            <Typography.Text>決策支援展示介面</Typography.Text>
          </div>
        </Space>
        <Menu
          className="main-menu"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={navigation}
          onClick={({ key }) => navigate(key)}
        />
        <Space className="demo-actions">
          <Tag color="gold">MOCK DEMO</Tag>
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={handleReset}
          >
            重置
          </Button>
        </Space>
      </header>
      <div className="mock-notice">
        展示資料來自本機 Mock，不代表真實即時站況；前端操作不會寫入後端或資料庫。
      </div>
      <Layout.Content className="page-content">{children}</Layout.Content>
    </Layout>
  );
}
