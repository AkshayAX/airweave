"""FastAPI dependencies for authentication, database, etc."""

from .database import get_db
from .auth import get_current_user, require_admin

__all__ = [
    "get_db",
    "get_current_user",
    "require_admin",
]
