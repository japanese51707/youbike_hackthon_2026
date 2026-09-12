import { ConfigProvider, theme as antdTheme } from "antd";
import { createContext, useContext, useEffect, useLayoutEffect, useMemo, useState } from "react";
import { palettes, resolveAppearance, THEME_STORAGE_KEY, validAppearance } from "./palettes.js";

const ThemeContext = createContext(null);
function readPreference() {
  try { return validAppearance(localStorage.getItem(THEME_STORAGE_KEY)); }
  catch { return "system"; }
}
export function useAppearance() { return useContext(ThemeContext); }

// 只儲存外觀偏好。切換不重建頁面，保留篩選、抽屜與派工草稿。
export default function ThemeProvider({ children }) {
  const [preference, setPreference] = useState(readPreference);
  const [systemDark, setSystemDark] = useState(() => window.matchMedia("(prefers-color-scheme: dark)").matches);
  const [storageError, setStorageError] = useState(false);
  const mode = resolveAppearance(preference, systemDark);
  const colors = palettes[mode];
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event) => setSystemDark(event.matches);
    const onStorage = (event) => {
      if (event.key === THEME_STORAGE_KEY || event.key === null) setPreference(readPreference());
    };
    query.addEventListener("change", onChange);
    window.addEventListener("storage", onStorage);
    return () => { query.removeEventListener("change", onChange); window.removeEventListener("storage", onStorage); };
  }, []);
  useLayoutEffect(() => {
    const el = document.documentElement;
    el.dataset.theme = mode;
    el.style.colorScheme = mode;
    for (const [key, value] of Object.entries(colors)) {
      if (typeof value === "string") el.style.setProperty(`--ct-${key.replace(/[A-Z]/g, c => `-${c.toLowerCase()}`)}`, value);
    }
    el.style.setProperty("--ct-text-dim", colors.muted);
    el.style.setProperty("--ct-panel-2", colors.panel2);
  }, [mode, colors]);
  const changePreference = (value) => {
    const next = validAppearance(value);
    setPreference(next);
    try { localStorage.setItem(THEME_STORAGE_KEY, next); setStorageError(false); }
    catch { setStorageError(true); }
  };
  const theme = useMemo(() => ({
    algorithm: mode === "dark" ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
    token: {
      colorPrimary: colors.accent, colorInfo: colors.info, colorSuccess: colors.success,
      colorWarning: colors.warning, colorError: colors.danger,
      colorBgBase: colors.bg, colorBgContainer: colors.panel, colorBgElevated: colors.panel,
      colorBorder: colors.border, colorBorderSecondary: colors.border,
      colorText: colors.text, colorTextSecondary: colors.muted,
      colorLink: colors.primary, colorLinkHover: colors.primary,
      borderRadius: 12, fontSize: 13, controlHeight: 34,
      fontFamily: '"PingFang TC", "Hiragino Sans", "Noto Sans TC", "Microsoft JhengHei", sans-serif',
      fontFamilyCode: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
    },
    components: {
      Button: { primaryColor: colors.onAccent, primaryShadow: "none", fontWeight: 600 },
      Menu: { itemColor: colors.muted, itemSelectedColor: colors.primary, horizontalItemSelectedColor: colors.primary, itemSelectedBg: colors.primarySoft },
      Segmented: { trackBg: colors.bgSoft, itemSelectedBg: colors.panel, itemColor: colors.muted, itemSelectedColor: colors.text },
      Card: { headerFontSize: 14 },
      Tabs: { itemSelectedColor: colors.primary, itemHoverColor: colors.primary, inkBarColor: colors.accent },
    },
  }), [mode, colors]);
  return <ThemeContext.Provider value={{ mode, preference, setPreference: changePreference, colors, storageError }}>
    <ConfigProvider theme={theme}>{children}</ConfigProvider>
  </ThemeContext.Provider>;
}
