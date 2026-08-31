# YouBike 資料分析平台 — AWS 使用說明

## 一、用了哪些 AWS 資源？分別做什麼用？

| 資源 | 做什麼用的 | 有開伺服器嗎？ | 收費方式 |
|------|-----------|--------------|---------|
| **S3（Simple Storage Service）** | 存放你的 Parquet 資料檔案，就像雲端硬碟 | ❌ 沒有伺服器 | 按儲存量計費（每 GB $0.023/月） |
| **Glue Data Catalog** | 幫你的資料建「目錄」，讓 Athena 知道資料長什麼樣 | ❌ 沒有伺服器 | 免費（前 100 萬物件） |
| **Athena** | 讓你用 SQL 查詢 S3 上的資料 | ❌ 沒有伺服器 | 按查詢掃描量計費（每 TB $5） |

### 🔑 重點：沒有任何伺服器！

這三個服務都是 **Serverless（無伺服器）架構**：
- **不會有「開著就一直收錢」的問題**
- 沒有在用的時候 = 不花錢（Athena）或幾乎不花錢（S3 儲存費）
- 不需要關機、不需要停止 instance
- 跟 EC2 或 RDS 那種「開著就燒錢」的完全不同

---

## 二、費用估算

### 你的資料量
- Parquet 大小：**~105 MB**
- 分成 6 個月份分區

### 每月固定費用（資料只是放著）

| 項目 | 計算 | 費用 |
|------|------|------|
| S3 儲存 | 105 MB × $0.023/GB | **$0.002/月**（不到 1 角台幣） |
| Glue Catalog | 1 個 table | **免費** |
| Athena（沒查詢時） | — | **$0** |

→ **資料放著不查，每月 < NT$ 0.1**

### 查詢費用

| 查詢方式 | 每次掃描量 | 費用/次 | 10,000 次總費用 |
|----------|-----------|---------|----------------|
| 全表掃描（不指定月份） | ~105 MB | $0.000525 | **$5.25**（NT$ 168） |
| 指定單月（用分區） | ~12-23 MB | $0.0001 | **$1**（NT$ 32） |
| 指定月份 + 只取少數欄位 | ~5-10 MB | $0.00005 | **$0.50**（NT$ 16） |

> ⚠️ Athena 最低計費 10 MB/次，就算你只查 1 筆也算 10 MB

### Free Tier（新帳號前 12 個月）
- S3：5 GB 免費儲存 → 你的 105 MB 完全在免費額度內 ✅
- S3 請求：每月 20,000 GET 免費 ✅
- Glue：100 萬物件免費 ✅
- Athena：**沒有 Free Tier**，但費用極低

**結論：研發期間整體花費預估 NT$ 30~100 之間（視查詢次數而定）**

---

## 三、在哪裡看資料？怎麼查詢和篩選？

### 方法 1：AWS Athena Console（推薦，最方便）

1. 登入 AWS Console：https://console.aws.amazon.com/
2. 搜尋欄打 **「Athena」** → 進入 Athena 服務
3. 左邊選擇 Database：**`youbike_db`**
4. 你會看到 Table：**`station_status`**
5. 直接在查詢編輯器寫 SQL

#### 常用查詢範例：

```sql
-- 看前 100 筆資料（快速確認）
SELECT * FROM youbike_db.station_status
WHERE year_month = '2026-03'
LIMIT 100;

-- 查各行政區空站/滿站次數
SELECT 行政區,
       SUM(是否空站) as 空站次數,
       SUM(是否滿站) as 滿站次數,
       ROUND(AVG(空位率), 2) as 平均空位率
FROM youbike_db.station_status
WHERE year_month = '2026-03'
GROUP BY 行政區
ORDER BY 空站次數 DESC;

-- 找出最常滿站的 Top 20 站點
SELECT 場站名稱, 行政區,
       COUNT(*) as 總紀錄數,
       SUM(是否滿站) as 滿站次數,
       ROUND(SUM(是否滿站) * 100.0 / COUNT(*), 2) as 滿站比例
FROM youbike_db.station_status
GROUP BY 場站名稱, 行政區
ORDER BY 滿站次數 DESC
LIMIT 20;

-- 分析尖峰時段（用小時拆解）
SELECT SUBSTR(日期, 12, 2) as 小時,
       ROUND(AVG(借用率), 2) as 平均借用率,
       SUM(是否空站) as 空站次數
FROM youbike_db.station_status
WHERE year_month = '2026-01'
GROUP BY SUBSTR(日期, 12, 2)
ORDER BY 小時;

-- 特定站點的歷史趨勢
SELECT 日期, 可借車數, 可還位數, 空位率
FROM youbike_db.station_status
WHERE 場站名稱 = '三井Outlet'
  AND year_month = '2026-01'
ORDER BY 日期;
```

#### 篩選方式：
- **按月份篩選**：`WHERE year_month = '2026-03'`（這會利用分區，省錢又快）
- **按行政區篩選**：`WHERE 行政區 = '板橋區'`
- **按站點篩選**：`WHERE 場站名稱 LIKE '%捷運%'`
- **按時間篩選**：`WHERE 日期 BETWEEN '2026-03-01' AND '2026-03-07'`
- **找空站**：`WHERE 是否空站 = 1`
- **找滿站**：`WHERE 是否滿站 = 1`

### 方法 2：從程式直接查（Python）

```python
import boto3
import pandas as pd

# 用 boto3 透過 Athena 查詢
client = boto3.client('athena', region_name='ap-northeast-1')

query = """
SELECT 行政區, AVG(空位率) as avg_空位率
FROM youbike_db.station_status
WHERE year_month = '2026-03'
GROUP BY 行政區
"""

response = client.start_query_execution(
    QueryString=query,
    ResultConfiguration={'OutputLocation': 's3://你的bucket/athena-results/'}
)
# 查詢是非同步的，需要等幾秒再取結果
```

### 方法 3：本地快速查看

合併後的 CSV 在 `output/youbike_all.csv`，可以用：
- Excel / Google Sheets 打開（但 1,300 萬筆可能會卡）
- Python pandas 直接讀 Parquet 更快：

```python
import pandas as pd

# 讀取特定月份（超快）
df = pd.read_parquet('output/youbike_parquet/year_month=2026-03/data.parquet')
print(df.head())
```

---

## 四、如何關閉資源（不再花錢）

### 快速關閉（一鍵）

```bash
python teardown_aws.py --bucket youbike-hackathon-2026
```

輸入 `yes` 確認後，會自動：
1. 刪除 Glue Table
2. 刪除 Glue Database
3. 清空並刪除 S3 Bucket

**刪除後 = 零費用，完全不會再收錢。**

### 手動關閉（如果腳本有問題）

1. **S3**：Console → S3 → 找到你的 bucket → 「清空」→「刪除」
2. **Glue**：Console → Glue → Databases → 刪除 `youbike_db`
3. **Athena**：不需要特別關，它本身不存資料

### 暫停但不刪除

如果你只是暫時不用，但之後還要用：
- **什麼都不用做**！S3 放著每月只有 $0.002，幾乎等於免費
- Athena 不查就不收錢
- 等你要用的時候直接開 Athena 查就好

---

## 五、部署步驟（第一次使用）

### 前置準備

1. 註冊 AWS 帳號（如果還沒有）：https://aws.amazon.com/
2. 安裝 AWS CLI：
   ```bash
   brew install awscli
   ```
3. 設定 credentials：
   ```bash
   aws configure
   # 輸入 Access Key ID、Secret Key、Region (ap-northeast-1)
   ```

### 部署

```bash
# 1. 整合資料（已完成）
python merge_csv_to_parquet.py

# 2. 部署到 AWS
python setup_aws.py --bucket 你的bucket名稱 --region ap-northeast-1
```

### 轉移到黑客松會場環境

```bash
# 切換到會場帳號
export AWS_PROFILE=hackathon
# 或用 aws configure --profile hackathon 設定

# 重新部署（腳本會自動建 bucket、上傳、建表）
python setup_aws.py --bucket 會場bucket名稱 --region ap-northeast-1 --profile hackathon
```

---

## 六、資料欄位說明

| 欄位 | 型態 | 說明 |
|------|------|------|
| 日期 | string | 資料時間（YYYY-MM-DD HH:MM:SS） |
| 城市 | string | 新北市 |
| 行政區 | string | 29 個行政區 |
| 場站名稱 | string | YouBike 場站名稱（共 1,583 站） |
| 總車柱數 | int | 該站總車位數 |
| 可借車數 | int | 目前可借車輛數 |
| 可還位數 | int | 目前可停空位數 |
| 經度 | double | 站點經度（WGS84） |
| 緯度 | double | 站點緯度（WGS84） |
| 空位率 | double | 可還位數 ÷ 總車柱數 × 100 |
| 借用率 | double | 可借車數 ÷ 總車柱數 × 100 |
| 是否空站 | int | 可借車數 = 0 時為 1（無車可借） |
| 是否滿站 | int | 可還位數 = 0 時為 1（無位可還） |
| year_month | string | 分區鍵（YYYY-MM），用於篩選省錢 |

---

## 七、檔案清單

```
新北市黑客松_20260912/
├── youbike資料集/              ← 原始 CSV（可留可刪）
├── output/
│   ├── youbike_all.csv         ← 合併後的完整 CSV（本地檢視用）
│   └── youbike_parquet/        ← 分區 Parquet（上傳到 AWS 用）
│       ├── year_month=2026-01/
│       ├── year_month=2026-02/
│       ├── year_month=2026-03/
│       ├── year_month=2026-04/
│       ├── year_month=2026-05/
│       └── year_month=2026-06/
├── merge_csv_to_parquet.py     ← 資料整合腳本
├── setup_aws.py                ← AWS 部署腳本
├── teardown_aws.py             ← AWS 資源關閉腳本
└── AWS使用說明.md              ← 本文件
```

---

## 八、省錢小撇步

1. **查詢時一定要加 `WHERE year_month = 'YYYY-MM'`** — 這會讓 Athena 只掃描該月份的資料，省 80% 費用
2. **只 SELECT 你需要的欄位** — 不要 `SELECT *`，指定欄位可以進一步減少掃描量
3. **Parquet 格式已經幫你省了 13.5 倍** — 比起直接放 CSV，費用少了 93%
4. **研發期把查詢結果存起來** — 避免重複跑同樣的查詢
5. **不用的時候不需要關** — Serverless 架構，不查就不收錢
