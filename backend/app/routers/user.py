from fastapi import APIRouter

from app.core.dependencies import UserOrAdmin
from app.routers.auth import user_response
from app.schemas.auth import UserResponse


router = APIRouter(prefix="/api/v1/user", tags=["user"])


@router.get("/me", response_model=UserResponse)
async def get_current_user_profile(current_user: UserOrAdmin) -> UserResponse:
    return user_response(current_user)
