"""
最簡身分驗證（C-08 骨架）
========================
以 HTTP header `X-Operator-Id` 辨識操作者，對照角色決定能否執行敏感動作。
A0 階段先做骨架（角色對照用記憶體 dict）；A4/A5 接 SQLite operators 表後改為查表。

角色（對應 models_schema/operator.py OperatorRole）：
  operator   外勤調度員 — 只能回報自己的任務
  dispatcher 後台調派員 — 可確認派發、緊急覆寫
  maintainer 維護人員 — 可審核每日最適化、調參
"""

from fastapi import Depends, Header, HTTPException


def get_operator(x_operator_id: str | None = Header(default=None)) -> dict:
    """驗證 X-Operator-Id，回傳 {operator_id, role}。缺或無效（含停用）則 401。

    A5 起改查 SQLite operators 表（原本寫死 3 帳號）。停用帳號 get_role 回 None → 視為無效。
    """
    if not x_operator_id:
        raise HTTPException(status_code=401, detail="缺少或無效的 X-Operator-Id")
    from db.operators_repo import get_role
    role = get_role(x_operator_id)
    if role is None:
        raise HTTPException(status_code=401, detail="缺少或無效的 X-Operator-Id")
    return {"operator_id": x_operator_id, "role": role}


def require_role(*allowed_roles: str):
    """宣告式權限依賴：限定特定角色才能通過。

    用法（寫在端點簽名，無法被遺漏）：
        @router.post("/xxx")
        def handler(operator: dict = Depends(require_role("dispatcher", "maintainer"))):
            ...

    這個依賴內部自己會呼叫 get_operator（先驗身分再驗角色），
    所以端點不用再另外宣告 get_operator，避免「忘記手動呼叫」的破口。
    """
    def checker(operator: dict = Depends(get_operator)) -> dict:
        if operator.get("role") not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"權限不足：需要 {' 或 '.join(allowed_roles)} 角色",
            )
        return operator
    return checker
