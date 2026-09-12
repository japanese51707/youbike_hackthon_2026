import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent / "backend"))

# 模擬 demo backend 的資料源設定
from config_loader import get_config
get_config()["data_source"]["mode"] = "youbike_official"

from core.data import get_stations_with_degradation
try:
    rows = get_stations_with_degradation()
    print("degradation OK count=", len(rows))
    if rows:
        print("first freshness:", rows[0].get("data_freshness"), "reasons:", rows[0].get("quality_reasons"))
except Exception as e:
    import traceback
    print("degradation FAIL:", type(e).__name__, str(e))
    traceback.print_exc()
