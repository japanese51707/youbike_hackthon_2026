# YouBike 後端（FastAPI）— 雲端自包含版（ADR-307 ECS Fargate 部署）
# 注意：build context 為「專案根目錄」，才能把根目錄的 config.yaml 一起打包。
#   docker build -f backend/Dockerfile -t <image> .   （在專案根執行）
FROM python:3.12-slim

WORKDIR /app

# LightGBM Linux wheels require the OpenMP runtime.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 先裝依賴（利用 layer 快取）
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端程式碼（放到 /app）
COPY backend/ /app/

# 複製專案根的 config.yaml 到 /app（容器內自包含，不靠掛載）。
# config_loader 預設找 backend 上一層；雲端用 YOUBIKE_CONFIG_PATH 明確指向此檔。
COPY config.yaml /app/config.yaml
ENV YOUBIKE_CONFIG_PATH=/app/config.yaml

# 人力分派分析結果（ADR-308/312）：seed_workforce_allocation 啟動時讀，讓雲端也能
# 依「行政區×班別」預設分派人力。路徑對齊 operators_repo._ALLOC_PATH（parents[2]/docs/analysis）。
COPY docs/analysis/workforce_allocation.json /docs/analysis/workforce_allocation.json

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
