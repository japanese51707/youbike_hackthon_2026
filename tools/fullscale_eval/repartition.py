"""Pass 1：把 6 個月 Parquet 重切成「按站分塊」的小檔，只留建特徵需要的 7 個欄位。

一次載入全部 13.3M 列 × 13 欄會吃掉 3.2 GB，後面建特徵必然 OOM；
按站分塊後每塊只需載自己的列，且站級統計（p50／周轉量／指紋／POI／地形／天氣）
本來就是每站獨立算的，分塊不影響結果。
"""
import json, sys
from pathlib import Path
import pyarrow as pa, pyarrow.parquet as pq

COLS = ["日期", "場站名稱", "總車柱數", "可借車數", "可還位數", "經度", "緯度"]
SRC = Path("/home/claude/yb/output/youbike_parquet")
OUT = Path("/home/claude/work/chunks")
N_CHUNKS = int(sys.argv[1]) if len(sys.argv) > 1 else 10

OUT.mkdir(parents=True, exist_ok=True)
files = sorted(SRC.glob("year_month=*/data.parquet"))

# 先掃一遍站名（只讀一欄，便宜）
names = set()
for f in files:
    names |= set(pq.read_table(f, columns=["場站名稱"])["場站名稱"].to_pylist())
names = sorted(names)
print(f"stations: {len(names):,}", flush=True)
assign = {n: i % N_CHUNKS for i, n in enumerate(names)}
(OUT / "assign.json").write_text(json.dumps(assign, ensure_ascii=False), encoding="utf-8")

writers = {}
try:
    for f in files:
        table = pq.read_table(f, columns=COLS)
        chunk_col = pa.array([assign[n] for n in table["場站名稱"].to_pylist()], type=pa.int8())
        table = table.append_column("_chunk", chunk_col)
        for c in range(N_CHUNKS):
            part = table.filter(pa.compute.equal(table["_chunk"], c)).drop(["_chunk"])
            if part.num_rows == 0:
                continue
            if c not in writers:
                writers[c] = pq.ParquetWriter(OUT / f"chunk_{c:02d}.parquet", part.schema,
                                              compression="zstd")
            writers[c].write_table(part)
        print(f"  {f.parent.name}: {table.num_rows:,} rows", flush=True)
        del table
finally:
    for w in writers.values():
        w.close()

total = 0
for c in range(N_CHUNKS):
    p = OUT / f"chunk_{c:02d}.parquet"
    m = pq.ParquetFile(p).metadata
    total += m.num_rows
    print(f"chunk_{c:02d}: {m.num_rows:,} rows, {p.stat().st_size/1e6:.1f} MB", flush=True)
print(f"total {total:,} rows", flush=True)
