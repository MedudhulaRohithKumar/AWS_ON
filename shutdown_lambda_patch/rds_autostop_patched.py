"""
PATCHED: RDS_AutoStop_6PM Lambda
=================================
Changes from original (marked with ─── CSR ─── blocks):
  • Added _is_csr_protected_rds() helper that reads EXTEND_UNTIL tag via ARN.
  • Added a `continue` guard inside the stop loop to skip protected RDS instances.
"""
import boto3
import datetime

region = 'ap-south-1'
instances = ['uat-db']


def lambda_handler(event, context):
    rds = boto3.client('rds', region_name=region)

    for db_id in instances:
        response = rds.describe_db_instances(DBInstanceIdentifier=db_id)

        for r in response['DBInstances']:
            db_instance_name = r['DBInstanceIdentifier']
            db_status        = r['DBInstanceStatus']
            db_arn           = r.get('DBInstanceArn', '')

            print(f"{db_instance_name} | {db_status}")

            if db_status == 'stopped':
                print(f"DB Status is already {db_status}")
            else:
                # ─── CSR: Skip RDS instances with an active EXTEND_UNTIL tag ─
                if _is_csr_protected_rds(rds, db_arn):
                    print(f"[CSR] Skipping {db_id} — EXTEND_UNTIL tag is active")
                    continue
                # ─────────────────────────────────────────────────────────────
                rds.stop_db_instance(DBInstanceIdentifier=db_id)
                print(f"Stopped RDS instance: {db_id}")


# ─── CSR Helper — DO NOT REMOVE ────────────────────────────────────────────
def _is_csr_protected_rds(rds_client, db_arn: str) -> bool:
    """
    Returns True only if the RDS instance has an EXTEND_UNTIL tag
    whose value is a valid ISO-8601 UTC timestamp still in the future.

    Uses list_tags_for_resource() with the DB ARN (already available from
    describe_db_instances, so no extra API call is needed).
    """
    if not db_arn:
        return False
    try:
        tags_response = rds_client.list_tags_for_resource(ResourceName=db_arn)
        tags = {t['Key']: t['Value'] for t in tags_response.get('TagList', [])}

        protected_until_str = tags.get('EXTEND_UNTIL')
        if not protected_until_str:
            return False

        protected_until = datetime.datetime.fromisoformat(
            protected_until_str.replace('Z', '+00:00')
        )
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return protected_until > now_utc
    except Exception as e:
        print(f"[CSR] Error checking EXTEND_UNTIL tag for {db_arn}: {e}")
        return False  # Fail open — stop the instance if we can't check
# ───────────────────────────────────────────────────────────────────────────
