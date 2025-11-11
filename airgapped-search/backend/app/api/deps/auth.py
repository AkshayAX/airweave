"""Authentication dependencies for FastAPI endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import Depends, HTTPException, Header, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, UserOrganization
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


async def require_org_access(
    organization_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserOrganization:
    """Verify user has access to organization.

    Args:
        organization_id: Organization UUID to check access for
        current_user: Current authenticated user
        db: Database session

    Returns:
        UserOrganization: User's membership in the organization

    Raises:
        HTTPException: If user doesn't have access
    """
    result = await db.execute(
        select(UserOrganization).where(
            UserOrganization.user_id == current_user.id,
            UserOrganization.organization_id == organization_id,
        )
    )
    user_org = result.scalar_one_or_none()

    if not user_org:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this organization",
        )

    return user_org


def require_role(required_role: str):
    """Dependency factory to require specific role in organization.

    Role hierarchy: member < admin < owner

    Args:
        required_role: Minimum required role (member, admin, owner)

    Returns:
        Dependency function that checks role

    Example:
        @router.delete("/documents/{document_id}")
        async def delete_document(
            user_org: UserOrganization = Depends(require_role("admin")),
        ):
            # Only admins and owners can access this
            ...
    """
    ROLE_HIERARCHY = {"member": 0, "admin": 1, "owner": 2}

    async def check_role(
        user_org: UserOrganization = Depends(require_org_access),
    ) -> UserOrganization:
        user_role_level = ROLE_HIERARCHY.get(user_org.role, -1)
        required_role_level = ROLE_HIERARCHY.get(required_role, 999)

        if user_role_level < required_role_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {required_role} role or higher",
            )

        return user_org

    return check_role
