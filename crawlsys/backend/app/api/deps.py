"""API request dependencies and application resource lifespan."""

from __future__ import annotations

import os
from contextlib import AsyncExitStack, asynccontextmanager
from typing import TYPE_CHECKING, cast

import httpx
from core.config import PlatformQuota, SchedulerConfig
from fastapi import Request
from go_rpc import RpcClient
from llm.catalog import LlmCatalog
from llm.discovery import ModelDiscoveryService
from llm.migration import RuntimeConfigReferenceChecker, migrate_legacy_llm_settings
from llm.model_factory import LitellmModelFactory
from llm.provider_url import DEFAULT_ALLOWED_HOSTS, ProviderUrlValidator, normalize_host
from models.platform import platformSource as SiteSource
from runtime_config.store import (
    AsyncStringRedis,
    RuntimeConfigDefaults,
    RuntimeConfigStore,
)
from services.parser_configuration.assistant import (
    AssistantActionParserService,
    ParserRuleAssistant,
)
from services.parser_configuration.rate_limit import RedisParserRateLimiter
from services.parser_configuration.repository import ActionParserRepository
from services.parser_configuration.storage import ParserSampleObjectStore
from storage import MinioDB, RedisDB, SQLAlchemyDB

if TYPE_CHECKING:
    from worker.rate_limit import PlatformLimiter


def _platform_limiter_class():
    from worker.rate_limit import PlatformLimiter

    return PlatformLimiter


def get_db(request: Request) -> SQLAlchemyDB:
    db = getattr(request.app.state, "db", None)
    assert db is not None, "Database not initialized"
    return db


def get_config(request: Request) -> SchedulerConfig:
    return request.app.state.config


def get_minio(request: Request) -> MinioDB:
    minio = getattr(request.app.state, "minio", None)
    assert minio is not None, "MinIO not initialized"
    return minio


def get_runtime_config_store(request: Request) -> RuntimeConfigStore:
    store = getattr(request.app.state, "runtime_config_store", None)
    assert store is not None, "Runtime config store not initialized"
    return store


def get_llm_catalog(request: Request) -> LlmCatalog:
    catalog = getattr(request.app.state, "llm_catalog", None)
    assert catalog is not None, "LLM catalog not initialized"
    return catalog


def get_model_discovery(request: Request) -> ModelDiscoveryService:
    discovery = getattr(request.app.state, "model_discovery", None)
    assert discovery is not None, "Model discovery not initialized"
    return discovery


def get_action_parser_service(request: Request) -> AssistantActionParserService:
    service = getattr(request.app.state, "action_parser_service", None)
    assert service is not None, "Action parser service not initialized"
    return service


def provider_allowed_hosts() -> set[str]:
    custom = os.environ.get("LLM_PROVIDER_ALLOWED_HOSTS", "")
    return set(DEFAULT_ALLOWED_HOSTS) | {
        normalize_host(host.strip()) for host in custom.split(",") if host.strip()
    }


@asynccontextmanager
async def lifespan(app):
    """Own web-loop resources for exactly one FastAPI application instance."""
    config: SchedulerConfig = app.state.config
    defaults: RuntimeConfigDefaults = app.state.runtime_config_defaults
    app.state.db = None
    app.state.minio = None
    app.state.redis = None
    app.state.runtime_config_store = None
    app.state.llm_catalog = None
    app.state.model_discovery = None
    app.state.action_parser_service = None

    try:
        async with AsyncExitStack() as stack:
            pg = config.postgresql
            db = SQLAlchemyDB(
                username=pg.username,
                password=pg.password,
                host=pg.host,
                port=pg.port,
                database=pg.database,
                amode=True,
                driver="postgresql",
            )
            stack.push_async_callback(db.aclose)
            await db.aconnect()
            await db.ainit_db()
            try:
                from core.repository import DatatypeRepo

                await DatatypeRepo(db).sync_from_code()
            except Exception as exc:
                import logging

                logging.getLogger(__name__).warning(
                    "Auto sync sys datatypes skipped: %s", exc
                )
            app.state.db = db

            minio_config = config.minio
            minio = MinioDB(
                endpoint=f"{minio_config.host}:{minio_config.port}",
                access_key=minio_config.username,
                secret_key=minio_config.password,
                secure=minio_config.secure,
                amode=True,
            )
            stack.push_async_callback(minio.aclose)
            app.state.minio = minio

            redis = RedisDB(config.redis.url, amode=True)
            stack.push_async_callback(redis.aclose)
            await redis.aconnect()
            app.state.redis = redis
            app.state.runtime_config_store = RuntimeConfigStore(
                cast(AsyncStringRedis, redis), defaults
            )
            await migrate_legacy_llm_settings(db, redis, defaults.legacy_llm)

            rpc = RpcClient(
                token=config.rpc_token,
                config_store=app.state.runtime_config_store,
            )
            stack.push_async_callback(rpc.close)
            PlatformLimiter = _platform_limiter_class()

            quotas = {
                quota.platform: PlatformLimiter(quota)
                for quota in await SiteSource.load_active_quotas(db)
            }
            default_limiter = PlatformLimiter(PlatformQuota(platform="default"))

            def limiter_for(platform: str) -> PlatformLimiter:
                return quotas.get(platform, default_limiter)

            app.state.llm_catalog = LlmCatalog(
                db,
                reference_checker=RuntimeConfigReferenceChecker(db, redis),
            )
            parser_config = config.parser_configuration
            assistant = ParserRuleAssistant(
                LitellmModelFactory(app.state.llm_catalog),
                max_bytes=parser_config.ai_max_bytes,
                max_array_items=parser_config.ai_max_array_items,
                max_depth=parser_config.json_max_depth,
                max_nodes=parser_config.json_max_nodes,
            )
            if getattr(app.state, "action_parser_service", None) is None:
                app.state.action_parser_service = AssistantActionParserService(
                    repository=ActionParserRepository(db),
                    rpc=rpc,
                    limiter_for=limiter_for,
                    rate_limiter=RedisParserRateLimiter(redis.get_redis_obj()),
                    object_store=ParserSampleObjectStore(
                        minio,
                        bucket=parser_config.sample_bucket,
                        sse_enabled=parser_config.object_sse_enabled,
                        storage_ready=parser_config.storage_ready(
                            web_mode=config.web.mode,
                            minio_secure=minio_config.secure,
                        ),
                    ),
                    config=parser_config,
                    assistant=assistant,
                )
            client = await stack.enter_async_context(
                httpx.AsyncClient(follow_redirects=False)
            )
            allowed = provider_allowed_hosts()
            if config.llm.base_url:
                try:
                    parsed_llm_host = urlsplit(config.llm.base_url).hostname
                    if parsed_llm_host:
                        allowed.add(normalize_host(parsed_llm_host))
                except Exception:
                    pass
            app.state.model_discovery = ModelDiscoveryService(
                app.state.llm_catalog,
                client,
                ProviderUrlValidator(allowed),
            )

            mcp_resources = getattr(app.state, "mcp_resources", None)
            mcp_server = getattr(app.state, "mcp_server", None)
            if mcp_resources is not None and mcp_server is not None:
                mcp_resources.db = db
                mcp_resources.minio = minio
                await stack.enter_async_context(mcp_server.session_manager.run())

            yield
    finally:
        mcp_resources = getattr(app.state, "mcp_resources", None)
        if mcp_resources is not None:
            mcp_resources.db = None
            mcp_resources.minio = None
        app.state.model_discovery = None
        app.state.action_parser_service = None
        app.state.llm_catalog = None
        app.state.runtime_config_store = None
        app.state.redis = None
        app.state.minio = None
        app.state.db = None
