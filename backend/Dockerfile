# YouBike 後端（FastAPI）
FROM python:3.12-slim

WORKDIR /app

# 先裝依賴（利用 layer 快取）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 複製後端程式碼
COPY . .

EXPOSE 8000

# config.yaml 在專案根目錄，容器內掛載到 /app 上層（見 docker-compose）
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
