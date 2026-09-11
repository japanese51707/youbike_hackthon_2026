"""Explicit Demo duty check-in, sharing the dispatch resource transaction."""
from db.connection import atomic
from db import operators_repo
from core.dispatch_guards import occupied_tasks
from core.dispatch_errors import DispatchConflict, DispatchForbidden


@atomic
def set_duty(operator_id, status):
    operator = operators_repo.get_operator(operator_id)
    if not operator or not operator["is_active"] or operator.get("role_type") not in {"driver", "depot_standby"}:
        raise DispatchForbidden("此帳號不具調度車執行角色")
    if operator.get("current_task_id") or any(t.get("assigned_operator") == operator_id for t in occupied_tasks()):
        raise DispatchConflict("仍有任務，請先完成或退回任務")
    if status not in {"on_duty", "off_duty"}:
        raise ValueError("無效的值勤狀態")
    operators_repo.update_status(operator_id, status)
    from core.audit import get_audit_service
    get_audit_service().record(type="task_report", operator=operator_id, action=f"值勤狀態改為 {status}")
    return operators_repo.get_operator(operator_id)
