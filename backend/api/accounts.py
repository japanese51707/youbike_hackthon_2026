"""
帳號管理端點（A5）
==================
- 登入：公開端點，比對 bcrypt
- 建立/停用帳號：需 maintainer 權限（不開放自助註冊——政府系統不該讓人自行註冊調度員）
- 建立/停用都記稽核（誰建了誰、誰停用誰）

安全備註：
  - 密碼經 bcrypt 雜湊存 DB，端點回傳一律不含 password_hash
  - 登入失敗回統一訊息，不透露「是帳號不存在還是密碼錯」（避免帳號枚舉）
"""

from fastapi import APIRouter, Depends, HTTPException

from auth import require_role
from db import operators_repo as repo
from core.audit import get_audit_service
from models_schema.account import CreateAccountRequest, LoginRequest

router = APIRouter(prefix="/api/v1", tags=["accounts"])


@router.post("/auth/login")
def login(body: LoginRequest):
    """登入驗證（公開）。成功回帳號基本資料（不含密碼雜湊），失敗 401。"""
    op = repo.verify_login(body.operator_id, body.password)
    if op is None:
        # 統一訊息，不區分帳號不存在/密碼錯（防帳號枚舉）
        raise HTTPException(status_code=401, detail="帳號或密碼錯誤")
    return {"message": "登入成功", "operator": op}


@router.post("/accounts")
def create_account(
    body: CreateAccountRequest,
    operator: dict = Depends(require_role("maintainer")),
):
    """建立帳號（需 maintainer）。密碼 bcrypt 雜湊後存，記稽核。"""
    try:
        created = repo.create_operator(
            body.operator_id, body.name, body.role, body.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    get_audit_service().record(
        type="param_edit",   # 沿用現有稽核類型（帳號異動歸為管理操作）
        operator=operator["operator_id"],
        action=f"建立帳號 {body.operator_id}（角色 {body.role}）",
        reason="帳號管理",
    )
    return {"message": "帳號已建立", "operator": created}


@router.delete("/accounts/{operator_id}")
def deactivate_account(
    operator_id: str,
    operator: dict = Depends(require_role("maintainer")),
):
    """停用帳號（需 maintainer）。停用取代刪除，保留稽核關聯；記稽核。"""
    ok = repo.deactivate(operator_id)
    if not ok:
        raise HTTPException(status_code=404, detail=f"查無帳號 {operator_id}")
    get_audit_service().record(
        type="param_edit",
        operator=operator["operator_id"],
        action=f"停用帳號 {operator_id}",
        reason="帳號管理",
    )
    return {"message": f"帳號 {operator_id} 已停用"}


@router.get("/accounts")
def list_accounts(operator: dict = Depends(require_role("maintainer"))):
    """列出所有帳號（需 maintainer，不含密碼雜湊）。"""
    return repo.list_operators()
