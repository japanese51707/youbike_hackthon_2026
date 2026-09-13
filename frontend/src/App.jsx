import ThemeProvider from "./theme/ThemeProvider.jsx";
import AppShell from "./components/layout/AppShell.jsx";
import PersistentPages from "./components/layout/PersistentPages.jsx";
import AlertTrackingPage from "./pages/AlertTrackingPage.jsx";
import DispatchStatusPage from "./pages/DispatchStatusPage.jsx";
import DashboardPage from "./pages/DashboardPage.jsx";
import DriverPage from "./pages/DriverPage.jsx";
import OverviewPage from "./pages/OverviewPage.jsx";
import RiderPage from "./pages/RiderPage.jsx";
import TwinPage from "./pages/TwinPage.jsx";

const pages = {
  "/dashboard": <DashboardPage />,
  "/alerts": <DispatchStatusPage />,
  "/alert-tracking": <AlertTrackingPage />,
  "/driver": <DriverPage />,
  "/overview": <OverviewPage />,
  "/rider": <RiderPage />,
  "/twin": <TwinPage />,
};

export default function App() {
  return (
    <ThemeProvider>
      <AppShell>
        <PersistentPages pages={pages} />
      </AppShell>
    </ThemeProvider>
  );
}
