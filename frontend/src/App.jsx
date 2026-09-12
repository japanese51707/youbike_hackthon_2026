import ThemeProvider from "./theme/ThemeProvider.jsx";
import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./components/layout/AppShell.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DriverPage from "./pages/DriverPage.jsx";
import OptimizationReviewPage from "./pages/OptimizationReviewPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import TwinPage from "./pages/TwinPage.jsx";


export default function App() {
  return (
    <ThemeProvider>
      <AppShell>
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/driver" element={<DriverPage />} />
          <Route path="/optimization" element={<OptimizationReviewPage />} />
          <Route path="/overview" element={<OverviewPage />} />
          <Route path="/twin" element={<TwinPage />} />
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AppShell>
    </ThemeProvider>
  );
}
