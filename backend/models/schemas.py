from pydantic import BaseModel
from typing import Optional
from enum import Enum


class UserRole(str, Enum):
    admin = "admin"
    user = "user"


class ResourceType(str, Enum):
    EC2 = "EC2"
    RDS = "RDS"


class ExtensionStatus(str, Enum):
    active = "active"
    expired = "expired"
    manually_stopped = "manually_stopped"


# ─── Request Models ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class ExtendRequest(BaseModel):
    extended_until: str  # ISO8601 string, e.g. "2026-06-23T23:00:00Z"


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: str
    role: UserRole = UserRole.user


class UpdateUserRequest(BaseModel):
    email: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = None


class AddServerRequest(BaseModel):
    instance_id: str
    type: ResourceType
    display_name: str
    region: str = "ap-south-1"


# ─── Response Models ───────────────────────────────────────────────────────

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    created_at: str


class ServerResponse(BaseModel):
    id: str
    instance_id: str
    type: str
    display_name: str
    region: str
    is_active: bool
    added_at: str
    status: Optional[str] = None


class ExtensionResponse(BaseModel):
    id: str
    user_id: str
    username: str
    instance_id: str
    instance_type: str
    display_name: str
    extended_until: str
    requested_at: str
    status: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
