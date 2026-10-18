"""Crawler FastAPI application factory."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

_crawler_dir = str(Path(__file__).resolve().parent.parent)
if _crawler_dir not in sys.path:
    sys.path.insert(0, _crawler_dir)

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.encoders import jsonable_encoder  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402

from api.crawler import router as crawler_router  # noqa: E402
from api.analysis import router as analysis_router  # noqa: E402
from api.settings import router as settings_router  # noqa: E402
from api.llm import router as llm_router  # noqa: E402
from core.config import SchedulerConfig  # noqa: E402
from runtime_config.defaults import build_runtime_config_defaults  # noqa: E402
from api.deps import lifespan  # noqa: E402
from services.parser_configuration.errors import ParserConfigurationError  # noqa: E402
from services.parser_configuration.rate_limit import ParserRateLimitExceeded  # noqa: E402
from services.datatype_data.errors import DatatypeDataError  # noqa: E402


logger = logging.getLogger(__name__)
_PARSER_ERROR_DETAIL_FIELDS = {
    "ba_id",
    "sample_id",
    "revision_id",
    "model_id",
    "path",
    "validator",
    "retry_after_seconds",
}
_DATATYPE_ERROR_DETAIL_FIELDS = {"field"}


async def _request_validation_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    errors = []
    for error in exc.errors():
        sanitized = dict(error)
        sanitized.pop("input", None)
        errors.append(sanitized)
    logger.warning("Request validation failed: %s", errors)
    status_code = 400 if any(error.get("type") == "json_invalid" for error in errors) else 422
    return JSONResponse(
        status_code=status_code, content={"detail": jsonable_encoder(errors)}
    )


def _parser_error_details(details: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in details.items()
        if key in _PARSER_ERROR_DETAIL_FIELDS
        and isinstance(value, (str, int, float, bool))
    }


async def _parser_configuration_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    if not isinstance(exc, ParserConfigurationError):
        raise exc
    details = _parser_error_details(exc.details)
    headers = None
    retry_after = details.get("retry_after_seconds")
    if exc.status_code == 429 and isinstance(retry_after, (int, float)):
        headers = {"Retry-After": str(max(1, int(retry_after)))}
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": details},
        headers=headers,
    )


async def _parser_rate_limit_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    if not isinstance(exc, ParserRateLimitExceeded):
        raise exc
    retry_after = max(1, int(exc.retry_after_seconds))
    return JSONResponse(
        status_code=429,
        content={
            "code": "parser_rate_limited",
            "message": "parser configuration rate limit exceeded",
            "details": {"retry_after_seconds": retry_after},
        },
        headers={"Retry-After": str(retry_after)},
    )


async def _datatype_data_error_handler(
    _request: Request, exc: Exception
) -> JSONResponse:
    if not isinstance(exc, DatatypeDataError):
        raise exc
    details = {
        key: value
        for key, value in exc.details.items()
        if key in _DATATYPE_ERROR_DETAIL_FIELDS
        and isinstance(value, (str, int, float, bool))
    }
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "details": details},
    )


def create_app(config: SchedulerConfig, config_path: str | Path | None = None) -> FastAPI:
    """Build the FastAPI app, injecting the shared scheduler config."""
    app = FastAPI(
        title="Crawler Admin",
        description="Crawler task/action/platform management API",
        lifespan=lifespan,
    )
    app.state.config = config
    app.state.runtime_config_defaults = build_runtime_config_defaults(
        config, config_path
    )
    app.state.mcp_resources = None
    app.state.mcp_server = None
    app.state.mcp_http_app = None
    app.add_exception_handler(
        RequestValidationError,
        _request_validation_error_handler,
    )
    app.add_exception_handler(
        ParserConfigurationError,
        _parser_configuration_error_handler,
    )
    app.add_exception_handler(
        ParserRateLimitExceeded,
        _parser_rate_limit_error_handler,
    )
    app.add_exception_handler(
        DatatypeDataError,
        _datatype_data_error_handler,
    )

    if config.mcp.enabled:
        from mcp_adapter import (
            McpAppResources,
            create_mcp_http_app,
            create_mcp_server,
        )

        mcp_resources = McpAppResources(db=None, minio=None, config=config.mcp)
        mcp_server = create_mcp_server(mcp_resources, config.mcp)
        mcp_http_app = create_mcp_http_app(mcp_server, config.mcp)
        app.state.mcp_resources = mcp_resources
        app.state.mcp_server = mcp_server
        app.state.mcp_http_app = mcp_http_app
        app.mount("/mcp", mcp_http_app, name="mcp")

    app.include_router(crawler_router)
    app.include_router(analysis_router)
    app.include_router(settings_router)
    app.include_router(llm_router)

    return app
