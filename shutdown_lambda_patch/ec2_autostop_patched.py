"""
PATCHED: Instances_AutoStop_6PM Lambda
======================================
Changes from original (marked with ─── CSR ─── blocks):
  • Added _is_csr_protected() helper that checks the EXTEND_UNTIL tag.
  • Added a `continue` guard inside the stop loop to skip protected instances.

This ensures that when a user extends only Instance A via the CSR portal,
Instances B and C still stop as normal at 6 PM while A stays running.
"""
import boto3
import datetime


def lambda_handler(event, context):
    ec2 = boto3.client('ec2')

    # Fetch all EC2 instances (original filter — unchanged)
    response = ec2.describe_instances(
        Filters=[
            {
                'Name': 'tag:environment',
                'Values': ['Dev', 'UAT', 'DevOps']
            }
        ]
    )

    instances_to_stop = []

    for reservation in response['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            state = instance['State']['Name']
            print(f"Instance {instance_id} is in state: {state}")

            if state == 'running':
                # ─── CSR: Skip instances with an active EXTEND_UNTIL tag ────
                if _is_csr_protected(instance):
                    print(f"[CSR] Skipping {instance_id} — EXTEND_UNTIL tag is active")
                    continue
                # ─────────────────────────────────────────────────────────────
                instances_to_stop.append(instance_id)

    if instances_to_stop:
        print(f"Stopping instances: {instances_to_stop}")
        ec2.stop_instances(InstanceIds=instances_to_stop)
    else:
        print("No running instances found to stop")

    return {
        'statusCode': 200,
        'body': f"Checked and stopped instances: {instances_to_stop}"
    }


# ─── CSR Helper — DO NOT REMOVE ────────────────────────────────────────────
def _is_csr_protected(instance: dict) -> bool:
    """
    Returns True only if the instance has an EXTEND_UNTIL tag
    whose value is a valid ISO-8601 UTC timestamp that is still in the future.

    The tag is applied by the CSR portal when a user extends an instance.
    It is automatically removed by CSR when the extension expires or the
    user manually stops the instance.
    """
    tags = {t['Key']: t['Value'] for t in instance.get('Tags', [])}
    protected_until_str = tags.get('EXTEND_UNTIL')

    if not protected_until_str:
        return False

    try:
        protected_until = datetime.datetime.fromisoformat(
            protected_until_str.replace('Z', '+00:00')
        )
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        return protected_until > now_utc
    except (ValueError, TypeError):
        # Malformed tag value — treat as no protection
        return False
# ───────────────────────────────────────────────────────────────────────────
