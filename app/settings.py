"""
Application settings, loaded from environment variables (prefix OSM2NS3_)
and an optional .env file.

Directory layout is derived from ``data_dir`` — nothing is created at import
time; the FastAPI lifespan handler calls ``ensure_dirs()`` at startup.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root (parent of this file's package directory).
_REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration for the osm2ns3 service."""

    model_config = SettingsConfigDict(
        env_prefix="OSM2NS3_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Security ──────────────────────────────────────────────
    # API-key auth is DISABLED when api_key is None (local dev default).
    # Set OSM2NS3_API_KEY to require an `X-API-Key` header on /jobs routes.
    api_key: str | None = None
    # JSON list value when set via env:
    #   OSM2NS3_CORS_ORIGINS='["https://example.com"]'
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8000",
    ]

    # ── Uploads ───────────────────────────────────────────────
    max_upload_mb: int = 100

    # ── Job control ───────────────────────────────────────────
    max_concurrent_jobs: int = 2
    job_retention_max: int = 200  # prune oldest finished beyond this many
    job_retention_days: int = 7

    # ── Pipeline timeouts (seconds) ───────────────────────────
    timeout_default_s: float = 600.0
    timeout_sumo_s: float = 1200.0  # simulations can be slow on large maps
    timeout_trace_export_s: float = 300.0

    # ── Filesystem ────────────────────────────────────────────
    # jobs/uploads/outputs (and jobs.db) live directly under data_dir.
    data_dir: Path = _REPO_ROOT
    # Built frontend (Vite dist). Present only in the Docker image by default.
    static_dir: Path = _REPO_ROOT / "static"

    # ── SUMO toolchain ────────────────────────────────────────
    # Extra directory searched first for randomTrips.py / traceExporter.py.
    # Falls back to the SUMO_HOME environment variable when unset.
    sumo_home: str | None = None

    # ── Logging ───────────────────────────────────────────────
    log_level: str = "INFO"

    # ── Derived paths ─────────────────────────────────────────
    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def upload_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def out_dir(self) -> Path:
        return self.data_dir / "outputs"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "jobs.db"

    def ensure_dirs(self) -> None:
        for d in (self.jobs_dir, self.upload_dir, self.out_dir):
            d.mkdir(parents=True, exist_ok=True)

    def resolve_sumo_home(self) -> str:
        return self.sumo_home or os.environ.get("SUMO_HOME", "")


@lru_cache
def get_settings() -> Settings:
    """Process-wide settings (FastAPI dependency). Bypassed by tests, which
    construct Settings directly to avoid lru_cache cross-test pollution."""
    return Settings()
