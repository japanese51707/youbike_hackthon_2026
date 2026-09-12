#!/usr/bin/env bash
# YouBike 智慧調度系統 — 一鍵啟動前端（連雲端後端）
# ============================================================
# 從 GitHub clone 下來後，在專案根目錄執行：  ./start.sh
# 會自動：複製前端環境設定 → 安裝相依 → 啟動 dev server。
# 前端預設連「雲端 ECS 後端」（含即時資料/天氣/Bedrock 顧問，走 IAM 免金鑰），
# 使用者不需要準備任何 AWS 或 API 金鑰。
#
# 只想連本機後端開發時：先自行把 frontend/.env 的 YOUBIKE_BACKEND_URL 改成 http://127.0.0.1:8000。

set -euo pipefail

# 切到腳本所在目錄（專案根），不依賴呼叫者的當前路徑
cd "$(dirname "$0")"

FRONTEND_DIR="frontend"

if [ ! -d "$FRONTEND_DIR" ]; then
  echo "✗ 找不到 $FRONTEND_DIR 目錄，請在專案根目錄執行 ./start.sh"
  exit 1
fi

echo "[1/3] 準備前端環境設定 (frontend/.env)…"
if [ -f "$FRONTEND_DIR/.env" ]; then
  echo "      已存在 frontend/.env，保留現有設定（不覆寫）。"
else
  cp "$FRONTEND_DIR/.env.example" "$FRONTEND_DIR/.env"
  echo "      已從 .env.example 建立 frontend/.env（預設連雲端後端）。"
fi

echo "[2/3] 安裝前端相依 (npm install)…"
( cd "$FRONTEND_DIR" && npm install )

echo "[3/3] 啟動前端 dev server (npm run dev)…"
echo "      瀏覽器開啟 http://localhost:5173"
( cd "$FRONTEND_DIR" && npm run dev )
