#!/usr/bin/env python3
"""
CSR Admin Bootstrap Script
===========================
Run this ONCE to create the initial admin user in S3.

Usage:
    AWS_REGION=ap-south-1 \
    S3_BUCKET_NAME=instance-rds-extend \
    python deploy/seed_admin.py

Or set env vars in your shell before running.
"""
import boto3
import bcrypt
import json
import uuid
import os
from datetime import datetime, timezone
from getpass import getpass

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "instance-rds-extend")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")


def main():
    print("=" * 55)
    print("  CSR — Cloud Server Resurrector: Admin Bootstrap")
    print("=" * 55)
    print(f"\nTarget bucket : {S3_BUCKET}")
    print(f"Region        : {AWS_REGION}\n")

    username = input("Admin username [admin]: ").strip() or "admin"
    email    = input("Admin email   : ").strip()
    password = getpass("Admin password: ")
    confirm  = getpass("Confirm password: ")

    if password != confirm:
        print("\n❌ Passwords do not match. Aborting.")
        return

    if len(password) < 8:
        print("\n❌ Password must be at least 8 characters. Aborting.")
        return

    s3 = boto3.client("s3", region_name=AWS_REGION)

    # Check if users.json already exists
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key="users.json")
        existing = json.loads(response["Body"].read().decode("utf-8"))
        if any(u.get("username") == username for u in existing):
            print(f"\n⚠️  User '{username}' already exists in users.json. Aborting.")
            return
    except s3.exceptions.NoSuchKey:
        existing = []
    except Exception as e:
        print(f"\n❌ Error reading S3: {e}")
        return

    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(12)).decode("utf-8")

    admin_user = {
        "id": str(uuid.uuid4()),
        "username": username,
        "email": email,
        "password_hash": password_hash,
        "role": "admin",
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "is_active": True,
    }

    existing.append(admin_user)

    try:
        s3.put_object(
            Bucket=S3_BUCKET,
            Key="users.json",
            Body=json.dumps(existing, indent=2).encode("utf-8"),
            ContentType="application/json",
        )
        print(f"\n✅ Admin user '{username}' created successfully in s3://{S3_BUCKET}/users.json")
        print(f"   User ID : {admin_user['id']}")
        print(f"   Role    : admin")
        print("\nYou can now log in to the CSR portal with these credentials.")
    except Exception as e:
        print(f"\n❌ Failed to write to S3: {e}")


if __name__ == "__main__":
    main()
