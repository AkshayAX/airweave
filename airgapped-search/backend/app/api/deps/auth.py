"""Authentication dependencies for FastAPI endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.api.deps.database import get_db


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from Authorization header.

    TODO: Implement proper JWT token validation.
    For now, this is a placeholder that expects "Bearer <user_id>".

    Args:
        authorization: Authorization header value
        db: Database session

    Returns:
        User: Authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # TODO: Replace with JWT token validation
        # For now, expect "Bearer <user_id>"
        scheme, user_id = authorization.split()
        if scheme.lower() != "bearer":
            raise ValueError("Invalid authentication scheme")

        # Get user from database
        result = await db.execute(
            select(User).where(User.id == UUID(user_id), User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
            )

        return user

    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    """Verify user is an admin.

    Args:
        current_user: Current authenticated user

    Returns:
        User: Authenticated admin user

    Raises:
        HTTPException: If user is not an admin
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
