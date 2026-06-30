from fastapi import APIRouter, HTTPException, Depends, Request
from models.schemas import CreateUserRequest, UpdateUserRequest, AddServerRequest
from services.s3_service import (
    get_all_users, get_user_by_id, create_user, update_user,
    get_all_servers, get_server_by_id, create_server, update_server,
    get_all_activity, get_all_extensions, log_activity,
)
from services.auth_service import hash_password
from middleware.auth_middleware import require_admin
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/admin", tags=["admin"])

SHUTDOWN_HOUR = 18   # 6 PM UTC+5:30 equivalent; stored extensions are in UTC
STARTUP_HOUR  = 9    # 9 AM


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    return fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )


def _now_str() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_user(u: dict) -> dict:
    safe = {k: v for k, v in u.items() if k != "password_hash"}
    if "assigned_servers" not in safe:
        safe["assigned_servers"] = []
    return safe


# ─── User Management ───────────────────────────────────────────────────────

@router.get("/users")
async def list_users(current_user: dict = Depends(require_admin)):
    return [_safe_user(u) for u in get_all_users()]


@router.post("/users")
async def add_user(body: CreateUserRequest, request: Request,
                   current_user: dict = Depends(require_admin)):
    if any(u["username"] == body.username for u in get_all_users()):
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = {
        "id": str(uuid.uuid4()),
        "username": body.username,
        "email": body.email,
        "password_hash": hash_password(body.password),
        "role": body.role,
        "created_at": _now_str(),
        "is_active": True,
        "assigned_servers": body.assigned_servers,
    }
    create_user(new_user)
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "ADD_USER",
        "resource_id": new_user["id"],
        "resource_type": "USER",
        "details": f"Created user '{body.username}' with role '{body.role}'",
        "timestamp": _now_str(),
        "ip_address": _get_ip(request),
    })
    return _safe_user(new_user)


@router.put("/users/{user_id}")
async def update_user_endpoint(user_id: str, body: UpdateUserRequest,
                               request: Request,
                               current_user: dict = Depends(require_admin)):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    updates = {}
    if body.email is not None:
        updates["email"] = body.email
    if body.role is not None:
        updates["role"] = body.role
    if body.is_active is not None:
        updates["is_active"] = body.is_active
    if body.password is not None:
        updates["password_hash"] = hash_password(body.password)
    if body.assigned_servers is not None:
        updates["assigned_servers"] = body.assigned_servers

    updated = update_user(user_id, updates)
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "UPDATE_USER",
        "resource_id": user_id,
        "resource_type": "USER",
        "details": f"Updated user '{user['username']}': fields={list(updates.keys())}",
        "timestamp": _now_str(),
        "ip_address": _get_ip(request),
    })
    return _safe_user(updated)


@router.delete("/users/{user_id}")
async def deactivate_user(user_id: str, request: Request,
                          current_user: dict = Depends(require_admin)):
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate your own account")

    update_user(user_id, {"is_active": False})
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "REMOVE_USER",
        "resource_id": user_id,
        "resource_type": "USER",
        "details": f"Deactivated user '{user['username']}'",
        "timestamp": _now_str(),
        "ip_address": _get_ip(request),
    })
    return {"message": f"User '{user['username']}' deactivated"}


# ─── Server Management ─────────────────────────────────────────────────────

@router.post("/servers")
async def add_server(body: AddServerRequest, request: Request,
                     current_user: dict = Depends(require_admin)):
    if any(s["instance_id"] == body.instance_id for s in get_all_servers()):
        raise HTTPException(status_code=400, detail="Instance ID already registered")

    new_server = {
        "id": str(uuid.uuid4()),
        "instance_id": body.instance_id,
        "type": body.type,
        "display_name": body.display_name,
        "region": body.region or "ap-south-1",
        "added_by": current_user["username"],
        "added_at": _now_str(),
        "is_active": True,
    }
    create_server(new_server)
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "ADD_SERVER",
        "resource_id": body.instance_id,
        "resource_type": body.type,
        "details": f"Added {body.type} '{body.display_name}' ({body.instance_id})",
        "timestamp": _now_str(),
        "ip_address": _get_ip(request),
    })
    return new_server


@router.delete("/servers/{server_id}")
async def remove_server(server_id: str, request: Request,
                        current_user: dict = Depends(require_admin)):
    server = get_server_by_id(server_id)
    if not server:
        raise HTTPException(status_code=404, detail="Server not found")

    update_server(server_id, {"is_active": False})
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "REMOVE_SERVER",
        "resource_id": server["instance_id"],
        "resource_type": server["type"],
        "details": f"Removed '{server['display_name']}' ({server['instance_id']})",
        "timestamp": _now_str(),
        "ip_address": _get_ip(request),
    })
    return {"message": f"Server '{server['display_name']}' removed"}


# ─── Activity Log ──────────────────────────────────────────────────────────

@router.get("/activity")
async def activity_log(current_user: dict = Depends(require_admin)):
    activities = get_all_activity()
    return sorted(activities, key=lambda x: x.get("timestamp", ""), reverse=True)


# ─── Reports ───────────────────────────────────────────────────────────────

def _extra_hours(ext: dict) -> float:
    """
    Calculate hours the instance ran outside normal working time.
    Anything after 6 PM IST (= 12:30 UTC) until 9 AM IST (= 3:30 UTC)
    counts as extra. We approximate using extension start vs end.
    """
    try:
        req_str = ext.get("requested_at", "")
        end_str = ext.get("extended_until", "")
        if not req_str or not end_str:
            return 0.0

        start = datetime.fromisoformat(req_str.replace("Z", "+00:00"))
        end   = datetime.fromisoformat(end_str.replace("Z", "+00:00"))

        # Effective extra time: from whichever is later — request time or 6PM IST
        # 6PM IST = 12:30 UTC
        shutdown_utc = start.replace(hour=12, minute=30, second=0, microsecond=0)
        effective_start = max(start, shutdown_utc)

        if effective_start >= end:
            return 0.0

        return round((end - effective_start).total_seconds() / 3600, 2)
    except Exception:
        return 0.0


@router.get("/reports/extra-hours")
async def extra_hours_report(current_user: dict = Depends(require_admin)):
    extensions = get_all_extensions()
    servers_map = {s["instance_id"]: s["display_name"] for s in get_all_servers()}

    report = []
    for ext in extensions:
        report.append({
            "instance_id": ext["instance_id"],
            "display_name": ext.get("display_name") or servers_map.get(ext["instance_id"], ext["instance_id"]),
            "instance_type": ext.get("instance_type", "EC2"),
            "username": ext["username"],
            "extended_until": ext["extended_until"],
            "requested_at": ext["requested_at"],
            "status": ext["status"],
            "extra_hours": _extra_hours(ext),
        })

    return sorted(report, key=lambda x: x["extra_hours"], reverse=True)


@router.get("/reports/leaderboard")
async def leaderboard(current_user: dict = Depends(require_admin)):
    extensions = get_all_extensions()

    stats: dict = {}
    for ext in extensions:
        uname = ext["username"]
        if uname not in stats:
            stats[uname] = {
                "username": uname,
                "total_extensions": 0,
                "total_extra_hours": 0.0,
                "active_extensions": 0,
            }
        stats[uname]["total_extensions"] += 1
        stats[uname]["total_extra_hours"] += _extra_hours(ext)
        if ext["status"] == "active":
            stats[uname]["active_extensions"] += 1

    board = sorted(stats.values(), key=lambda x: x["total_extra_hours"], reverse=True)
    for i, entry in enumerate(board):
        entry["rank"] = i + 1
        entry["total_extra_hours"] = round(entry["total_extra_hours"], 2)

    return board
