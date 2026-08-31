"""
AWS 資源關閉腳本
================
刪除所有 YouBike 相關的 AWS 資源，確保不再產生任何費用。

用法：
  python teardown_aws.py --bucket YOUR_BUCKET_NAME --region ap-northeast-1

⚠️ 這會刪除：
  - S3 Bucket 中所有物件和 Bucket 本身
  - Glue Database 和 Table
  - Athena 查詢結果
"""

import argparse
import boto3


DEFAULT_REGION = "ap-northeast-1"
DEFAULT_BUCKET = "youbike-hackathon-2026"
DATABASE_NAME = "youbike_db"
TABLE_NAME = "station_status"


def parse_args():
    parser = argparse.ArgumentParser(description="關閉 YouBike AWS 資源")
    parser.add_argument("--bucket", default=DEFAULT_BUCKET, help="S3 bucket 名稱")
    parser.add_argument("--region", default=DEFAULT_REGION, help="AWS region")
    parser.add_argument("--profile", default=None, help="AWS CLI profile 名稱")
    parser.add_argument("--confirm", action="store_true", help="跳過確認提示，直接刪除")
    return parser.parse_args()


def delete_all_objects_in_bucket(s3_client, bucket_name):
    """刪除 bucket 中所有物件"""
    paginator = s3_client.get_paginator("list_objects_v2")
    total_deleted = 0

    for page in paginator.paginate(Bucket=bucket_name):
        objects = page.get("Contents", [])
        if not objects:
            continue

        delete_keys = [{"Key": obj["Key"]} for obj in objects]
        s3_client.delete_objects(
            Bucket=bucket_name,
            Delete={"Objects": delete_keys},
        )
        total_deleted += len(delete_keys)

    return total_deleted


def main():
    args = parse_args()

    if not args.confirm:
        print("⚠️  即將刪除以下 AWS 資源：")
        print(f"    - S3 Bucket: {args.bucket}（含所有物件）")
        print(f"    - Glue Database: {DATABASE_NAME}")
        print(f"    - Glue Table: {TABLE_NAME}")
        print()
        answer = input("確定要刪除嗎？輸入 'yes' 繼續: ")
        if answer.lower() != "yes":
            print("已取消。")
            return

    session_kwargs = {"region_name": args.region}
    if args.profile:
        session_kwargs["profile_name"] = args.profile

    session = boto3.Session(**session_kwargs)
    s3_client = session.client("s3")
    glue_client = session.client("glue")

    print("\n" + "=" * 60)
    print("🗑️  關閉 AWS 資源")
    print("=" * 60)

    # 1. 刪除 Glue Table
    print("\n📋 Step 1: 刪除 Glue Table")
    try:
        glue_client.delete_table(DatabaseName=DATABASE_NAME, Name=TABLE_NAME)
        print(f"  ✅ 已刪除 Table: {TABLE_NAME}")
    except glue_client.exceptions.EntityNotFoundException:
        print(f"  ⏭️  Table 不存在，跳過")
    except Exception as e:
        print(f"  ⚠️  {e}")

    # 2. 刪除 Glue Database
    print("\n🗄️  Step 2: 刪除 Glue Database")
    try:
        glue_client.delete_database(Name=DATABASE_NAME)
        print(f"  ✅ 已刪除 Database: {DATABASE_NAME}")
    except glue_client.exceptions.EntityNotFoundException:
        print(f"  ⏭️  Database 不存在，跳過")
    except Exception as e:
        print(f"  ⚠️  {e}")

    # 3. 清空並刪除 S3 Bucket
    print(f"\n📦 Step 3: 清空並刪除 S3 Bucket ({args.bucket})")
    try:
        s3_client.head_bucket(Bucket=args.bucket)
        # Bucket 存在，先清空
        deleted_count = delete_all_objects_in_bucket(s3_client, args.bucket)
        print(f"  🗑️  已刪除 {deleted_count} 個物件")
        # 再刪除 bucket
        s3_client.delete_bucket(Bucket=args.bucket)
        print(f"  ✅ 已刪除 Bucket: {args.bucket}")
    except s3_client.exceptions.ClientError as e:
        if "404" in str(e) or "NoSuchBucket" in str(e):
            print(f"  ⏭️  Bucket 不存在，跳過")
        else:
            print(f"  ⚠️  {e}")

    print("\n" + "=" * 60)
    print("✅ 所有資源已關閉！不會再產生任何費用。")
    print("=" * 60)
    print("""
已刪除的資源：
  ❌ S3 Bucket（資料儲存）→ 不再計算儲存費
  ❌ Glue Catalog（表定義）→ 不再佔用物件數
  ❌ Athena 查詢結果       → 隨 bucket 一起刪除

💡 提醒：
  - 本地的 Parquet 檔案還在 output/ 資料夾中
  - 隨時可以用 setup_aws.py 重新部署
""")


if __name__ == "__main__":
    main()
