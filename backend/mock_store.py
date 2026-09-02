"""
Mock 資料載入器（A0 骨架階段用）
================================
載入 frontend/src/mock/mock_data.json，供所有 API 端點回傳假資料。
A1 完成後，端點會改為呼叫 core/data 取真實資料，這個檔就只留給測試用。
"""

from pathlib import Path
import os
import json

# 預設在專案 frontend/src/mock/；Docker 可用 YOUBIKE_MOCK_PATH 覆寫。
_MOCK_PATH = Path(os.environ.get(
    "YOUBIKE_MOCK_PATH",
    Path(__file__).parent.parent / "frontend" / "src" / "mock" / "mock_data.json",
))

_cache = None


def get_mock() -> dict:
    global _cache
    if _cache is None:
        with open(_MOCK_PATH, "r", encoding="utf-8") as f:
            _cache = json.load(f)
    return _cache
