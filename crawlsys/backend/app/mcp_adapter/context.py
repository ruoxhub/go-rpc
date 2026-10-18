"""Explicit runtime dependencies shared by MCP adapter tools."""

from dataclasses import dataclass

from core.config import McpConfig
from storage.minio import MinioDB
from storage.sql import SQLAlchemyDB


@dataclass(slots=True)
class McpAppResources:
    """Application-owned services bound before the MCP session manager starts."""

    db: SQLAlchemyDB | None
    minio: MinioDB | None
    config: McpConfig

    def require_ready(self) -> "McpAppResources":
        """Reject tool dispatch before application storage initialization."""
        if self.db is None or self.minio is None:
            raise RuntimeError("MCP application resources are not initialized")
        return self
