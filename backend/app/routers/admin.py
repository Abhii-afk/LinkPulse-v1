from fastapi import APIRouter

from app.core.dependencies import AdminUser


router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/access-check")
async def admin_access_check(current_user: AdminUser) -> dict[str, str]:
    return {"status": "authorized", "role": current_user.role}
