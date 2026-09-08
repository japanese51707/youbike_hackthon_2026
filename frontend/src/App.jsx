import { ConfigProvider, theme as antdTheme } from "antd";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DriverPage from "./pages/DriverPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";

// 數位孿生戰情室深色主題（ADR-204）：Slate 深藍灰底 + 亮綠主色 + 系統等寬字體。
const theme = {
  algorithm: antdTheme.darkAlgorithm,
  token: {
    colorPrimary: "#38d9a9",
    colorInfo: "#38d9a9",
    colorBgBase: "#0B0F19",
    colorBgContainer: "#111a2b",
    colorBgElevated: "#152037",
    colorBorder: "#243149",
    borderRadius: 10,
    fontFamily: '"Noto Sans TC", "Microsoft JhengHei", Inter, sans-serif',
    fontFamilyCode:
      'ui-monospace, SFMono-Regular, "JetBrains Mono", Menlo, Consolas, monospace',
  },
};

export default function App() {
  return (
    <ConfigProvider theme={theme}>
      <AppShell>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/driver" element={<DriverPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppShell>
    </ConfigProvider>
  );
}
