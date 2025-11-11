from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "airgapped_search"
    POSTGRES_PASSWORD: str = "changeme"
    POSTGRES_DB: str = "airgapped_search"

    # Vector Database
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333

    # Application
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8001
    SECRET_KEY: str = "dev_secret_key_change_in_production"
    ALLOWED_ORIGINS: List[str] = ["http://localhost:8080", "http://localhost:3000"]

    # Embedding
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    EMBEDDING_DIMENSION: int = 384

    # File Upload
    MAX_UPLOAD_SIZE_MB: int = 100
    UPLOAD_DIR: str = "/tmp/uploads"

    # OCR Configuration
    ENABLE_OCR: bool = True  # Enable DeepSeek-OCR for scanned documents
    OCR_DEVICE: str = "auto"  # Device: "auto", "cuda", "cpu", "mps"
    OCR_BATCH_SIZE: int = 4  # Number of images to process in parallel

    # Environment
    ENVIRONMENT: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore"
    )

    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL connection URL"""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def database_url_sync(self) -> str:
        """Construct sync PostgreSQL connection URL (for Alembic)"""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


settings = Settings()
