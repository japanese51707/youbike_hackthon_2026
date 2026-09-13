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
    shift                 TEXT,                     -- ADR-312 排班班別：morning/evening/night（人力分三班，班內對應行政區）
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

-- 5b. 緊急調度案件與稽核軌跡（ADR-309）
--     案件的 opened_at 不隨警示重建而改變，這是「已經沒人管幾分鐘」的唯一依據。
CREATE TABLE IF NOT EXISTS alert_cases (
    case_id           TEXT PRIMARY KEY,
    station_id        TEXT NOT NULL,
    station_name      TEXT,
    district          TEXT,
    opened_at         TEXT NOT NULL,        -- 升級時鐘的起點，開案後不再變動
    trigger_reason    TEXT,
    suggested_action  TEXT,
    highest_stage     INTEGER DEFAULT 0,    -- 曾達到的最高階段（稽核用）
    muted_until       TEXT,                 -- 已讀/已聯絡的靜音到期；不關案、不重置時鐘
    closed_at         TEXT,
    close_reason      TEXT                  -- dispatched（已派工）/ recovered（站況恢復）
);

-- 同一站同時間只能有一個未結案案件（兩個分頁同時開案是真的會發生）
CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_cases_open
    ON alert_cases(station_id) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_alert_cases_opened ON alert_cases(opened_at);

CREATE TABLE IF NOT EXISTS alert_case_actions (
    action_id   TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,
    action      TEXT NOT NULL,              -- acknowledged / called / deferred / dispatch
    actor       TEXT NOT NULL,
    stage       INTEGER DEFAULT 0,
    note        TEXT,
    contact     TEXT,
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_case_actions_case ON alert_case_actions(case_id);

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

-- 5c. 空／滿站緊急時計（ADR-324）
--     與 alert_cases 分開：派工不關案，站況離開空／滿才算排除。
CREATE TABLE IF NOT EXISTS service_problems (
    problem_id    TEXT PRIMARY KEY,
    station_id    TEXT NOT NULL,
    station_name  TEXT,
    district      TEXT,
    kind          TEXT NOT NULL,        -- empty / full
    opened_at     TEXT NOT NULL,        -- 時計起點，開案後不再變動
    closed_at     TEXT,
    close_reason  TEXT                  -- recovered / kind_changed
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_service_problems_open
    ON service_problems(station_id) WHERE closed_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_service_problems_closed
    ON service_problems(closed_at);
CREATE INDEX IF NOT EXISTS idx_service_problems_district
    ON service_problems(district, closed_at);

-- ADR-328：近 24 小時站況快照（背景收集；與時計同庫）
CREATE TABLE IF NOT EXISTS station_snapshots (
    observed_at      TEXT NOT NULL,
    station_id       TEXT NOT NULL,
    station_name     TEXT,
    district         TEXT,
    status           TEXT,
    available_bikes  INTEGER,
    available_docks  INTEGER,
    total_docks      INTEGER,
    PRIMARY KEY (observed_at, station_id)
);
CREATE INDEX IF NOT EXISTS idx_station_snapshots_station
    ON station_snapshots(station_id, observed_at);
CREATE INDEX IF NOT EXISTS idx_station_snapshots_observed
    ON station_snapshots(observed_at);

-- ADR-302：只有確認後才保存收據，草稿本身仍在記憶體。
CREATE TABLE IF NOT EXISTS dispatch_confirmations (
    draft_id TEXT PRIMARY KEY,
    version INTEGER NOT NULL,
    fingerprint TEXT NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(task_id),
    confirmed_by TEXT NOT NULL,
    confirmed_at TEXT NOT NULL
);

-- ADR-330：任務單當日當班流水號計數器（產生 20260911-早001 這類人類可讀編號）。
-- 鍵 = 日期(YYYYMMDD) + 班別代碼(早/晚/夜)；seq 每產一張單原子 +1，跨日跨班各自從 1 起算。
CREATE TABLE IF NOT EXISTS task_seq (
    seq_key TEXT PRIMARY KEY,     -- 例：20260911-早
    seq     INTEGER NOT NULL      -- 目前已用到的最大流水號
);

-- ADR-335：分級催辦的站內通知。每「事件×階段×收件人×承辦版本×提醒批次」一筆，
-- 唯一鍵擋掉重複送；建立／取走／看到／已讀四件事分開記，不混成一個 bool。
CREATE TABLE IF NOT EXISTS alert_notifications (
    notification_id    TEXT PRIMARY KEY,
    case_id            TEXT NOT NULL,
    stage              INTEGER NOT NULL,
    recipient_id       TEXT NOT NULL,
    recipient_role     TEXT NOT NULL DEFAULT 'controller',
    task_id            TEXT,
    assignment_version TEXT NOT NULL DEFAULT '',   -- 轉派後新承辦收得到自己那份
    reminder_index     INTEGER NOT NULL DEFAULT 0, -- 最高階段後的第幾次持續提醒
    digest_key         TEXT,                       -- 同區同階段合併時的分組鍵
    body               TEXT,
    created_at         TEXT NOT NULL,
    delivered_at       TEXT,                       -- 前端取走（不等於送達手機）
    seen_at            TEXT,
    acknowledged_at    TEXT,
    muted_until        TEXT                        -- 個人靜音；不遮清單、不擋下一階段
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_alert_notifications_unique
    ON alert_notifications(case_id, stage, recipient_id, assignment_version, reminder_index);
CREATE INDEX IF NOT EXISTS idx_alert_notifications_recipient
    ON alert_notifications(recipient_id, created_at);
