"""Authentication endpoints for user registration and login."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, EmailStr

from app.database.models import User
from app.api.deps import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])


# Pydantic models
class UserRegister(BaseModel):
    """User registration request."""
    email: EmailStr
    password: str
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    """User login request."""
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str
    token_type: str = "bearer"
    user_id: str
    email: str
    is_admin: bool


# Simple password hashing (TODO: Replace with proper bcrypt)
def hash_password(password: str) -> str:
    """Hash a password (placeholder - use bcrypt in production)."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against hash."""
    return hash_password(plain_password) == hashed_password


@router.post("/register", response_model=TokenResponse)
async def register(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user.

    Creates a new user account and returns an access token.

    Args:
        user_data: Registration data (email, password, full_name)
        db: Database session

    Returns:
        TokenResponse with access token and user info
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(User.email == user_data.email)
    )
    existing_user = result.scalar_one_or_none()

    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Create new user
    user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        hashed_password=hash_password(user_data.password),
        is_active=True,
        is_admin=False,  # First user should be made admin manually or via env
    )

    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Return token (for now, just use user_id as token)
    # TODO: Implement proper JWT tokens
    return TokenResponse(
        access_token=str(user.id),
        user_id=str(user.id),
        email=user.email,
        is_admin=user.is_admin,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    credentials: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Login with email and password.

    Authenticates user and returns access token.

    Args:
        credentials: Login credentials (email, password)
        db: Database session

    Returns:
        TokenResponse with access token and user info
    """
    # Get user by email
    result = await db.execute(
        select(User).where(User.email == credentials.email)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Verify password
    if not verify_password(credentials.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    # Check if user is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )

    # Update last active
    user.last_active_at = datetime.utcnow()
    await db.commit()

    # Return token (for now, just use user_id as token)
    # TODO: Implement proper JWT tokens
    return TokenResponse(
        access_token=str(user.id),
        user_id=str(user.id),
        email=user.email,
        is_admin=user.is_admin,
    )


@router.get("/me")
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
):
    """Get current authenticated user information.

    Args:
        current_user: Authenticated user from token

    Returns:
        User information
    """
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "full_name": current_user.full_name,
        "is_admin": current_user.is_admin,
        "is_active": current_user.is_active,
    }


@router.get("/test-auth")
async def test_authentication(
    current_user: User = Depends(get_current_user),
):
    """Test endpoint to verify authentication is working.

    Returns:
        Success message with user info
    """
    return {
        "message": "Authentication successful!",
        "user_id": str(current_user.id),
        "email": current_user.email,
        "is_admin": current_user.is_admin,
    }
