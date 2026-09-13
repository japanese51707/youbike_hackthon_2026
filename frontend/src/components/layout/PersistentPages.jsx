import { createContext, useContext, useRef } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";

const PageActiveContext = createContext(true);

export function usePageActive() {
  return useContext(PageActiveContext);
}

const PAGE_ROUTES = [
  { path: "/dashboard" },
  { path: "/alerts" },
  { path: "/alert-tracking" },
  { path: "/driver" },
  { path: "/overview" },
  { path: "/rider" },
  { path: "/twin" },
];

const PAGE_PATHS = new Set(PAGE_ROUTES.map((item) => item.path));

export default function PersistentPages({ pages }) {
  const location = useLocation();
  const visitedRef = useRef(new Set());
  const path = location.pathname;
  if (PAGE_PATHS.has(path)) visitedRef.current.add(path);

  return (
    <div className="persistent-pages">
      {PAGE_ROUTES.map(({ path: pagePath }) => {
        if (!visitedRef.current.has(pagePath)) return null;
        const active = path === pagePath;
        return (
          <PageActiveContext.Provider key={pagePath} value={active}>
            <div className="persistent-page" hidden={!active} data-page={pagePath}>
              {pages[pagePath]}
            </div>
          </PageActiveContext.Provider>
        );
      })}
      <Routes>
        <Route path="/optimization" element={<Navigate to="/twin?tab=optimization" replace />} />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route
          path="*"
          element={PAGE_PATHS.has(path) ? null : <Navigate to="/dashboard" replace />}
        />
      </Routes>
    </div>
  );
}
