"""
ADR-113 即時預測端到端 Demo（即時→LightGBM→規則引擎三層→緊急度排序）
=====================================================================
串起全鏈路，驗證真實模型即時跑通：
  1. 即時源（新北開放資料 010e5b15）拿站點當下快照
  2. LightGBMPredictor 出 4 視野 × P10/P50/P90 到達存量區間（raw+bound）
  3. 規則引擎三層判斷（截斷/警示/正常）+ 補齊 4 視野 arrival_by_horizon
  4. RealUrgencyCalculator 分層打底緊急度 + 排序

用法：python backend/prediction/demo_realtime_e2e.py [站數，預設 8]
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.data.youbike_official import YouBikeOfficialDataSource
from core.interfaces import LightGBMPredictor, RealUrgencyCalculator
from core.rule_engine import evaluate_station
from config_loader import get_config


def main(n_show: int = 8):
    cfg = get_config()
    ds = YouBikeOfficialDataSource()
    allst = ds.get_stations()
    print(f"即時源：抓到 {len(allst)} 站", flush=True)

    # 挑不同狀態站（接近空/接近滿/正常）驗證三層都會被觸發
    empty_ish = [s for s in allst if s["available_bikes"] <= 2][:3]
    full_ish = [s for s in allst if s["available_docks"] <= 2][:3]
    normal = [s for s in allst if 5 < s["available_bikes"] < s["total_docks"] - 5][:2]
    sample = empty_ish + full_ish + normal
    sample = sample[:n_show]

    pred = LightGBMPredictor()
    urg = RealUrgencyCalculator()
    horizon = cfg["fleet"]["響應時間_分鐘"]

    print(f"\n端到端跑 {len(sample)} 站（響應視野 {horizon} 分）：", flush=True)
    recs = []
    for st in sample:
        multi = pred.predict_multi(st)
        interval = multi.for_horizon(horizon)
        rec = evaluate_station(st, interval, cfg, multi=multi)
        tag = rec["urgency_tier"] if rec else "normal(不調度)"
        print(f"  {st['station_name'][:16]:20s} 借{st['available_bikes']:3d}/{st['total_docks']:3d} "
              f"-> {tag}", flush=True)
        if rec:
            st2 = dict(st)
            st2["hour"] = 12
            rec["urgency_score"] = urg.calc_urgency(st2, interval, rec["action"])
            recs.append(rec)

    print("\n需調度站（依緊急度排序）：", flush=True)
    for r in sorted(recs, key=lambda x: -x["urgency_score"]):
        print(f"  [{r['urgency_score']:5.1f}] {r['action']} {r['quantity']:2d}台 "
              f"{r['station_name'][:12]:14s} 層={r['urgency_tier']:8s} "
              f"早穿透={r['breach_horizon_min']} 4視野={r['arrival_by_horizon']}", flush=True)
    print("\n✓ 端到端跑通：即時→LightGBM(4視野區間)→規則引擎三層→緊急度排序", flush=True)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    main(n)
