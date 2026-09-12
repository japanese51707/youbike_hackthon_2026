-- YouBike 智慧調度系統 — SQLite Schema（A5，對齊 design §8 七張表）
-- 黑客松規模：一個檔案就是資料庫，免安裝伺服器。
-- 只放「需要持久 + 需要查詢」的狀態資料；即時站況(熱)在記憶體、歷史(溫)在 S3 Parquet。

-- 1. 調度員（含帳號：password_hash 存 bcrypt，絕不存原文）
CREATE TABLE IF NOT EXISTS operators (
    operator_id           TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    role                  TEXT NOT NULL,            -- operator / dispatcher / maintainer
    password_hash         TEXT,                     -- bcrypt 雜湊；NULL=尚未設定密碼
    status                TEXT DEFAULT 'off_duty',  -- on_duty/busy/resting/off_duty
    is_active             INTEGER DEFAULT 1,        -- 1=啟用 0=停用（停用取代刪除，保留稽核關聯）
    current_lat           REAL,
    current_lng           REAL,
    current_task_id       TEXT,
    current_district      TEXT,                     -- ADR-114 動態：當前被指派作業的行政區（隨任務變動，非綁定責任區）
    role_type             TEXT,                     -- ADR-116 營運角色：driver/stationed/controller（與登入 role 正交）
    stationed_at          TEXT,                     -- ADR-116 駐點人員駐守站（僅 stationed；driver/controller 為 NULL）
    task_queue_json       TEXT DEFAULT '[]',
    today_completed_tasks INTEGER DEFAULT 0,
    today_bikes_moved     INTEGER DEFAULT 0,
    today_work_minutes    INTEGER DEFAULT 0,        -- fatigue 判斷用，重啟不歸零
    on_duty_since         TEXT,
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

-- 2. 調度任務
CREATE TABLE IF NOT EXISTS tasks (
    task_id                     TEXT PRIMARY KEY,
    task_type                   TEXT NOT NULL,       -- normal / emergency
    task_status                 TEXT NOT NULL DEFAULT 'pending',
    assigned_operator           TEXT,                -- 司機（主責，維持既有單人全鏈路）
    assigned_escort             TEXT,                -- ADR-308 隨車人員（可選，第二名）；NULL=只派一名
    route_json                  TEXT DEFAULT '[]',
    estimated_travel_minutes    INTEGER,
    estimated_work_minutes      INTEGER,
    estimated_total_minutes     INTEGER,
    estimated_distance_km       REAL,
    estimated_fuel_cost         REAL,
    route_map_url               TEXT,
    source_override_station_id  TEXT,                -- 由哪個③覆寫產生（覆寫到期連動取消依據）
    onboard_start               INTEGER,             -- ADR-123 出車時車上台數（確認當下算定）
    onboard_planned_end         INTEGER,             -- ADR-123 依載量計畫預估的收車載量
    district                    TEXT,                -- ADR-114 這趟任務的行政區（一趟不跨區的約束落地）
    assigned_vehicle            TEXT,                -- ADR-114 指派的調度車（vehicle_id）
    cancel_reason               TEXT,
    cancelled_by                TEXT,
    assigned_at                 TEXT,
    created_at                  TEXT NOT NULL,
    updated_at                  TEXT NOT NULL
);

-- 3. 稽核留痕（append-only，不 UPDATE/DELETE）
CREATE TABLE IF NOT EXISTS audit_logs (
    log_id                TEXT PRIMARY KEY,
    type                  TEXT NOT NULL,             -- emergency_override/task_transfer/optimization/param_edit/task_report
    station_id            TEXT,
    operator              TEXT NOT NULL,
    action                TEXT NOT NULL,
    reason                TEXT,
    timestamp             TEXT NOT NULL,
    expired_at            TEXT,
    task_duration_minutes INTEGER
);

-- 4. 站點參數 + 版本（主鍵 station_id+version，保留所有版本供回溯 FR-7 ②）
CREATE TABLE IF NOT EXISTS station_params (
    station_id       TEXT NOT NULL,
    version          TEXT NOT NULL,                  -- 版本（時間戳）
    params_json      TEXT NOT NULL,
    param_source     TEXT NOT NULL,                  -- base / ai_optimized（③覆寫不寫參數，不在此列）
    override_active  INTEGER DEFAULT 0,              -- 1=該站目前有生效中的③覆寫（狀態，非參數來源）
    conditions_json  TEXT DEFAULT '[]',
    reason           TEXT,
    created_at       TEXT NOT NULL,
    is_active        INTEGER DEFAULT 0,              -- 1=當前生效版本
    PRIMARY KEY (station_id, version)
);

-- 5. 警示狀態（acknowledged 重啟後保留，避免已讀變未讀）
CREATE TABLE IF NOT EXISTS alerts (
    alert_id          TEXT PRIMARY KEY,
    level             TEXT NOT NULL,                 -- info/warning/critical
    station_id        TEXT,
    station_name      TEXT,
    district          TEXT,
    message           TEXT NOT NULL,
    suggested_action  TEXT,
    triggered_at      TEXT NOT NULL,
    acknowledged      INTEGER DEFAULT 0
);

-- 6. 機關 webhook 訂閱（出向資安：callback 須通過 SSRF 檢查才存入）
CREATE TABLE IF NOT EXISTS alert_subscriptions (
    subscription_id  TEXT PRIMARY KEY,
    callback_url     TEXT NOT NULL,
    levels           TEXT DEFAULT '[]',
    districts        TEXT DEFAULT '[]',
    token            TEXT
);

-- 7. 活動事件
CREATE TABLE IF NOT EXISTS events (
    event_id                TEXT PRIMARY KEY,
    event_name              TEXT NOT NULL,
    lat                     REAL,
    lng                     REAL,
    expected_attendance     INTEGER,
    event_type              TEXT,
    start_time              TEXT,
    end_time                TEXT,
    dispatch_requested      INTEGER DEFAULT 0,
    influence_radius_km     REAL,
    affected_stations_json  TEXT DEFAULT '[]'
);

-- 8. 調度車主檔（ADR-114：可增刪改，未來由 YouBike 車隊 API 覆蓋 seed）
--    載運量逐台可不同、可改（車種差異）；current_district 為動態狀態（隨任務指派變動，非綁定責任區）。
CREATE TABLE IF NOT EXISTS vehicles (
    vehicle_id        TEXT PRIMARY KEY,
    max_capacity      INTEGER NOT NULL DEFAULT 15,   -- 最高載運量(台)；預設 15，依車種可改
    status            TEXT DEFAULT 'available',      -- available/dispatched/maintenance/off_duty
    current_district  TEXT,                          -- 動態：當前作業行政區（隨任務指派變動）
    current_task_id   TEXT,                          -- 當前任務
    is_active         INTEGER DEFAULT 1,             -- 1=啟用 0=停用（停用取代刪除，保留稽核關聯）
    is_depot          INTEGER DEFAULT 0,             -- ADR-119 總站待命車（1=總站待命，可調派各區支援）
    onboard_bikes       INTEGER,                   -- ADR-123 車上現有台數；NULL=未知（不得當成 0）
    onboard_source      TEXT,                      -- ADR-123 載量來源：manual_report/task_completion/fleet_api
    onboard_observed_at TEXT,                      -- ADR-123 載量觀測時間（過期即不可用）
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL
);

-- 索引（常用查詢加速）
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(task_status);
CREATE INDEX IF NOT EXISTS idx_tasks_operator ON tasks(assigned_operator);
CREATE INDEX IF NOT EXISTS idx_tasks_override ON tasks(source_override_station_id);
CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_logs(type);
CREATE INDEX IF NOT EXISTS idx_audit_station ON audit_logs(station_id);
CREATE INDEX IF NOT EXISTS idx_params_active ON station_params(station_id, is_active);
CREATE INDEX IF NOT EXISTS idx_alerts_ack ON alerts(acknowledged);
CREATE INDEX IF NOT EXISTS idx_vehicles_status ON vehicles(status);
CREATE INDEX IF NOT EXISTS idx_vehicles_district ON vehicles(current_district);

-- ADR-302：只有確認後才保存收據，草稿本身仍在記憶體。
CREATE TABLE IF NOT EXISTS dispatch_confirmations (
    draft_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);
