"""
AWS 部署腳本（S3 + Glue + Athena）
===================================
將本地 Parquet 資料上傳到 S3，建立 Glue Table，並執行驗證查詢。

用法：
  python setup_aws.py --bucket YOUR_BUCKET_NAME --region ap-northeast-1

可重複執行：會覆蓋舊資料、重建 table。

環境需求：
  - AWS CLI 已設定好 credentials（aws configure）
  - pip install boto3 pandas pyarrow
"""

import argparse
import time
import boto3
from pathlib import Path


# === 預設設定 ===
DEFAULT_REGION = "ap-northeast-1"  # 東京（離台灣最近）
DEFAULT_BUCKET = "youbike-hackathon-2026"
DATABASE_NAME = "youbike_db"
TABLE_NAME = "station_status"
S3_PREFIX = "youbike_data/"

# 本地 Parquet 路徑
BASE_DIR = Path(__file__).parent
PARQUET_DIR = BASE_DIR / "output" / "youbike_parquet"


def parse_args():
    parser = argparse.ArgumentParser(description="部署 YouBike 資料到 AWS")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="S3 bucket 名稱")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region")
    parser.add_argument("--profile", default=None, help="AWS CLI profile 名稱（可選）")
    parser.add_argument("--skip-upload", action="store_true", help="跳過上傳，只建表")
    return parser.parse_args()


def create_bucket_if_not_exists(s3_client, bucket_name, region):
    """建立 S3 bucket（如果不存在）"""
    try:
        s3_client.head_bucket(Bucket=bucket_name)
        print(f"  ✅ Bucket 已存在: {bucket_name}")
    except s3_client.exceptions.ClientError:
        print(f"  🆕 建立 Bucket: {bucket_name}")
        if region == "us-east-1":
            s3_client.create_bucket(Bucket=bucket_name)
        else:
            s3_client.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )
        print(f"  ✅ Bucket 建立完成")


def upload_parquet_to_s3(s3_client, bucket_name):
    """上傳本地 Parquet 到 S3"""
    if not PARQUET_DIR.exists():
        print(f"  ❌ 找不到 Parquet 目錄: {PARQUET_DIR}")
        print("     請先執行 merge_csv_to_parquet.py")
        return False

    parquet_files = list(PARQUET_DIR.rglob("*.parquet"))
    if not parquet_files:
        print("  ❌ 沒有找到 Parquet 檔案")
        return False

    print(f"  📤 上傳 {len(parquet_files)} 個 Parquet 檔案...")
    for f in parquet_files:
        # 保留分區目錄結構: youbike_data/year_month=2026-01/data.parquet
        relative_path = f.relative_to(PARQUET_DIR)
        s3_key = f"{S3_PREFIX}{relative_path}"
        s3_client.upload_file(str(f), bucket_name, s3_key)
        print(f"    ✅ s3://{bucket_name}/{s3_key}")

    return True


def create_glue_database(glue_client):
    """建立 Glue Database"""
    try:
        glue_client.get_database(Name=DATABASE_NAME)
        print(f"  ✅ Database 已存在: {DATABASE_NAME}")
    except glue_client.exceptions.EntityNotFoundException:
        glue_client.create_database(
            DatabaseInput={
                "Name": DATABASE_NAME,
                "Description": "YouBike 新北市站點狀態資料（黑客松研發用）",
            }
        )
        print(f"  ✅ Database 建立完成: {DATABASE_NAME}")


def create_glue_table(glue_client, bucket_name):
    """建立 Glue Table（指向 S3 上的 Parquet）"""
    s3_location = f"s3://{bucket_name}/{S3_PREFIX}"

    # 先刪除舊 table（如果存在）
    try:
        glue_client.delete_table(DatabaseName=DATABASE_NAME, Name=TABLE_NAME)
        print(f"  🗑️  已刪除舊 table: {TABLE_NAME}")
    except glue_client.exceptions.EntityNotFoundException:
        pass

    glue_client.create_table(
        DatabaseName=DATABASE_NAME,
        TableInput={
            "Name": TABLE_NAME,
            "Description": "YouBike 站點即時狀態（每半小時快照）",
            "StorageDescriptor": {
                "Columns": [
                    {"Name": "日期", "Type": "string", "Comment": "資料時間 YYYY-MM-DD HH:MM:SS"},
                    {"Name": "城市", "Type": "string", "Comment": "城市名稱"},
                    {"Name": "行政區", "Type": "string", "Comment": "行政區名稱"},
                    {"Name": "場站名稱", "Type": "string", "Comment": "YouBike 場站名稱"},
                    {"Name": "總車柱數", "Type": "int", "Comment": "該站總車位數"},
                    {"Name": "可借車數", "Type": "int", "Comment": "目前可借車輛數"},
                    {"Name": "可還位數", "Type": "int", "Comment": "目前可停空位數"},
                    {"Name": "經度", "Type": "double", "Comment": "站點經度"},
                    {"Name": "緯度", "Type": "double", "Comment": "站點緯度"},
                    {"Name": "空位率", "Type": "double", "Comment": "可還位數/總車柱數 * 100"},
                    {"Name": "借用率", "Type": "double", "Comment": "可借車數/總車柱數 * 100"},
                    {"Name": "是否空站", "Type": "int", "Comment": "可借車數=0 時為 1"},
                    {"Name": "是否滿站", "Type": "int", "Comment": "可還位數=0 時為 1"},
                ],
                "Location": s3_location,
                "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                    "Parameters": {"serialization.format": "1"},
                },
            },
            "PartitionKeys": [
                {"Name": "year_month", "Type": "string", "Comment": "分區鍵：YYYY-MM"},
            ],
            "TableType": "EXTERNAL_TABLE",
            "Parameters": {
                "classification": "parquet",
                "compressionType": "snappy",
                "typeOfData": "file",
            },
        },
    )
    print(f"  ✅ Table 建立完成: {DATABASE_NAME}.{TABLE_NAME}")
    print(f"     位置: {s3_location}")


def add_partitions(glue_client, bucket_name):
    """新增分區（讓 Athena 能找到資料）"""
    partitions = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05", "2026-06"]
    s3_base = f"s3://{bucket_name}/{S3_PREFIX}"

    partition_inputs = []
    for ym in partitions:
        partition_inputs.append({
            "Values": [ym],
            "StorageDescriptor": {
                "Columns": [
                    {"Name": "日期", "Type": "string"},
                    {"Name": "城市", "Type": "string"},
                    {"Name": "行政區", "Type": "string"},
                    {"Name": "場站名稱", "Type": "string"},
                    {"Name": "總車柱數", "Type": "int"},
                    {"Name": "可借車數", "Type": "int"},
                    {"Name": "可還位數", "Type": "int"},
                    {"Name": "經度", "Type": "double"},
                    {"Name": "緯度", "Type": "double"},
                    {"Name": "空位率", "Type": "double"},
                    {"Name": "借用率", "Type": "double"},
                    {"Name": "是否空站", "Type": "int"},
                    {"Name": "是否滿站", "Type": "int"},
                ],
                "Location": f"{s3_base}year_month={ym}/",
                "InputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetInputFormat",
                "OutputFormat": "org.apache.hadoop.hive.ql.io.parquet.MapredParquetOutputFormat",
                "SerdeInfo": {
                    "SerializationLibrary": "org.apache.hadoop.hive.ql.io.parquet.serde.ParquetHiveSerDe",
                    "Parameters": {"serialization.format": "1"},
                },
            },
        })

    try:
        glue_client.batch_create_partition(
            DatabaseName=DATABASE_NAME,
            TableName=TABLE_NAME,
            PartitionInputList=partition_inputs,
        )
        print(f"  ✅ 已新增 {len(partitions)} 個分區")
    except Exception as e:
        print(f"  ⚠️  分區新增部分失敗（可能已存在）: {e}")


def run_athena_test_query(athena_client, bucket_name, region):
    """執行一個測試查詢確認一切正常"""
    output_location = f"s3://{bucket_name}/athena-results/"

    query = f"""
    SELECT 
        year_month,
        COUNT(*) as total_records,
        COUNT(DISTINCT "場站名稱") as station_count,
        ROUND(AVG("空位率"), 2) as avg_empty_rate,
        SUM("是否空站") as empty_station_count,
        SUM("是否滿站") as full_station_count
    FROM {DATABASE_NAME}.{TABLE_NAME}
    GROUP BY year_month
    ORDER BY year_month
    """

    print(f"\n  🔍 執行測試查詢...")
    print(f"     SQL: SELECT year_month, COUNT(*), ... GROUP BY year_month")

    response = athena_client.start_query_execution(
        QueryString=query,
        ResultConfiguration={"OutputLocation": output_location},
        QueryExecutionContext={"Database": DATABASE_NAME},
    )

    query_id = response["QueryExecutionId"]
    print(f"     Query ID: {query_id}")

    # 等待查詢完成
    while True:
        result = athena_client.get_query_execution(QueryExecutionId=query_id)
        status = result["QueryExecution"]["Status"]["State"]
        if status in ("SUCCEEDED", "FAILED", "CANCELLED"):
            break
        print(f"     狀態: {status}...")
        time.sleep(2)

    if status == "SUCCEEDED":
        # 取得結果
        results = athena_client.get_query_results(QueryExecutionId=query_id)
        rows = results["ResultSet"]["Rows"]
        print(f"\n  ✅ 查詢成功！結果：")
        print(f"     {'月份':<12} {'記錄數':<10} {'場站數':<8} {'平均空位率':<12} {'空站次數':<10} {'滿站次數'}")
        print(f"     {'-'*64}")
        for row in rows[1:]:  # 跳過 header
            data = [col.get("VarCharValue", "N/A") for col in row["Data"]]
            print(f"     {data[0]:<12} {data[1]:<10} {data[2]:<8} {data[3]:<12} {data[4]:<10} {data[5]}")

        # 顯示掃描量
        stats = result["QueryExecution"]["Statistics"]
        scanned_mb = stats["DataScannedInBytes"] / 1024 / 1024
        print(f"\n     📊 此次查詢掃描: {scanned_mb:.2f} MB")
        print(f"     💰 預估費用: ${scanned_mb / 1024 / 1024 * 5:.6f}")
    else:
        reason = result["QueryExecution"]["Status"].get("StateChangeReason", "未知")
        print(f"  ❌ 查詢失敗: {reason}")


def main():
    args = parse_args()

    # 建立 AWS clients
    session_kwargs = {"region_name": args.region}
    if args.profile:
        session_kwargs["profile_name"] = args.profile

    session = boto3.Session(**session_kwargs)
    s3_client = session.client("s3")
    glue_client = session.client("glue")
    athena_client = session.client("athena")

    print("=" * 60)
    print("AWS 部署腳本 — YouBike 資料")
    print("=" * 60)
    print(f"  Bucket:  {args.bucket}")
    print(f"  Region:  {args.region}")
    print(f"  Profile: {args.profile or '(default)'}")
    print()

    # Step 1: 建立 S3 Bucket
    print("📦 Step 1: S3 Bucket")
    create_bucket_if_not_exists(s3_client, args.bucket, args.region)

    # Step 2: 上傳 Parquet
    if not args.skip_upload:
        print("\n📤 Step 2: 上傳 Parquet 資料")
        success = upload_parquet_to_s3(s3_client, args.bucket)
        if not success:
            return
    else:
        print("\n⏭️  Step 2: 跳過上傳")

    # Step 3: 建立 Glue Database
    print("\n🗄️  Step 3: Glue Database")
    create_glue_database(glue_client)

    # Step 4: 建立 Glue Table
    print("\n📋 Step 4: Glue Table")
    create_glue_table(glue_client, args.bucket)

    # Step 5: 新增分區
    print("\n📂 Step 5: 新增分區")
    add_partitions(glue_client, args.bucket)

    # Step 6: 測試查詢
    print("\n🧪 Step 6: Athena 驗證查詢")
    run_athena_test_query(athena_client, args.bucket, args.region)

    print("\n" + "=" * 60)
    print("🎉 部署完成！")
    print("=" * 60)
    print(f"""
接下來你可以：
  1. 開啟 AWS Console → Athena
  2. 選擇 Database: {DATABASE_NAME}
  3. 直接下 SQL 查詢，例如：

     -- 查看各行政區空滿站狀況
     SELECT 行政區, 
            SUM(是否空站) as 空站次數,
            SUM(是否滿站) as 滿站次數
     FROM {DATABASE_NAME}.{TABLE_NAME}
     WHERE year_month = '2026-03'
     GROUP BY 行政區
     ORDER BY 空站次數 DESC;

  4. 要關閉資源時，執行：
     python teardown_aws.py --bucket {args.bucket}
""")


if __name__ == "__main__":
    main()
