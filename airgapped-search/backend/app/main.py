"""Main FastAPI application."""

from contextlib import asynccontextmanager
import hashlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.core.config import settings
from app.database.base import engine, Base, AsyncSessionLocal
from app.database.models import User

logger = logging.getLogger(__name__)


async def create_default_admin():
    """Create default admin user if no users exist."""
    async with AsyncSessionLocal() as session:
        # Check if any users exist
        result = await session.execute(select(User))
        existing_users = result.scalars().all()

        if not existing_users:
            # Create default admin user
            default_password = "admin123"
            hashed_password = hashlib.sha256(default_password.encode()).hexdigest()

            admin_user = User(
                email="admin@example.com",
                full_name="Default Admin",
                hashed_password=hashed_password,
                is_active=True,
                is_admin=True,
            )

            session.add(admin_user)
            await session.commit()
            await session.refresh(admin_user)

            logger.warning(
                f"⚠️  Created default admin user:\n"
                f"   Email: admin@example.com\n"
                f"   Password: admin123\n"
                f"   User ID: {admin_user.id}\n"
                f"   ⚠️  CHANGE THIS PASSWORD IMMEDIATELY IN PRODUCTION!"
            )
            print(
                f"\n{'='*60}\n"
                f"⚠️  DEFAULT ADMIN USER CREATED:\n"
                f"   Email: admin@example.com\n"
                f"   Password: admin123\n"
                f"   User ID: {admin_user.id}\n"
                f"   ⚠️  CHANGE THIS PASSWORD IMMEDIATELY!\n"
                f"{'='*60}\n"
            )
        else:
            logger.info(f"Found {len(existing_users)} existing user(s)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup: Create database tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create default admin user if needed
    await create_default_admin()

    yield
    # Shutdown: Close database connections
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="Air-Gapped Document Search",
    description="On-premise document search system with RBAC",
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Air-Gapped Document Search API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


# Import and include API router
from app.api import api_router

app.include_router(api_router, prefix="/api")
