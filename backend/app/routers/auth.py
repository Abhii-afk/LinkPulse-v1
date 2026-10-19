from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    hash_password,
    normalize_email,
    verify_password,
)
from app.models.user import User, UserRole
from app.schemas.auth import Credentials, RegisterRequest, TokenResponse, UserResponse


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def user_response(user: User) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> UserResponse:
    try:
        email = normalize_email(payload.email)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from error

    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        role=UserRole.USER.value,
    )
    db.add(user)
    try:
        await db.commit()
        await db.refresh(user)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered") from None

    return user_response(user)


@router.post("/login", response_model=TokenResponse)
async def login(payload: Credentials, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    try:
        email = normalize_email(payload.email)
    except ValueError:
        email = ""

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    return TokenResponse(access_token=create_access_token(user), user=user_response(user))
