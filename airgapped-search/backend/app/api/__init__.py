"""Main API router aggregation."""

from fastapi import APIRouter

from app.api.endpoints import auth, documents

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(auth.router)
api_router.include_router(documents.router)

__all__ = ["api_router"]
