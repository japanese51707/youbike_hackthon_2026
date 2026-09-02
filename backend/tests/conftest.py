"""
pytest 共用設定與 fixture
==========================
- 把 backend/ 加進 sys.path，讓測試能 import main / core / api
- 每個測試前重置所有記憶體單例，確保測試互不干擾（隔離）
- 提供 client fixture（TestClient）
"""

import sys
from pathlib import Path

import pytest

# backend/ 根目錄（conftest 在 backend/tests/）
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def _reset_singletons():
    """每個測試前後重置所有模組級單例，避免狀態外溢到別的測試。"""
    from core.audit import reset_audit_service
    from core.override_service import reset_override_service
    from core.task_manager import reset_task_manager
    from core.alert_service import reset_alert_service
    from core.data.data_source import reset_data_source

    def _reset_all():
        reset_audit_service()
        reset_override_service()
        reset_task_manager()
        reset_alert_service()
        reset_data_source()

    _reset_all()
    yield
    _reset_all()


@pytest.fixture
def client():
    """FastAPI TestClient。"""
    from fastapi.testclient import TestClient
    from main import app
    return TestClient(app)


# 測試帳號（對齊 auth.py）
OP_OPERATOR = {"X-Operator-Id": "OP-001"}    # operator
OP_DISPATCHER = {"X-Operator-Id": "OP-002"}  # dispatcher
OP_MAINTAINER = {"X-Operator-Id": "OP-003"}  # maintainer
