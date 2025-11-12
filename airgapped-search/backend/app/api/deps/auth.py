"""Authentication dependencies for FastAPI endpoints."""

from typing import Optional
from uuid import UUID
import logging

from fastapi import Depends, HTTPException, Header, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User
from app.api.deps.database import get_db

logger = logging.getLogger(__name__)

# Security scheme for Swagger UI (auto=False to make it optional)
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from Bearer token.

    TODO: Implement proper JWT token validation.
    For now, this is a placeholder that expects user_id as token.

    Args:
        credentials: HTTP Bearer token credentials from security scheme
        authorization: Fallback authorization header
        db: Database session

    Returns:
        User: Authenticated user

    Raises:
        HTTPException: If authentication fails
    """
    logger.info(f"Auth check - credentials: {credentials}, authorization header: {authorization}")

    # Try to get token from either source
    token = None
    if credentials:
        token = credentials.credentials
        logger.info(f"Got token from HTTPBearer: {token[:8]}...")
    elif authorization:
        # Manual header parsing as fallback
        try:
            scheme, token = authorization.split(maxsplit=1)
            if scheme.lower() != "bearer":
                raise ValueError("Invalid scheme")
            logger.info(f"Got token from Authorization header: {token[:8]}...")
        except:
            pass

    if not token:
        logger.error("❌ No authentication token provided!")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No authentication token provided. Please login first and use the Authorize button.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Extract user_id from token (currently token IS the user_id)
        logger.info(f"Authenticating with token: {token[:8]}...")

        user_id = UUID(token)
        logger.debug(f"Parsed user_id: {user_id}")

        # Get user from database
        result = await db.execute(
            select(User).where(User.id == user_id, User.is_active == True)
        )
        user = result.scalar_one_or_none()

        if not user:
            logger.warning(f"User not found for token: {token[:8]}...")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        logger.info(f"✅ User authenticated: {user.email} (admin={user.is_admin})")
        return user

    except ValueError as e:
        logger.error(f"Invalid token format: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token format: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
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
