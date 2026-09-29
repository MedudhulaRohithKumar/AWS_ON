#!/usr/bin/env python3
"""
CSR Admin Bootstrap Script
===========================
Run this script to create the initial admin user in your S3 bucket.

Usage:
    export S3_BUCKET_NAME=your-new-bucket-name
    export AWS_REGION=ap-south-1
    python3 seed_admin.py

Or simply run `python3 seed_admin.py` and follow the prompts.
"""
import os
import json
import uuid
from datetime import datetime, timezone
from getpass import getpass

try:
    import bcrypt
except ImportError:
    print("❌ Error: 'bcrypt' is not installed.")
    print("Please install dependencies: pip install bcrypt boto3")
    exit(1)

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:
    boto3 = None


def main():
    print("=" * 60)
    print("  CSR — Cloud Server Resurrector: Admin Bootstrap")
    print("=" * 60)

    default_bucket = os.environ.get("S3_BUCKET_NAME", "")
    bucket_input = input(f"Target S3 Bucket [{default_bucket or 'required'}]: ").strip()
    bucket_name = bucket_input or default_bucket

    if not bucket_name:
        print("❌ S3 Bucket name is required. Aborting.")
        return

    default_region = os.environ.get("AWS_REGION", "ap-south-1")
    region_input = input(f"AWS Region [{default_region}]: ").strip()
    aws_region = region_input or default_region

    print("-" * 60)
    username = input("Admin username [admin]: ").strip() or "admin"
    email = input("Admin email [admin@example.com]: ").strip() or "admin@example.com"
    password = getpass("Admin password (min 8 chars): ")
    confirm = getpass("Confirm password: ")

    if password != confirm:
        print("\n❌ Passwords do not match. Aborting.")
        return

    if len(password) < 8:
        print("\n❌ Password must be at least 8 characters. Aborting.")
        return

    # Generate bcrypt hash (12 rounds)
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

    # Attempt to read existing users from S3 if boto3 is available
    users = []
    s3_success = False

    if boto3:
        try:
            s3 = boto3.client("s3", region_name=aws_region)
            try:
                response = s3.get_object(Bucket=bucket_name, Key="users.json")
                existing = json.loads(response["Body"].read().decode("utf-8"))
                if isinstance(existing, list):
                    # Replace user if username already exists, or append
                    users = [u for u in existing if u.get("username") != username]
            except ClientError as e:
                if e.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                    print(f"⚠️  Warning while checking existing S3 users: {e}")

            users.append(admin_user)

            s3.put_object(
                Bucket=bucket_name,
                Key="users.json",
                Body=json.dumps(users, indent=2).encode("utf-8"),
                ContentType="application/json",
            )
            s3_success = True
            print(f"\n✅ Admin user '{username}' successfully uploaded to s3://{bucket_name}/users.json")
        except Exception as e:
            print(f"\n⚠️  Could not write directly to S3: {e}")
            print("   (Don't worry, a local users.json has been created below so you can upload it manually).")
    else:
        users = [admin_user]

    # Always write a local users.json as backup / manual upload option
    local_filename = "users.json"
    with open(local_filename, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

    print(f"\n📁 Local copy saved: {os.path.abspath(local_filename)}")
    print("=" * 60)
    print("Summary:")
    print(f"  Username : {username}")
    print(f"  Role     : admin")
    print(f"  Bucket   : {bucket_name}")
    print(f"  S3 Status: {'Uploaded ✅' if s3_success else 'Upload manually to s3://' + bucket_name + '/users.json ⚠️'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
