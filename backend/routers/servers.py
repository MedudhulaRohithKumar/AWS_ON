from fastapi import APIRouter, HTTPException, Depends, Request
from models.schemas import AddServerRequest, ExtendRequest
from services.s3_service import (
    get_all_servers, get_server_by_id, create_server,
    log_activity, get_active_extension_for_instance,
    create_extension, update_extension,
)
from services.aws_service import (
    discover_ec2_by_tag,
    get_ec2_status, get_rds_status,
    start_ec2, stop_ec2, start_rds, stop_rds,
    apply_protection_tag_ec2, remove_protection_tag_ec2,
    apply_protection_tag_rds, remove_protection_tag_rds,
    create_expiry_schedule, delete_expiry_schedule,
)
from middleware.auth_middleware import get_current_user, require_admin
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/servers", tags=["servers"])


def _get_ip(request: Request) -> str:
    fwd = request.headers.get("X-Forwarded-For")
    return fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )


def _parse_utc(dt_str: str) -> datetime:
    """Parse ISO8601 string to UTC-aware datetime."""
    dt_str = dt_str.replace("Z", "+00:00")
    dt = datetime.fromisoformat(dt_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


@router.get("")
async def list_servers(current_user: dict = Depends(get_current_user)):
    """List all active servers with their live AWS status."""
    all_active = [s for s in get_all_servers() if s.get("is_active", True)]
    
    if current_user.get("role") != "admin":
        assigned = set(current_user.get("assigned_servers", []))
        servers = [s for s in all_active if s["instance_id"] in assigned]
    else:
        servers = all_active

    result = []
    for s in servers:
        live_status = (
            get_ec2_status(s["instance_id"])
            if s["type"] == "EC2"
            else get_rds_status(s["instance_id"])
        )
        # Check if there's an active extension
        ext = get_active_extension_for_instance(s["instance_id"])
        result.append({
            **s,
            "status": live_status,
            "active_extension": ext,
        })
    return result


@router.get("/discover")
async def discover_servers(current_user: dict = Depends(require_admin)):
    """Discover EC2 instances tagged TURN_UP=UAT_EXTEND."""
    instances = discover_ec2_by_tag()
    existing_ids = {s["instance_id"] for s in get_all_servers()}
    for inst in instances:
        inst["already_added"] = inst["instance_id"] in existing_ids
    return {"instances": instances}


@router.post("/{server_id}/extend")
async def extend_server(
    server_id: str,
    body: ExtendRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Start an instance and apply EXTEND_UNTIL tag until specified time."""
    server = get_server_by_id(server_id)
    if not server or not server.get("is_active", True):
        raise HTTPException(status_code=404, detail="Server not found")

    until_utc_dt = _parse_utc(body.extended_until)
    now_utc = datetime.now(timezone.utc)

    if until_utc_dt <= now_utc:
        raise HTTPException(status_code=400, detail="Extension time must be in the future")

    instance_id = server["instance_id"]
    instance_type = server["type"]
    until_str = until_utc_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    existing_ext = get_active_extension_for_instance(instance_id)

    if existing_ext:
        # Update deadline on existing extension
        delete_expiry_schedule(existing_ext["id"])
        update_extension(existing_ext["id"], {
            "extended_until": until_str,
            "updated_at": now_utc.isoformat().replace("+00:00", "Z"),
        })
        # Re-apply tag with new time
        if instance_type == "EC2":
            apply_protection_tag_ec2(instance_id, until_str)
        else:
            apply_protection_tag_rds(instance_id, until_str)
        create_expiry_schedule(existing_ext["id"], instance_id, until_utc_dt)
        ext_id = existing_ext["id"]
    else:
        # Start the instance
        if instance_type == "EC2":
            start_ec2(instance_id)
            apply_protection_tag_ec2(instance_id, until_str)
        else:
            start_rds(instance_id)
            apply_protection_tag_rds(instance_id, until_str)

        ext_id = str(uuid.uuid4())
        extension = {
            "id": ext_id,
            "user_id": current_user["id"],
            "username": current_user["username"],
            "instance_id": instance_id,
            "instance_type": instance_type,
            "display_name": server["display_name"],
            "extended_until": until_str,
            "requested_at": now_utc.isoformat().replace("+00:00", "Z"),
            "status": "active",
            "tag_applied": True,
            "scheduler_created": False,
        }
        create_extension(extension)
        scheduled = create_expiry_schedule(ext_id, instance_id, until_utc_dt)
        if scheduled:
            update_extension(ext_id, {"scheduler_created": True})

    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "EXTEND_INSTANCE",
        "resource_id": instance_id,
        "resource_type": instance_type,
        "details": f"Extended {server['display_name']} ({instance_id}) until {until_str}",
        "timestamp": now_utc.isoformat().replace("+00:00", "Z"),
        "ip_address": _get_ip(request),
    })

    return {
        "message": f"{instance_id} extended until {until_str}",
        "extension_id": ext_id,
        "instance_id": instance_id,
        "extended_until": until_str,
    }


@router.post("/{server_id}/stop")
async def stop_server(
    server_id: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Manually stop an instance, remove protection tag, and cancel expiry schedule."""
    server = get_server_by_id(server_id)
    if not server or not server.get("is_active", True):
        raise HTTPException(status_code=404, detail="Server not found")

    instance_id = server["instance_id"]
    instance_type = server["type"]

    if instance_type == "EC2":
        stop_ec2(instance_id)
        remove_protection_tag_ec2(instance_id)
    else:
        stop_rds(instance_id)
        remove_protection_tag_rds(instance_id)

    existing_ext = get_active_extension_for_instance(instance_id)
    if existing_ext:
        delete_expiry_schedule(existing_ext["id"])
        update_extension(existing_ext["id"], {
            "status": "manually_stopped",
            "stopped_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        })

    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "STOP_INSTANCE",
        "resource_id": instance_id,
        "resource_type": instance_type,
        "details": f"Manually stopped {server['display_name']} ({instance_id})",
        "timestamp": now_str,
        "ip_address": _get_ip(request),
    })

    return {"message": f"{instance_id} stopped successfully"}
