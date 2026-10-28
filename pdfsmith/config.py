"""Central configuration for Advanced Professional Suite."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    # App
    app_name: str = os.getenv("APP_NAME", "Advanced Professional Suite")
    app_version: str = os.getenv("APP_VERSION", "1.0.0")
    
    # Server
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    
    # Upload limits
    max_upload_mb: int = int(os.getenv("PDFSMITH_MAX_MB", os.getenv("MAX_UPLOAD_MB", "50")))
    max_files_per_request: int = int(os.getenv("MAX_FILES_PER_REQUEST", "20"))
    
    # Rate limiting
    rate_limit_enabled: bool = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
    rate_limit_requests: int = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))
    rate_limit_window_seconds: int = int(os.getenv("RATE_LIMIT_WINDOW", "60"))
    
    # Workers
    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))
    
    # Features
    allow_ai_tools: bool = os.getenv("ALLOW_AI_TOOLS", "true").lower() == "true"
    
    # CORS
    cors_origins: str = os.getenv("CORS_ORIGINS", "*")
    
    # Job queue (for future scaling)
    jobs_enabled: bool = os.getenv("JOBS_ENABLED", "false").lower() == "true"
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Storage
    storage_backend: str = os.getenv("STORAGE_BACKEND", "memory")  # memory or s3
    
    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


settings = Settings()
