"""Server configuration loaded from environment variables or a .env file.

Copy `.env.example` to `.env` for local development.
Every field can be overridden by an environment variable of the same name.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """IRS risk server settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Transport ────────────────────────────────────────────────────────────
    # "stdio"           — local subprocess (Claude Desktop, Bob, Claude Code)
    # "streamable-http" — remote HTTP server (containers, Code Engine)
    # app.py auto-selects HTTP when the platform injects PORT.
    mcp_transport: str = "stdio"
    mcp_host: str = "0.0.0.0"
    mcp_port: int = 8000

    # ── Risk engine ──────────────────────────────────────────────────────────
    # Engine version is embedded in every score payload for auditability.
    # Bump this when weights or thresholds change.
    risk_engine_version: str = "hypothetical-v1"

    # ── External data ────────────────────────────────────────────────────────
    # IRS Statistical of Income data endpoint (Socrata, no auth required).
    irs_soi_base_url: str = "https://data.irs.gov/resource"

    # Request timeout (seconds) for outbound API calls.
    http_timeout: float = 15.0


settings = Settings()
