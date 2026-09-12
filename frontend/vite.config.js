import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// 雲端後端固定位址（ADR-312：NLB + Elastic IP，task 重啟不變）。這是預設值：
// 從 GitHub clone 下來、什麼都沒設定，就要直接連得到雲端。
// 本機開發要連地端後端時，才在 frontend/.env 覆蓋 YOUBIKE_BACKEND_URL。
const CLOUD_BACKEND = "http://54.227.205.77:8000";

export default defineConfig(({ mode }) => {
  // ★ 第三個參數 "" = 不限前綴。Vite 只會把 VITE_ 開頭的變數交給前端，
  //   而且「不會」把 .env 的內容寫進 process.env，所以非 VITE_ 前綴的
  //   YOUBIKE_BACKEND_URL 必須用 loadEnv 明確讀取，否則永遠是 undefined。
  const envDir = import.meta.dirname ?? process.cwd();
  const env = loadEnv(mode, envDir, "");

  const target = env.YOUBIKE_BACKEND_URL || process.env.YOUBIKE_BACKEND_URL || CLOUD_BACKEND;
  console.log(`[vite] API proxy → ${target}`);

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": { target, changeOrigin: true } },
    },
  };
});
