"""
調度資源 Provider 抽象 + 工廠（ADR-114，比照 ADR-006 DataSource）
==================================================================
人員（調度員）與車輛（調度車）清單抽象成 Provider 介面。上層（dispatcher）只依賴介面，
不管清單從哪來。未來 YouBike 公司丟人力/車隊 API，只要新增一個實作接上即可，dispatcher 不動。

換源只改 config.yaml 的 `dispatch_resource.mode`（比照資料源 data_source.mode）。

對外暴露：
    get_operator_provider() -> OperatorProvider   # 依 config 回實作（單例快取）
    get_fleet_provider()    -> FleetProvider       # 依 config 回實作（單例快取）
    OperatorProvider / FleetProvider               # 抽象基底（介面契約）

回傳格式契約
------------
調度員 dict：operator_id, name, role, status, current_district, current_task_id, is_active
調度車 dict：vehicle_id, max_capacity, status, current_district, current_task_id, is_active
不同來源（本地 DB seed、未來 YouBike API）各自在實作裡對映到這組欄位，上層拿到一致格式。
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional


# ── 抽象介面（模板）──
class OperatorProvider(ABC):
    """調度員清單來源介面。所有實作回傳標準調度員 dict。"""

    name: str = "abstract"

    @abstractmethod
    def list_operators(self, active_only: bool = False) -> list[dict]:
        ...

    @abstractmethod
    def get_operator(self, operator_id: str) -> Optional[dict]:
        ...

    def available_operators(self) -> list[dict]:
        """可派遣的一般調度員（啟用中、非忙碌/休息，且非總站待命）。
        總站待命人力（ADR-119 depot_standby）為獨立資源池，用 depot_standby_operators() 取。"""
        out = []
        for o in self.list_operators(active_only=True):
            if o.get("role_type") == "depot_standby":
                continue   # 總站待命獨立，不進一般池
            if o.get("status") in (None, "on_duty", "off_duty"):
                out.append(o)
        return out

    def depot_standby_operators(self) -> list[dict]:
        """總站待命人力（ADR-119，可調派各區支援）。"""
        return [o for o in self.list_operators(active_only=True)
                if o.get("role_type") == "depot_standby"
                and o.get("status") in (None, "on_duty", "off_duty")]


class FleetProvider(ABC):
    """調度車清單來源介面。所有實作回傳標準調度車 dict。"""

    name: str = "abstract"

    @abstractmethod
    def list_vehicles(self, active_only: bool = False) -> list[dict]:
        ...

    @abstractmethod
    def get_vehicle(self, vehicle_id: str) -> Optional[dict]:
        ...

    def available_vehicles(self) -> list[dict]:
        """可派遣的一般調度車（啟用中、status=available，且非總站待命）。
        總站待命車（ADR-119 is_depot）與預備車（standby）為獨立池，各有專屬取法。"""
        return [v for v in self.list_vehicles(active_only=True)
                if v.get("status") == "available" and not v.get("is_depot")]

    def depot_standby_vehicles(self) -> list[dict]:
        """總站待命車（ADR-119，is_depot 且 available，可調派各區）。"""
        return [v for v in self.list_vehicles(active_only=True)
                if v.get("is_depot") and v.get("status") == "available"]


# ── 內建實作：讀本地 SQLite（開發/demo；含 seed）──
class DBOperatorProvider(OperatorProvider):
    name = "db"

    def list_operators(self, active_only: bool = False) -> list[dict]:
        from db import operators_repo
        return operators_repo.list_operators(active_only=active_only)

    def get_operator(self, operator_id: str) -> Optional[dict]:
        from db import operators_repo
        return operators_repo.get_operator(operator_id)


class DBFleetProvider(FleetProvider):
    name = "db"

    def list_vehicles(self, active_only: bool = False) -> list[dict]:
        from db import vehicles_repo
        return vehicles_repo.list_vehicles(active_only=active_only)

    def get_vehicle(self, vehicle_id: str) -> Optional[dict]:
        from db import vehicles_repo
        return vehicles_repo.get_vehicle(vehicle_id)


# ── 工廠（依 config 切換，單例快取；比照 get_data_source）──
_op_instance: Optional[OperatorProvider] = None
_op_mode: Optional[str] = None
_fleet_instance: Optional[FleetProvider] = None
_fleet_mode: Optional[str] = None


def _mode() -> str:
    """dispatch_resource.mode：db（本地 seed）/ youbike_api（未來）。預設 db。"""
    try:
        from config_loader import get_config
        return get_config().get("dispatch_resource", {}).get("mode", "db")
    except Exception:
        return "db"


def get_operator_provider(force_mode: Optional[str] = None) -> OperatorProvider:
    global _op_instance, _op_mode
    mode = force_mode or _mode()
    if force_mode is None and _op_instance is not None and _op_mode == mode:
        return _op_instance
    inst = _build_operator(mode)
    if force_mode is None:
        _op_instance, _op_mode = inst, mode
    return inst


def get_fleet_provider(force_mode: Optional[str] = None) -> FleetProvider:
    global _fleet_instance, _fleet_mode
    mode = force_mode or _mode()
    if force_mode is None and _fleet_instance is not None and _fleet_mode == mode:
        return _fleet_instance
    inst = _build_fleet(mode)
    if force_mode is None:
        _fleet_instance, _fleet_mode = inst, mode
    return inst


def _build_operator(mode: str) -> OperatorProvider:
    if mode == "db":
        return DBOperatorProvider()
    # 未來：if mode == "youbike_api": from .youbike_hr import YouBikeOperatorProvider ...
    raise ValueError(f"未知的 dispatch_resource.mode（operator）：'{mode}'（可用：db）")


def _build_fleet(mode: str) -> FleetProvider:
    if mode == "db":
        return DBFleetProvider()
    # 未來：if mode == "youbike_api": from .youbike_fleet import YouBikeFleetProvider ...
    raise ValueError(f"未知的 dispatch_resource.mode（fleet）：'{mode}'（可用：db）")


def reset_providers() -> None:
    """測試用：清掉快取單例。"""
    global _op_instance, _op_mode, _fleet_instance, _fleet_mode
    _op_instance = _op_mode = _fleet_instance = _fleet_mode = None
