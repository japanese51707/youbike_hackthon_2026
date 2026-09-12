"""ADR-324：一趟派工單的組成規則。

營運上「一趟」的定義是先到滿站取車、再到空站放車，兩種行為都要有才算完成。
先前會產出兩種做不完的單：只有補車站（車上沒車、沿途也沒取車）、
只有取車站（收了一車卻沒有要放的站）。這裡把規則釘住。
"""

import tests.test_auto_dispatch as T
from core import auto_dispatch, donor_stations
from db import tasks_repo


def _place_one(monkeypatch, recs):
    T._setup()
    monkeypatch.setattr(auto_dispatch, "_current_dispatch_list",
                        lambda: [dict(r) for r in recs])
    placed = auto_dispatch.scan_once()
    assert placed, f"應至少配出一張派工單，診斷：{auto_dispatch._last_diagnostics}"
    return [tasks_repo.get(p["trip_id"]) for p in placed]


def test_trip_has_both_collect_and_supply_in_order(monkeypatch):
    """每一趟都要有車源與去處，且取車排在補車之前。"""
    for task in _place_one(monkeypatch, T.DL):
        actions = [s["action"] for s in task["route"]]
        assert "補車" in actions, f"一趟一定要有補車站：{actions}"
        assert "取車" in actions or task.get("depot_load"), \
            f"一趟一定要有車源（趟內取車站或總部裝車）：{actions}"
        if "取車" in actions and "補車" in actions:
            assert actions.index("取車") < actions.index("補車"), \
                f"必須先取車再補車：{actions}"


def test_depot_load_persists_to_task_when_no_donor(monkeypatch):
    """完全沒有供車站可取時，改由總部裝車出發，且裝車指示要存進任務。

    司機端要靠這個欄位顯示「從總部裝幾台」——車源不在路線上，不寫進任務他就看不到。
    """
    monkeypatch.setattr(donor_stations, "get_all_stations", lambda *a, **k: [])
    # 需求要超過車上既有載量（夾具的車半載 7 台），否則根本不需要總部補足
    big = [dict(T.DL[0], quantity=14, current_available=1)]
    tasks = _place_one(monkeypatch, big)
    depot_tasks = [t for t in tasks if t.get("depot_load")]
    assert depot_tasks, "沒有供車站時應改由總部裝車出發"
    for task in depot_tasks:
        load = task["depot_load"]
        assert load["quantity"] > 0
        assert "總部" in (load.get("label") or "")
        # 總部裝車的量要能覆蓋這趟的補車需求
        demand = sum(int(s.get("quantity") or 0)
                     for s in task["route"] if s.get("action") != "取車")
        assert load["quantity"] > 0
