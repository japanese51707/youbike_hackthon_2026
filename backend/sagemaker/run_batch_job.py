"""
啟動 SageMaker Processing Job（ADR-307 雲端批次推論示範）
========================================================
用 boto3（不需 sagemaker SDK）啟動一個 Processing job：
  1. 上傳模型包、站點快照、batch_predict.py 到 S3
  2. 用 SageMaker 內建 sklearn container 跑 batch_predict.py
  3. 結果 predictions.json 由 SageMaker 自動上傳回 S3

按需啟動、跑完自動關機（符合競賽資源節制）。用 hackathon profile 跑：
  AWS_PROFILE=hackathon ../../.venv/bin/python3.14 run_batch_job.py
"""
from __future__ import annotations
import json
import time
from pathlib import Path

import boto3

REGION = "us-east-1"
BUCKET = "youbike-hackathon-2026-use1"
PREFIX = "sagemaker/batch-predict"
ROLE = "arn:aws:iam::053134152077:role/youbike-sagemaker-exec"
# SageMaker 官方 sklearn 內建 image（us-east-1）。
SKLEARN_IMAGE = "683313688378.dkr.ecr.us-east-1.amazonaws.com/sagemaker-scikit-learn:1.2-1-cpu-py3"
INSTANCE_TYPE = "ml.t3.medium"  # 競賽 SageMaker 配額內；跑完自動關

HERE = Path(__file__).parent
MODELS_DIR = HERE.parent / "prediction" / "_models"


def _sample_stations(n=50):
    """取一批站點快照當批次輸入。優先用即時源，失敗退回歷史源末筆。"""
    import sys
    sys.path.insert(0, str(HERE.parent))
    try:
        from core.data import get_stations_with_degradation
        rows = get_stations_with_degradation()[:n]
        if rows:
            return rows
    except Exception as e:
        print(f"  即時源不可用（{e}），改用歷史源")
    from core.data.historical import HistoricalDataSource
    return HistoricalDataSource().get_stations()[:n]


def main():
    s3 = boto3.client("s3", region_name=REGION)
    sm = boto3.client("sagemaker", region_name=REGION)

    print("1. 上傳模型包到 S3")
    for f in MODELS_DIR.iterdir():
        if f.is_file():
            s3.upload_file(str(f), BUCKET, f"{PREFIX}/model/{f.name}")

    print("2. 產生並上傳站點快照")
    stations = _sample_stations()
    s3.put_object(Bucket=BUCKET, Key=f"{PREFIX}/input/stations.json",
                  Body=json.dumps(stations, ensure_ascii=False).encode())
    print(f"   {len(stations)} 站")

    print("3. 上傳 batch_predict.py")
    s3.upload_file(str(HERE / "batch_predict.py"), BUCKET, f"{PREFIX}/code/batch_predict.py")

    job_name = f"youbike-batch-{int(time.time())}"
    print(f"4. 啟動 Processing job：{job_name}")
    sm.create_processing_job(
        ProcessingJobName=job_name,
        RoleArn=ROLE,
        AppSpecification={
            "ImageUri": SKLEARN_IMAGE,
            "ContainerEntrypoint": ["python3", "/opt/ml/processing/code/batch_predict.py"],
        },
        ProcessingResources={"ClusterConfig": {
            "InstanceCount": 1, "InstanceType": INSTANCE_TYPE, "VolumeSizeInGB": 5,
        }},
        ProcessingInputs=[
            {"InputName": "model", "S3Input": {
                "S3Uri": f"s3://{BUCKET}/{PREFIX}/model/",
                "LocalPath": "/opt/ml/processing/model", "S3DataType": "S3Prefix",
                "S3InputMode": "File"}},
            {"InputName": "input", "S3Input": {
                "S3Uri": f"s3://{BUCKET}/{PREFIX}/input/",
                "LocalPath": "/opt/ml/processing/input", "S3DataType": "S3Prefix",
                "S3InputMode": "File"}},
            {"InputName": "code", "S3Input": {
                "S3Uri": f"s3://{BUCKET}/{PREFIX}/code/",
                "LocalPath": "/opt/ml/processing/code", "S3DataType": "S3Prefix",
                "S3InputMode": "File"}},
        ],
        ProcessingOutputConfig={"Outputs": [
            {"OutputName": "output", "S3Output": {
                "S3Uri": f"s3://{BUCKET}/{PREFIX}/output/",
                "LocalPath": "/opt/ml/processing/output", "S3UploadMode": "EndOfJob"}},
        ]},
        StoppingCondition={"MaxRuntimeInSeconds": 1200},
    )

    print("5. 等待完成（輪詢）...")
    while True:
        d = sm.describe_processing_job(ProcessingJobName=job_name)
        status = d["ProcessingJobStatus"]
        print(f"   狀態：{status}")
        if status in ("Completed", "Failed", "Stopped"):
            if status != "Completed":
                print("   失敗原因：", d.get("FailureReason"))
            break
        time.sleep(20)

    if status == "Completed":
        print(f"6. 結果：s3://{BUCKET}/{PREFIX}/output/predictions.json")
    return status


if __name__ == "__main__":
    main()
