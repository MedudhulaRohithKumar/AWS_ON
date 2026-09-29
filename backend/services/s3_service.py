import json
import boto3
import os
import logging
from typing import List, Dict, Any, Optional
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

S3_BUCKET = os.environ.get("S3_BUCKET_NAME", "instance-rds-extend")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3", region_name=AWS_REGION)
    return _s3_client


KEYS = {
    "users": "users.json",
    "activity": "activity.json",
    "servers": "servers.json",
    "extensions": "extensions.json",
}


# ─── Core Read / Write ─────────────────────────────────────────────────────

def read_json(key: str) -> List[Dict[str, Any]]:
    """Read a JSON list from S3. Returns [] if file doesn't exist yet."""
    s3 = get_s3_client()
    file_key = KEYS.get(key, key)
    try:
        response = s3.get_object(Bucket=S3_BUCKET, Key=file_key)
        data = json.loads(response["Body"].read().decode("utf-8"))
        return data if isinstance(data, list) else []
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return []
        raise


def write_json(key: str, data: List[Dict[str, Any]]) -> None:
    """Write a JSON list to S3."""
    s3 = get_s3_client()
    file_key = KEYS.get(key, key)
    s3.put_object(
        Bucket=S3_BUCKET,
        Key=file_key,
        Body=json.dumps(data, indent=2, default=str).encode("utf-8"),
        ContentType="application/json",
    )


# ─── Users ─────────────────────────────────────────────────────────────────

DEFAULT_ADMIN_USER = {
    "id": "13fe6db3-7815-42a3-bcb7-982cb0fe3983",
    "username": "admin",
    "email": "admin@example.com",
    "password_hash": "$2b$12$h1xFPStyH5FikkcDVZ92YeOZOPxIIo6ASkLjg4PsMw084Kz1xo1ia",  # bcrypt hash of 'admin123'
    "role": "admin",
    "created_at": "2026-09-29T20:16:00.297298Z",
    "is_active": True,
    "assigned_servers": [],
}


def get_all_users() -> List[Dict]:
    try:
        users = read_json("users")
    except Exception as e:
        logger.warning(f"Error reading users from S3: {e}")
        users = []

    if not users:
        try:
            write_json("users", [DEFAULT_ADMIN_USER])
            logger.info("Auto-seeded default admin user to S3 users.json")
        except Exception as e:
            logger.warning(f"Could not persist auto-seeded admin user to S3: {e}")
        return [DEFAULT_ADMIN_USER]

    # If users exist but admin is missing, append default admin
    if not any(u.get("username") == "admin" for u in users):
        users.append(DEFAULT_ADMIN_USER)
        try:
            write_json("users", users)
            logger.info("Appended default admin user to S3 users.json")
        except Exception as e:
            logger.warning(f"Could not persist default admin to S3: {e}")

    return users


def get_user_by_username(username: str) -> Optional[Dict]:
    users = get_all_users()
    user = next((u for u in users if u.get("username") == username), None)
    if not user and username == "admin":
        return DEFAULT_ADMIN_USER
    return user


def get_user_by_id(user_id: str) -> Optional[Dict]:
    users = get_all_users()
    user = next((u for u in users if u.get("id") == user_id), None)
    if not user and user_id == DEFAULT_ADMIN_USER["id"]:
        return DEFAULT_ADMIN_USER
    return user


def create_user(user_data: Dict) -> Dict:
    users = get_all_users()
    users.append(user_data)
    write_json("users", users)
    return user_data


def update_user(user_id: str, updates: Dict) -> Optional[Dict]:
    users = get_all_users()
    for i, u in enumerate(users):
        if u["id"] == user_id:
            users[i].update(updates)
            write_json("users", users)
            return users[i]
    return None


# ─── Servers ───────────────────────────────────────────────────────────────

def get_all_servers() -> List[Dict]:
    return read_json("servers")


def get_server_by_id(server_id: str) -> Optional[Dict]:
    return next((s for s in get_all_servers() if s["id"] == server_id), None)


def get_server_by_instance_id(instance_id: str) -> Optional[Dict]:
    return next((s for s in get_all_servers() if s["instance_id"] == instance_id), None)


def create_server(server_data: Dict) -> Dict:
    servers = get_all_servers()
    servers.append(server_data)
    write_json("servers", servers)
    return server_data


def update_server(server_id: str, updates: Dict) -> Optional[Dict]:
    servers = get_all_servers()
    for i, s in enumerate(servers):
        if s["id"] == server_id:
            servers[i].update(updates)
            write_json("servers", servers)
            return servers[i]
    return None


# ─── Activity ──────────────────────────────────────────────────────────────

def get_all_activity() -> List[Dict]:
    return read_json("activity")


def log_activity(activity_data: Dict) -> None:
    activities = get_all_activity()
    activities.append(activity_data)
    # Cap at 10,000 entries to keep S3 file manageable
    if len(activities) > 10000:
        activities = activities[-10000:]
    write_json("activity", activities)


# ─── Extensions ────────────────────────────────────────────────────────────

def get_all_extensions() -> List[Dict]:
    return read_json("extensions")


def get_active_extension_for_instance(instance_id: str) -> Optional[Dict]:
    return next(
        (e for e in get_all_extensions()
         if e["instance_id"] == instance_id and e["status"] == "active"),
        None,
    )


def create_extension(extension_data: Dict) -> Dict:
    extensions = get_all_extensions()
    extensions.append(extension_data)
    write_json("extensions", extensions)
    return extension_data


def update_extension(extension_id: str, updates: Dict) -> Optional[Dict]:
    extensions = get_all_extensions()
    for i, e in enumerate(extensions):
        if e["id"] == extension_id:
            extensions[i].update(updates)
            write_json("extensions", extensions)
            return extensions[i]
    return None
