import ThemeProvider from "./theme/ThemeProvider.jsx";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell.jsx";
import AlertTrackingPage from "./pages/AlertTrackingPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DriverPage from "./pages/DriverPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import RiderPage from "./pages/RiderPage.jsx";
import TwinPage from "./pages/TwinPage.jsx";


export default function App() {
  return (
    <ThemeProvider>
      <AppShell>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/alerts" element={<AlertTrackingPage />} />
          <Route path="/driver" element={<DriverPage />} />
          <Route path="/optimization" element={<Navigate to="/twin?tab=optimization" replace />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/rider" element={<RiderPage />} />
          <Route path="/twin" element={<TwinPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppShell>
    </ThemeProvider>
  );
}
