"""派工領域錯誤；API 统一映射，不把核心邏輯綁定 FastAPI。"""


class DispatchConflict(ValueError):
    """狀態、版本或資源衝突，需要重新取得預覽。"""


class DispatchForbidden(PermissionError):
    """身分存在但無權操作該任務／草稿。"""
