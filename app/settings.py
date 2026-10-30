"""Non-credential runtime configuration.

Only transport settings live here. RunZero credentials are never read from
the environment or a config file - they come exclusively from the
X-Runzero-Api-Token request header (see app/credentials.py and SOP Sec 3.1).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Reads MCP_HTTP_HOST / MCP_HTTP_PORT and ignores any other variable.

    `extra="ignore"` is required (SOP Sec 1.2): the runtime environment
    injects variables this project never declared, and an unknown field
    would otherwise crash pydantic-settings at startup.
    """

    model_config = SettingsConfigDict(extra="ignore")

    mcp_http_host: str = "0.0.0.0"
    mcp_http_port: int = 8080


settings = Settings()
