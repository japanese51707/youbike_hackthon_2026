"""
YouBike 資料整合腳本
====================
將 12 個 CSV 檔案（混合編碼 UTF-8 / Big5）統一整合為分區 Parquet 格式。

輸出結構：
  output/youbike_parquet/
    year_month=2026-01/
      data.parquet
    year_month=2026-02/
      data.parquet
    ...
    year_month=2026-06/
      data.parquet

也會輸出一份完整合併的 CSV 供快速檢視：
  output/youbike_all.csv
"""

import os
import pandas as pd
from pathlib import Path

# === 設定 ===
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "youbike資料集"
OUTPUT_DIR = BASE_DIR / "output"
PARQUET_DIR = OUTPUT_DIR / "youbike_parquet"

# 欄位定義（兩種來源的欄位名稱一致）
COLUMNS = ["日期", "城市", "行政區", "場站名稱", "總車柱數", "可借車數", "可還位數", "經度", "緯度"]

# === 檔案分類 ===
# UTF-8 編碼的檔案（1月、2月、6月）
UTF8_FILES = [
    "YouBike 一月資料.csv 的副本.csv",
    "YouBike 二月資料.csv 的副本.csv",
    "YouBike 六月資料.csv 的副本.csv",
]

# Big5 編碼的檔案（3月～5月）
BIG5_FILES = [
    "新北AWS黑克松競賽0301-14.csv 的副本.csv",
    "新北AWS黑克松競賽0315-28.csv 的副本.csv",
    "新北AWS黑克松競賽0329-31.csv 的副本.csv",
    "新北AWS黑克松競賽0401-14.csv 的副本.csv",
    "新北AWS黑克松競賽0415-28.csv 的副本.csv",
    "新北AWS黑克松競賽0429-30.csv 的副本.csv",
    "新北AWS黑克松競賽0501-14.csv 的副本.csv",
    "新北AWS黑克松競賽0515-28.csv 的副本.csv",
    "新北AWS黑克松競賽0529-31.csv 的副本.csv",
]


def read_utf8_csv(filepath: Path) -> pd.DataFrame:
    """讀取 UTF-8 編碼的 CSV（1月、2月、6月格式）"""
    df = pd.read_csv(filepath, encoding="utf-8", dtype=str)
    df.columns = COLUMNS
    return df


def read_big5_csv(filepath: Path) -> pd.DataFrame:
    """讀取 Big5 編碼的 CSV（3月～5月格式）"""
    df = pd.read_csv(filepath, encoding="big5", dtype=str)
    df.columns = COLUMNS
    return df


def normalize_datetime(date_str: str) -> str:
    """
    統一日期格式為 'YYYY-MM-DD HH:MM:SS'
    輸入格式可能是：
      - '2026/01/11 18:00'（缺秒數）
      - '2026-03-01 23:30:40'（完整）
    """
    if pd.isna(date_str):
        return date_str
    date_str = date_str.strip().strip('"')
    # 把 / 替換為 -
    date_str = date_str.replace("/", "-")
    # 如果只有 HH:MM，補 :00
    parts = date_str.split(" ")
    if len(parts) == 2:
        time_parts = parts[1].split(":")
        if len(time_parts) == 2:
            date_str = f"{parts[0]} {parts[1]}:00"
    return date_str


def main():
    print("=" * 60)
    print("YouBike 資料整合腳本")
    print("=" * 60)

    all_dfs = []

    # 讀取 UTF-8 檔案
    print("\n📂 讀取 UTF-8 編碼檔案...")
    for filename in UTF8_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  ⚠️  找不到: {filename}")
            continue
        df = read_utf8_csv(filepath)
        print(f"  ✅ {filename}: {len(df):,} 筆")
        all_dfs.append(df)

    # 讀取 Big5 檔案
    print("\n📂 讀取 Big5 編碼檔案...")
    for filename in BIG5_FILES:
        filepath = DATA_DIR / filename
        if not filepath.exists():
            print(f"  ⚠️  找不到: {filename}")
            continue
        df = read_big5_csv(filepath)
        print(f"  ✅ {filename}: {len(df):,} 筆")
        all_dfs.append(df)

    # 合併
    print("\n🔄 合併所有資料...")
    merged = pd.concat(all_dfs, ignore_index=True)
    print(f"   合併後總筆數: {len(merged):,}")

    # 統一日期格式
    print("\n🕐 統一日期格式...")
    merged["日期"] = merged["日期"].apply(normalize_datetime)

    # 轉換資料型態
    print("🔢 轉換資料型態...")
    merged["總車柱數"] = pd.to_numeric(merged["總車柱數"], errors="coerce").astype("Int32")
    merged["可借車數"] = pd.to_numeric(merged["可借車數"], errors="coerce").astype("Int32")
    merged["可還位數"] = pd.to_numeric(merged["可還位數"], errors="coerce").astype("Int32")
    merged["經度"] = pd.to_numeric(merged["經度"], errors="coerce").astype("float64")
    merged["緯度"] = pd.to_numeric(merged["緯度"], errors="coerce").astype("float64")

    # 建立分區欄位 year_month
    print("📅 建立分區欄位 (year_month)...")
    merged["year_month"] = merged["日期"].str[:7]  # 取 'YYYY-MM'

    # 加入衍生欄位方便分析
    print("📊 加入衍生分析欄位...")
    merged["空位率"] = (merged["可還位數"] / merged["總車柱數"] * 100).round(2)
    merged["借用率"] = (merged["可借車數"] / merged["總車柱數"] * 100).round(2)
    # 空站（可借 = 0）或滿站（可還 = 0）標記
    merged["是否空站"] = (merged["可借車數"] == 0).astype("Int32")
    merged["是否滿站"] = (merged["可還位數"] == 0).astype("Int32")

    # 建立輸出目錄
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)

    # 輸出合併 CSV（供快速檢視）
    csv_output = OUTPUT_DIR / "youbike_all.csv"
    print(f"\n💾 輸出合併 CSV: {csv_output}")
    merged.to_csv(csv_output, index=False, encoding="utf-8-sig")

    # 輸出分區 Parquet
    print(f"💾 輸出分區 Parquet: {PARQUET_DIR}/")
    for ym, group in merged.groupby("year_month"):
        partition_dir = PARQUET_DIR / f"year_month={ym}"
        partition_dir.mkdir(parents=True, exist_ok=True)
        output_file = partition_dir / "data.parquet"
        # 寫入時不包含分區欄位（Athena 會自動推斷）
        group.drop(columns=["year_month"]).to_parquet(
            output_file,
            engine="pyarrow",
            index=False,
            compression="snappy",
        )
        print(f"  ✅ {ym}: {len(group):,} 筆 → {output_file.stat().st_size / 1024 / 1024:.1f} MB")

    # 統計摘要
    print("\n" + "=" * 60)
    print("📋 資料摘要")
    print("=" * 60)
    print(f"  總筆數: {len(merged):,}")
    print(f"  時間範圍: {merged['日期'].min()} ~ {merged['日期'].max()}")
    print(f"  行政區數: {merged['行政區'].nunique()}")
    print(f"  場站數: {merged['場站名稱'].nunique()}")
    print(f"  CSV 大小: {csv_output.stat().st_size / 1024 / 1024:.1f} MB")

    total_parquet_size = sum(
        f.stat().st_size for f in PARQUET_DIR.rglob("*.parquet")
    )
    print(f"  Parquet 總大小: {total_parquet_size / 1024 / 1024:.1f} MB")
    print(f"  壓縮比: {csv_output.stat().st_size / total_parquet_size:.1f}x")
    print("\n✅ 完成！")


if __name__ == "__main__":
    main()
