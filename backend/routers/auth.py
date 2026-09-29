from fastapi import APIRouter, HTTPException, status, Depends, Request
from models.schemas import LoginRequest, TokenResponse, UserResponse
from services.s3_service import get_user_by_username, log_activity, DEFAULT_ADMIN_USER, update_user
from services.auth_service import verify_password, create_access_token
from middleware.auth_middleware import get_current_user
from datetime import datetime, timezone
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
async def login(request: Request, body: LoginRequest):
    ip = _get_ip(request)
    user = get_user_by_username(body.username)

    is_valid = user is not None and verify_password(body.password, user.get("password_hash", ""))

    # Fallback / recovery for admin: if existing S3 hash is forgotten or outdated,
    # allow 'admin123' to authenticate and auto-update the hash in S3.
    if not is_valid and body.username == "admin":
        if verify_password(body.password, DEFAULT_ADMIN_USER["password_hash"]):
            is_valid = True
            if not user:
                user = dict(DEFAULT_ADMIN_USER)
            else:
                user["password_hash"] = DEFAULT_ADMIN_USER["password_hash"]
                try:
                    update_user(user["id"], {"password_hash": DEFAULT_ADMIN_USER["password_hash"]})
                    logger.info("Synchronized reset admin password to S3")
                except Exception as e:
                    logger.warning("Could not sync updated admin password to S3: %s", e)

    if not is_valid:
        # Log failed attempt
        log_activity({
            "id": str(uuid.uuid4()),
            "user_id": user["id"] if user else "unknown",
            "username": body.username,
            "action": "FAILED_LOGIN",
            "resource_id": None,
            "resource_type": "AUTH",
            "details": f"Failed login attempt for username '{body.username}'",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "ip_address": ip,
        })
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact your administrator.",
        )

    token = create_access_token(user)

    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": user["id"],
        "username": user["username"],
        "action": "LOGIN",
        "resource_id": None,
        "resource_type": "AUTH",
        "details": "Successful login",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ip_address": ip,
    })

    return TokenResponse(
        access_token=token,
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            email=user.get("email", "admin@example.com"),
            role=user.get("role", "admin"),
            is_active=user.get("is_active", True),
            created_at=user.get("created_at", datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")),
            assigned_servers=user.get("assigned_servers", []),
        ),
    )


@router.post("/logout")
async def logout(request: Request, current_user: dict = Depends(get_current_user)):
    log_activity({
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "username": current_user["username"],
        "action": "LOGOUT",
        "resource_id": None,
        "resource_type": "AUTH",
        "details": "User logged out",
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "ip_address": _get_ip(request),
    })
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        role=current_user["role"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
    )
