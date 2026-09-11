"""Start an isolated local Demo backend with explicit SQLite path and sample fleet."""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Demo SQLite path; use a separate file from operational data")
    parser.add_argument("--data-mode", choices=("mock", "youbike_official"), default="mock")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    os.environ["YOUBIKE_DB_PATH"] = str(args.db.resolve())
    from config_loader import get_config
    get_config()["data_source"]["mode"] = args.data_mode
    from db import init_db, operators_repo, vehicles_repo
    init_db()
    operators_repo.seed_default_operators()
    operators_repo.seed_dispatch_operators(6)
    vehicles_repo.seed_default_vehicles(3, 15)
    # ADR-123：車上載量未知的車不可確認派工。Demo 以「開班前回報滿載」起始，
    # 之後由逐站回報與結案推算自動維護；正式環境改由人工回報或車隊 API 提供。
    for index in range(1, 4):
        vehicles_repo.report_onboard(f"CAR-{index:03d}", 15, "manual_report")
    import uvicorn
    from main import app
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
