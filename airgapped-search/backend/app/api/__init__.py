"""Main API router aggregation."""

from fastapi import APIRouter

from app.api.endpoints import documents

api_router = APIRouter()

# Include endpoint routers
api_router.include_router(documents.router)

__all__ = ["api_router"]
