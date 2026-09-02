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
def _reset_state():
    """每個測試前後重置單例 + 重建乾淨記憶體 DB（含 3 預設帳號），確保隔離。"""
    from core.audit import reset_audit_service
    from core.override_service import reset_override_service
    from core.task_manager import reset_task_manager
    from core.alert_service import reset_alert_service
    from core.data.data_source import reset_data_source
    from db.connection import reset_memory_db, init_db
    from db.operators_repo import seed_default_operators

    def _reset_all():
        reset_audit_service()
        reset_override_service()
        reset_task_manager()
        reset_alert_service()
        reset_data_source()
        reset_memory_db()          # 丟掉舊記憶體 DB
        init_db()                  # 重建空 schema
        seed_default_operators()   # 種入 3 預設帳號（auth 查表用）

    _reset_all()
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
