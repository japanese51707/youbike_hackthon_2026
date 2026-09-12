"""
pytest 共用設定與 fixture
==========================
- 把 backend/ 加進 sys.path，讓測試能 import main / core / api / db
- 測試一律用記憶體 SQLite（不碰真實 youbike.db）
- 每個測試前重置所有記憶體單例 + 重建乾淨 DB（含預設帳號），確保隔離
- 提供 client fixture（TestClient）
"""

import os
import sys
from pathlib import Path

import pytest

# backend/ 根目錄（conftest 在 backend/tests/）
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# 測試用記憶體 DB（須在任何 db import 前設定）
os.environ["YOUBIKE_DB_PATH"] = ":memory:"
# 測試時把 bcrypt cost 調到最低（4），只加速運算、不影響雜湊正確性；正式維持 12
os.environ["BCRYPT_ROUNDS"] = "4"


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    """每個測試前後重置單例 + 重建乾淨記憶體 DB（含 3 預設帳號），確保隔離。"""
    from core.audit import reset_audit_service
    from core.override_service import reset_override_service
    from core.task_manager import reset_task_manager
    from core.alert_service import reset_alert_service
    from core.data.data_source import reset_data_source
    from db.connection import reset_memory_db, init_db
    from db.operators_repo import seed_default_operators
    from core.dispatch_drafts import reset_drafts
    from api.optimization import reset_reviews
    from core import interfaces, dispatcher, rule_engine
    from core.assistant.service import reset_assistant_limits
    from core.rider_faults import reset_rider_faults
    from config_loader import get_config

    # 測試一律用 mock 資料源，與 config.yaml 的正式 mode 解耦：
    # config.yaml 可設成 youbike_official（正式接真實 API），但測試不打外部 API、
    # 用可控 mock 站況驗證派工/確認/生命週期邏輯。就地覆寫記憶體中的 mode，
    # 不動設定檔；monkeypatch 於測試結束自動還原。
    _cfg = get_config()
    monkeypatch.setitem(_cfg.setdefault("data_source", {}), "mode", "mock")

    # 後端契約／派工測試不驗證模型準確度；隔離外部 S3 歷史讀取。
    monkeypatch.setattr(interfaces, "get_predictor", interfaces.MockPredictor)
    monkeypatch.setattr(dispatcher, "get_predictor", interfaces.MockPredictor)
    if hasattr(rule_engine, "get_predictor"):
        monkeypatch.setattr(rule_engine, "get_predictor", interfaces.MockPredictor)

    def _reset_all():
        if "main" in sys.modules:
            sys.modules["main"].app.middleware_stack = None  # 各測試獨立限流計數
        reset_audit_service()
        reset_override_service()
        reset_task_manager()
        reset_alert_service()
        reset_data_source()
        reset_drafts()
        reset_reviews()
        reset_assistant_limits()
        reset_rider_faults()
        from core.auto_dispatch import reset_runtime_enabled
        reset_runtime_enabled()    # ADR-320：清掉自動配單 runtime 開關，測試間隔離
        reset_memory_db()          # 丟掉舊記憶體 DB
        init_db()                  # 重建空 schema
        seed_default_operators()   # 種入 3 預設帳號（auth 查表用）

    _reset_all()

    # ADR-123：車上載量未知的車不可確認派工。測試環境的慣例是「開班前已回報車上半載」——
    # 任何在測試中建立的車，建立後立刻補一筆 manual_report(容量一半)，代表已完成回報，
    # 讓純補車與純取車的既有情境都有可用的載量與空間。
    # 這是測試夾具的約定，不是正式程式的預設：
    #   - 要驗證「未知載量擋確認」的測試會自行呼叫 vehicles_repo.clear_onboard()。
    #   - 要驗證特定載量邊界的測試會自行 report_onboard() 覆寫。
    from db import vehicles_repo as _vr
    _real_create = _vr.create_vehicle

    def _create_and_report(vehicle_id, *args, **kwargs):
        created = _real_create(vehicle_id, *args, **kwargs)
        vehicle = _vr.get_vehicle(vehicle_id) or created
        _vr.report_onboard(vehicle_id, int(vehicle["max_capacity"]) // 2, "manual_report")
        return _vr.get_vehicle(vehicle_id) or created

    monkeypatch.setattr(_vr, "create_vehicle", _create_and_report)

    yield
    _reset_all()


@pytest.fixture
def client():
    """FastAPI TestClient。"""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


# 測試帳號（對齊 seed_default_operators）
OP_OPERATOR = {"X-Operator-Id": "OP-001"}    # operator
OP_DISPATCHER = {"X-Operator-Id": "OP-002"}  # dispatcher
OP_MAINTAINER = {"X-Operator-Id": "OP-003"}  # maintainer


def put_drivers_on_duty():
    """測試情境明確設定已值勤；正式 seed 不自動把未上班人員視為可用。"""
    from db.connection import get_connection
    conn = get_connection()
    conn.execute("UPDATE operators SET status = 'on_duty' WHERE role_type IN ('driver', 'depot_standby')")
    conn.commit()
