import { ConfigProvider } from "antd";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import OperatorPage from "./pages/OperatorPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";

const theme = {
  token: {
    colorPrimary: "#087f5b",
    colorInfo: "#087f5b",
    borderRadius: 10,
    fontFamily: 'Inter, "Noto Sans TC", "Microsoft JhengHei", sans-serif',
  },
};

export default function App() {
  return (
    <ConfigProvider theme={theme}>
      <AppShell>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/operator" element={<OperatorPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppShell>
    </ConfigProvider>
  );
}
