from __future__ import annotations

from typing import Any


class DatatypeDataError(RuntimeError):
    """数据记录管理领域的可映射错误。

    携带稳定的 `code`、面向用户的 `message`、HTTP `status_code` 与白名单化的
    `details`；由 API 层统一映射为 JSON 响应，避免把 SQL 细节泄漏给客户端。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


__all__ = ["DatatypeDataError"]
