import boto3
import os
import json
import logging
from datetime import datetime, timezone
from typing import List, Dict, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
UAT_TAG_KEY = os.environ.get("UAT_TAG_KEY", "TURN_UP")
UAT_TAG_VALUE = os.environ.get("UAT_TAG_VALUE", "UAT_EXTEND")
CSR_PROTECTED_TAG = "EXTEND_UNTIL"
CSR_LAMBDA_ARN = os.environ.get("CSR_LAMBDA_ARN", "")
SCHEDULER_ROLE_ARN = os.environ.get("SCHEDULER_ROLE_ARN", "")

_ec2 = None
_rds = None
_scheduler = None


def _ec2_client():
    global _ec2
    if _ec2 is None:
        _ec2 = boto3.client("ec2", region_name=AWS_REGION)
    return _ec2


def _rds_client():
    global _rds
    if _rds is None:
        _rds = boto3.client("rds", region_name=AWS_REGION)
    return _rds


def _scheduler_client():
    global _scheduler
    if _scheduler is None:
        _scheduler = boto3.client("scheduler", region_name=AWS_REGION)
    return _scheduler


# ─── EC2 ───────────────────────────────────────────────────────────────────

def discover_ec2_by_tag() -> List[Dict]:
    """Find EC2 instances tagged TURN_UP=UAT_EXTEND."""
    ec2 = _ec2_client()
    try:
        response = ec2.describe_instances(
            Filters=[
                {"Name": f"tag:{UAT_TAG_KEY}", "Values": [UAT_TAG_VALUE]},
                {"Name": "instance-state-name",
                 "Values": ["running", "stopped", "stopping", "pending"]},
            ]
        )
        result = []
        for res in response.get("Reservations", []):
            for inst in res.get("Instances", []):
                tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                result.append({
                    "instance_id": inst["InstanceId"],
                    "type": "EC2",
                    "display_name": tags.get("Name", inst["InstanceId"]),
                    "state": inst["State"]["Name"],
                    "region": AWS_REGION,
                    "protected_until": tags.get(CSR_PROTECTED_TAG),
                })
        return result
    except ClientError as e:
        logger.error("discover_ec2_by_tag error: %s", e)
        return []


def get_ec2_status(instance_id: str) -> str:
    ec2 = _ec2_client()
    try:
        r = ec2.describe_instances(InstanceIds=[instance_id])
        for res in r.get("Reservations", []):
            for inst in res.get("Instances", []):
                return inst["State"]["Name"]
    except ClientError:
        pass
    return "unknown"


def start_ec2(instance_id: str) -> bool:
    try:
        _ec2_client().start_instances(InstanceIds=[instance_id])
        return True
    except ClientError as e:
        logger.error("start_ec2 %s: %s", instance_id, e)
        return False


def stop_ec2(instance_id: str) -> bool:
    try:
        _ec2_client().stop_instances(InstanceIds=[instance_id])
        return True
    except ClientError as e:
        logger.error("stop_ec2 %s: %s", instance_id, e)
        return False


def apply_protection_tag_ec2(instance_id: str, until_utc: str) -> bool:
    try:
        _ec2_client().create_tags(
            Resources=[instance_id],
            Tags=[{"Key": CSR_PROTECTED_TAG, "Value": until_utc}],
        )
        return True
    except ClientError as e:
        logger.error("apply_protection_tag_ec2 %s: %s", instance_id, e)
        return False


def remove_protection_tag_ec2(instance_id: str) -> bool:
    try:
        _ec2_client().delete_tags(
            Resources=[instance_id],
            Tags=[{"Key": CSR_PROTECTED_TAG}],
        )
        return True
    except ClientError as e:
        logger.error("remove_protection_tag_ec2 %s: %s", instance_id, e)
        return False


# ─── RDS ───────────────────────────────────────────────────────────────────

def get_rds_status(db_id: str) -> str:
    try:
        r = _rds_client().describe_db_instances(DBInstanceIdentifier=db_id)
        instances = r.get("DBInstances", [])
        return instances[0].get("DBInstanceStatus", "unknown") if instances else "unknown"
    except ClientError:
        return "unknown"


def _get_rds_arn(db_id: str) -> Optional[str]:
    try:
        r = _rds_client().describe_db_instances(DBInstanceIdentifier=db_id)
        instances = r.get("DBInstances", [])
        return instances[0].get("DBInstanceArn") if instances else None
    except ClientError:
        return None


def start_rds(db_id: str) -> bool:
    try:
        _rds_client().start_db_instance(DBInstanceIdentifier=db_id)
        return True
    except ClientError as e:
        logger.error("start_rds %s: %s", db_id, e)
        return False


def stop_rds(db_id: str) -> bool:
    try:
        _rds_client().stop_db_instance(DBInstanceIdentifier=db_id)
        return True
    except ClientError as e:
        logger.error("stop_rds %s: %s", db_id, e)
        return False


def apply_protection_tag_rds(db_id: str, until_utc: str) -> bool:
    arn = _get_rds_arn(db_id)
    if not arn:
        return False
    try:
        _rds_client().add_tags_to_resource(
            ResourceName=arn,
            Tags=[{"Key": CSR_PROTECTED_TAG, "Value": until_utc}],
        )
        return True
    except ClientError as e:
        logger.error("apply_protection_tag_rds %s: %s", db_id, e)
        return False


def remove_protection_tag_rds(db_id: str) -> bool:
    arn = _get_rds_arn(db_id)
    if not arn:
        return False
    try:
        _rds_client().remove_tags_from_resource(
            ResourceName=arn, TagKeys=[CSR_PROTECTED_TAG]
        )
        return True
    except ClientError as e:
        logger.error("remove_protection_tag_rds %s: %s", db_id, e)
        return False


# ─── EventBridge Scheduler (one-time per extension) ───────────────────────

def create_expiry_schedule(extension_id: str, instance_id: str,
                           expire_at_utc: datetime) -> bool:
    """
    Creates a one-time EventBridge Scheduler that fires at expire_at_utc
    and invokes the CSR Lambda to stop the instance and clean up.
    The schedule auto-deletes after firing (ActionAfterCompletion=DELETE).
    """
    if not CSR_LAMBDA_ARN or not SCHEDULER_ROLE_ARN:
        logger.warning(
            "CSR_LAMBDA_ARN or SCHEDULER_ROLE_ARN not configured — "
            "expiry scheduler not created. Instance will not auto-stop."
        )
        return False

    scheduler = _scheduler_client()
    # Sanitise schedule name — must be alphanumeric + hyphens
    schedule_name = f"csr-expire-{extension_id[:8]}"
    at_expr = expire_at_utc.strftime("at(%Y-%m-%dT%H:%M:%S)")

    payload = {
        "source": "csr-scheduler",
        "action": "expire_extension",
        "extension_id": extension_id,
        "instance_id": instance_id,
    }

    try:
        scheduler.create_schedule(
            Name=schedule_name,
            ScheduleExpression=at_expr,
            ScheduleExpressionTimezone="UTC",
            Target={
                "Arn": CSR_LAMBDA_ARN,
                "RoleArn": SCHEDULER_ROLE_ARN,
                "Input": json.dumps(payload),
            },
            FlexibleTimeWindow={"Mode": "OFF"},
            ActionAfterCompletion="DELETE",
        )
        logger.info("Created expiry schedule %s at %s", schedule_name, at_expr)
        return True
    except ClientError as e:
        logger.error("create_expiry_schedule error: %s", e)
        return False


def delete_expiry_schedule(extension_id: str) -> bool:
    """Cancel a pending expiry schedule (called on manual stop or time update)."""
    schedule_name = f"csr-expire-{extension_id[:8]}"
    try:
        _scheduler_client().delete_schedule(Name=schedule_name)
        return True
    except ClientError as e:
        err_code = e.response["Error"]["Code"]
        if err_code in ("ResourceNotFoundException", "404"):
            return True  # Already fired/deleted — that's fine
        logger.error("delete_expiry_schedule error: %s", e)
        return False
