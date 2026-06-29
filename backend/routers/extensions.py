from fastapi import APIRouter, Depends
from services.s3_service import get_all_extensions
from middleware.auth_middleware import get_current_user, require_admin

router = APIRouter(prefix="/api/extensions", tags=["extensions"])


@router.get("/mine")
async def my_extensions(current_user: dict = Depends(get_current_user)):
    """Current user's extension history."""
    all_ext = get_all_extensions()
    return sorted(
        [e for e in all_ext if e["user_id"] == current_user["id"]],
        key=lambda x: x.get("requested_at", ""),
        reverse=True,
    )


@router.get("")
async def all_extensions(current_user: dict = Depends(require_admin)):
    """All extensions — admin only."""
    all_ext = get_all_extensions()
    return sorted(all_ext, key=lambda x: x.get("requested_at", ""), reverse=True)
