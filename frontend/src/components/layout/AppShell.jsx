import {
  BarChartOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  MobileOutlined,
  ReloadOutlined,
  SlidersOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Select, Space, Tag, Typography, message } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { resetDemoData } from "../../api/operationsApi.js";

import { useEffect, useState } from "react";
import { isApiMode, request, getActorId, setActorId } from "../../api/httpClient.js";

import AppearanceControl from "./AppearanceControl.jsx";
import brandLogo from "../../assets/brand/youbike-logo.png";

const navigation = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "調度面板" },
  { key: "/driver", icon: <MobileOutlined />, label: "司機手機端" },
  { key: "/optimization", icon: <SlidersOutlined />, label: "最適化審核" },
  { key: "/overview", icon: <BarChartOutlined />, label: "長官導覽面板" },
  { key: "/twin", icon: <DeploymentUnitOutlined />, label: "數位孿生戰情室" },
];

export default function AppShell({ children }) {
  const [operators, setOperators] = useState([]);
  const [operatorError, setOperatorError] = useState("");
  useEffect(() => {
    if (isApiMode) request("/operators").then(setOperators).catch(error => setOperatorError(error.message));
  }, []);
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
          <span className="brand-logo"><img src={brandLogo} alt="YouBike" width="92" height="54" /></span>
          <div>
            <Typography.Title level={4}>智慧調度</Typography.Title>
            <Typography.Text>新北市・讓每一站，剛剛好</Typography.Text>
          </div>
        </Space>
        <Menu
          className="main-menu"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={navigation}
          onClick={({ key }) => navigate(key)}
        />
        <div className="header-tools">
          <AppearanceControl />
          <Space className="demo-actions">
          <Tag color={isApiMode ? "cyan" : "gold"}>{isApiMode ? "後端連線 · 受控 Demo" : "MOCK DEMO"}</Tag>
          {isApiMode && <Select showSearch optionFilterProp="label" aria-label="操作身分"
            placeholder={operatorError || "選擇操作身分"} value={getActorId() || undefined} style={{ width: 185 }}
            options={operators.map(o => ({ value: o.operator_id, label: `${o.operator_id} · ${o.name} (${o.role})` }))}
            onChange={id => { setActorId(id); window.location.reload(); }} />}
          <Button
            type="text"
            icon={<ReloadOutlined />}
            onClick={isApiMode ? () => window.location.reload() : handleReset}
          >
            {isApiMode ? "重新整理" : "重置"}
          </Button>
        </Space>
        </div>
      </header>
      <div className="mock-notice">
        {isApiMode && location.pathname !== "/twin"
          ? "操作會寫入後端。請依資料來源與觀測時間判讀；此處的身分選擇僅供受控展示。"
          : "此頁為本機 Mock 示範，不代表即時站況；操作僅影響展示資料。"}
      </div>
      <Layout.Content className="page-content">{children}</Layout.Content>
    </Layout>
  );
}
