import {
  ProfileOutlined,
  BarChartOutlined,
  DashboardOutlined,
  DeploymentUnitOutlined,
  EnvironmentOutlined,
  MobileOutlined,
  ReloadOutlined,
} from "@ant-design/icons";
import { Button, Layout, Menu, Select, Space, Tag, Typography, message } from "antd";
import { useLocation, useNavigate } from "react-router-dom";
import { resetDemoData } from "../../api/operationsApi.js";

import { useEffect, useState } from "react";
import { isApiMode, request, getActorId, setActorId } from "../../api/httpClient.js";

import EscalationBanner from "../alerts/EscalationBanner.jsx";
import EscalationModal from "../alerts/EscalationModal.jsx";
import useEscalations from "../../hooks/useEscalations.js";

import AppearanceControl from "./AppearanceControl.jsx";
import ApiSyncButton from "./ApiSyncButton.jsx";
import brandLogo from "../../assets/brand/youbike-logo.png";

// 警示追蹤放在調度面板旁邊：它是調度員與管理後台共用的那份真相（ADR-309）。
const baseNavigation = [
  { key: "/dashboard", icon: <DashboardOutlined />, label: "調度面板" },
  { key: "/alerts", icon: <ProfileOutlined />, label: "分派任務狀況" },
  { key: "/driver", icon: <MobileOutlined />, label: "司機手機端" },
  { key: "/overview", icon: <BarChartOutlined />, label: "服務水準看板" },
  { key: "/rider", icon: <EnvironmentOutlined />, label: "找車（使用者）" },
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
  // ADR-309：升級提示跨頁常駐——調度員切到別頁也不會漏掉該打電話的案件。
  const escalation = useEscalations();
  const [dismissedCaseId, setDismissedCaseId] = useState(null);
  const promptCase = escalation.promptCase;
  // ★彈窗會蓋住整頁（含頁首的身分選單），所以只在「這個人真的能處理」時才強制跳出：
  //   沒選身分 → 選不了身分，變成跳出來但什麼都不能做；
  //   身分是司機 → 送出會被後端擋（需要 dispatcher/maintainer），跳了也只是卡住他。
  //   這兩種情況都只出橫幅，橫幅會說明原因。
  const actorId = isApiMode ? getActorId() : "";
  const actorRole = operators.find((o) => o.operator_id === actorId)?.role;
  const canAct = !isApiMode || (Boolean(actorId) && ["dispatcher", "maintainer"].includes(actorRole));
  const showPrompt = Boolean(promptCase) && promptCase.case_id !== dismissedCaseId && canAct;

  // escalation 的提示改走全域橫幅/彈窗（下方 EscalationBanner/Modal），不再掛在導覽項上。
  const navigation = baseNavigation;

  const goHandle = (item) => {
    setDismissedCaseId(null);
    navigate(`/dashboard?station=${encodeURIComponent(item.station_id)}`);
  };

  const handleReset = async () => {
    await resetDemoData();
    messageApi.success("Mock 資料已重置");
    window.location.reload();
  };

  return (
    <Layout className="app-shell">
      {contextHolder}
      {escalation.bannerCases.length ? (
        <EscalationBanner cases={escalation.bannerCases} onOpen={goHandle}
          hint={canAct ? "" : (actorId ? "此身分無派工權限，請切換為調度或維運人員" : "請先於右上角選擇操作身分")} />
      ) : null}
      <EscalationModal
        open={showPrompt}
        item={promptCase}
        onDispatch={goHandle}
        onDone={() => { setDismissedCaseId(promptCase?.case_id ?? null); escalation.reload(); }}
      />
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
          <ApiSyncButton />
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
        {isApiMode
          ? location.pathname === "/rider"
            ? "此頁給騎乘者找附近可借／可還站，不派工。站點等級目前依站名推估，與實際調度會有誤差。"
            : location.pathname === "/twin"
            ? "此頁只做空間解讀與最適化審核，不派工。請依資料來源、新鮮度與右側結論邊界判讀。"
            : "操作會寫入後端。請依資料來源與觀測時間判讀；此處的身分選擇僅供受控展示。"
          : "此頁為本機 Mock 示範，不代表即時站況；操作僅影響展示資料。"}
      </div>
      <Layout.Content className="page-content">{children}</Layout.Content>
    </Layout>
  );
}
