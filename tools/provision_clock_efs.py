"""
冪等佈建雲端空滿時計共用庫（ADR-327）
====================================
在 us-east-1 建／對齊：EFS、NFS SG、mount target、access point、
task role 權限、worker task／service，並讓網站 task 掛同一份檔。

不把金鑰寫進檔案。沿用現況 youbike-backend 的環境變數與角色。
需已設定 AWS CLI 憑證（或環境變數）。

    python tools/provision_clock_efs.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

REGION = "us-east-1"
CLUSTER = "youbike"
BACKEND_SERVICE = "youbike-backend"
WORKER_SERVICE = "youbike-clock-worker"
BACKEND_FAMILY = "youbike-backend"
WORKER_FAMILY = "youbike-clock-worker"
EFS_NAME = "youbike-clock"
EFS_SG_NAME = "youbike-efs-sg"
BACKEND_SG = "sg-09e0635d293224992"
SUBNET = "subnet-04853fd4be8b82556"
CLOCK_PATH = "/data/runtime/service_clock.db"
VOLUME_NAME = "clock-data"
MOUNT_PATH = "/data/runtime"
LOG_GROUP = "/ecs/youbike-clock-worker"
TASK_ROLE_NAME = "youbike-ecs-task"
POLICY_NAME = "efs-youbike-clock"


def aws(*args: str, input_text: str | None = None) -> dict | list | str:
    cmd = ["aws", *args, "--region", REGION, "--output", "json"]
    result = subprocess.run(
        cmd, input=input_text, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"aws {' '.join(args)} failed:\n{result.stderr}")
    text = (result.stdout or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def log(message: str) -> None:
    try:
        print(message, flush=True)
    except UnicodeEncodeError:
        print(message.encode("utf-8", "replace").decode("ascii", "replace"), flush=True)


def ensure_efs_sg(vpc_id: str) -> str:
    found = aws(
        "ec2", "describe-security-groups",
        "--filters", f"Name=group-name,Values={EFS_SG_NAME}",
        f"Name=vpc-id,Values={vpc_id}",
    )
    groups = found.get("SecurityGroups") or []
    if groups:
        sg_id = groups[0]["GroupId"]
        log(f"EFS SG 已存在 {sg_id}")
    else:
        created = aws(
            "ec2", "create-security-group",
            "--group-name", EFS_SG_NAME,
            "--description", "YouBike clock EFS NFS from ECS tasks only",
            "--vpc-id", vpc_id,
        )
        sg_id = created["GroupId"]
        aws("ec2", "create-tags", "--resources", sg_id,
            "--tags", f"Key=Name,Value={EFS_SG_NAME}")
        log(f"已建 EFS SG {sg_id}")
    perms = aws("ec2", "describe-security-groups", "--group-ids", sg_id)
    ingress = (perms["SecurityGroups"][0].get("IpPermissions") or [])
    already = any(
        p.get("FromPort") == 2049
        and any(pair.get("GroupId") == BACKEND_SG
                for pair in p.get("UserIdGroupPairs") or [])
        for p in ingress
    )
    if not already:
        aws(
            "ec2", "authorize-security-group-ingress",
            "--group-id", sg_id,
            "--protocol", "tcp",
            "--port", "2049",
            "--source-group", BACKEND_SG,
        )
        log("已開 NFS 2049（僅 ECS task SG）")
    return sg_id


def ensure_efs() -> str:
    existing = aws(
        "efs", "describe-file-systems",
        "--query", f"FileSystems[?Name=='{EFS_NAME}']",
    )
    if existing:
        fs_id = existing[0]["FileSystemId"]
        log(f"EFS 已存在 {fs_id}")
        return fs_id
    created = aws(
        "efs", "create-file-system",
        "--encrypted",
        "--performance-mode", "generalPurpose",
        "--throughput-mode", "bursting",
        "--tags", f"Key=Name,Value={EFS_NAME}",
        "--creation-token", "youbike-clock-efs",
    )
    fs_id = created["FileSystemId"]
    log(f"已建 EFS {fs_id}，等待 available")
    for _ in range(30):
        info = aws("efs", "describe-file-systems", "--file-system-id", fs_id)
        state = info["FileSystems"][0]["LifeCycleState"]
        if state == "available":
            return fs_id
        time.sleep(5)
    raise RuntimeError("EFS 未在時限內 available")


def ensure_mount_target(fs_id: str, sg_id: str) -> None:
    targets = aws("efs", "describe-mount-targets", "--file-system-id", fs_id)
    if targets.get("MountTargets"):
        log(f"mount target 已存在 {targets['MountTargets'][0]['MountTargetId']}")
        return
    aws(
        "efs", "create-mount-target",
        "--file-system-id", fs_id,
        "--subnet-id", SUBNET,
        "--security-groups", sg_id,
    )
    log("已建 mount target，等待 available")
    for _ in range(36):
        try:
            again = aws("efs", "describe-mount-targets", "--file-system-id", fs_id)
        except RuntimeError as exc:
            if "Could not connect" in str(exc):
                time.sleep(5)
                continue
            raise
        states = [t["LifeCycleState"] for t in again.get("MountTargets") or []]
        if states and all(state == "available" for state in states):
            return
        time.sleep(5)
    raise RuntimeError("mount target 未在時限內 available")


def ensure_access_point(fs_id: str) -> str:
    points = aws("efs", "describe-access-points", "--file-system-id", fs_id)
    for point in points.get("AccessPoints") or []:
        tags = {t["Key"]: t["Value"] for t in point.get("Tags") or []}
        if tags.get("Name") == EFS_NAME:
            log(f"access point 已存在 {point['AccessPointId']}")
            return point["AccessPointId"]
    created = aws(
        "efs", "create-access-point",
        "--file-system-id", fs_id,
        "--posix-user", "Uid=0,Gid=0",
        "--root-directory",
        "Path=/clock,CreationInfo={OwnerUid=0,OwnerGid=0,Permissions=0755}",
        "--tags", f"Key=Name,Value={EFS_NAME}",
    )
    log(f"已建 access point {created['AccessPointId']}")
    return created["AccessPointId"]


def ensure_iam(fs_id: str) -> None:
    account = aws("sts", "get-caller-identity")["Account"]
    resource = f"arn:aws:elasticfilesystem:{REGION}:{account}:file-system/{fs_id}"
    doc = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Action": [
                "elasticfilesystem:ClientMount",
                "elasticfilesystem:ClientWrite",
                "elasticfilesystem:ClientRootAccess",
            ],
            "Resource": resource,
        }],
    }
    aws(
        "iam", "put-role-policy",
        "--role-name", TASK_ROLE_NAME,
        "--policy-name", POLICY_NAME,
        "--policy-document", json.dumps(doc),
    )
    log(f"task role 已對齊 EFS 權限 {fs_id}")


def ensure_log_group() -> None:
    groups = aws(
        "logs", "describe-log-groups",
        "--log-group-name-prefix", LOG_GROUP,
    )
    names = [g["logGroupName"] for g in groups.get("logGroups") or []]
    if LOG_GROUP in names:
        log(f"log group 已存在 {LOG_GROUP}")
        return
    aws("logs", "create-log-group", "--log-group-name", LOG_GROUP)
    log(f"已建 log group {LOG_GROUP}")


def _clean_task(td: dict) -> dict:
    keep = (
        "family", "taskRoleArn", "executionRoleArn", "networkMode",
        "containerDefinitions", "volumes", "requiresCompatibilities",
        "cpu", "memory",
    )
    return {key: td[key] for key in keep if key in td}


def _env_with(env: list, extra: dict[str, str]) -> list:
    merged = {item["name"]: item["value"] for item in env or []}
    merged.update(extra)
    return [{"name": key, "value": value} for key, value in merged.items()]


def _volume(fs_id: str, access_point_id: str) -> dict:
    return {
        "name": VOLUME_NAME,
        "efsVolumeConfiguration": {
            "fileSystemId": fs_id,
            "transitEncryption": "ENABLED",
            "authorizationConfig": {
                "accessPointId": access_point_id,
                "iam": "ENABLED",
            },
        },
    }


def _mount() -> dict:
    return {
        "sourceVolume": VOLUME_NAME,
        "containerPath": MOUNT_PATH,
        "readOnly": False,
    }


def register_backend(fs_id: str, access_point_id: str) -> str:
    raw = aws("ecs", "describe-task-definition", "--task-definition", BACKEND_FAMILY)
    td = _clean_task(raw["taskDefinition"])
    container = td["containerDefinitions"][0]
    container["environment"] = _env_with(container.get("environment") or [], {
        "YOUBIKE_CLOCK_DB_PATH": CLOCK_PATH,
        "SERVICE_CLOCK_EXTERNAL": "1",
    })
    container["mountPoints"] = [_mount()]
    td["volumes"] = [_volume(fs_id, access_point_id)]
    registered = aws(
        "ecs", "register-task-definition",
        "--cli-input-json", json.dumps(td),
    )
    arn = registered["taskDefinition"]["taskDefinitionArn"]
    log(f"已註冊網站 task {arn}")
    return arn


def register_worker(fs_id: str, access_point_id: str) -> str:
    raw = aws("ecs", "describe-task-definition", "--task-definition", BACKEND_FAMILY)
    src = raw["taskDefinition"]
    container = json.loads(json.dumps(src["containerDefinitions"][0]))
    container["name"] = WORKER_FAMILY
    container["command"] = ["python", "tools/service_clock_worker.py"]
    container["portMappings"] = []
    container["environment"] = _env_with(container.get("environment") or [], {
        "YOUBIKE_CLOCK_DB_PATH": CLOCK_PATH,
    })
    container["mountPoints"] = [_mount()]
    container["logConfiguration"] = {
        "logDriver": "awslogs",
        "options": {
            "awslogs-group": LOG_GROUP,
            "awslogs-region": REGION,
            "awslogs-stream-prefix": "ecs",
        },
    }
    td = {
        "family": WORKER_FAMILY,
        "taskRoleArn": src["taskRoleArn"],
        "executionRoleArn": src["executionRoleArn"],
        "networkMode": src["networkMode"],
        "requiresCompatibilities": src["requiresCompatibilities"],
        "cpu": "256",
        "memory": "512",
        "containerDefinitions": [container],
        "volumes": [_volume(fs_id, access_point_id)],
    }
    registered = aws(
        "ecs", "register-task-definition",
        "--cli-input-json", json.dumps(td),
    )
    arn = registered["taskDefinition"]["taskDefinitionArn"]
    log(f"已註冊收集 task {arn}")
    return arn


def update_backend_service(task_arn: str) -> None:
    aws(
        "ecs", "update-service",
        "--cluster", CLUSTER,
        "--service", BACKEND_SERVICE,
        "--task-definition", task_arn,
    )
    log("網站 service 已改掛 EFS")


def ensure_worker_service(task_arn: str) -> None:
    services = aws(
        "ecs", "describe-services",
        "--cluster", CLUSTER,
        "--services", WORKER_SERVICE,
    )
    active = [
        s for s in services.get("services") or []
        if s.get("status") != "INACTIVE"
    ]
    if active:
        aws(
            "ecs", "update-service",
            "--cluster", CLUSTER,
            "--service", WORKER_SERVICE,
            "--task-definition", task_arn,
            "--desired-count", "1",
        )
        log("收集 service 已更新")
        return
    aws(
        "ecs", "create-service",
        "--cluster", CLUSTER,
        "--service-name", WORKER_SERVICE,
        "--task-definition", task_arn,
        "--desired-count", "1",
        "--launch-type", "FARGATE",
        "--platform-version", "LATEST",
        "--network-configuration",
        (
            f"awsvpcConfiguration={{subnets=[{SUBNET}],"
            f"securityGroups=[{BACKEND_SG}],assignPublicIp=ENABLED}}"
        ),
        "--deployment-configuration",
        "minimumHealthyPercent=0,maximumPercent=100",
    )
    log("已建收集 service")


def main() -> int:
    vpc = aws("ec2", "describe-subnets", "--subnet-ids", SUBNET)["Subnets"][0]["VpcId"]
    sg_id = ensure_efs_sg(vpc)
    fs_id = ensure_efs()
    ensure_mount_target(fs_id, sg_id)
    access_point_id = ensure_access_point(fs_id)
    ensure_iam(fs_id)
    ensure_log_group()
    backend_arn = register_backend(fs_id, access_point_id)
    worker_arn = register_worker(fs_id, access_point_id)
    update_backend_service(backend_arn)
    ensure_worker_service(worker_arn)
    log("ADR-327 佈建完成。worker 要等含 service_clock_worker 的 image 才會穩。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"失敗：{exc}", file=sys.stderr)
        sys.exit(1)
