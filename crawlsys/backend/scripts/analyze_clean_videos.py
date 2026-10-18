"""Analyze a batch of cleaned videos stored in MinIO."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tomllib
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(BACKEND_ROOT / "app"))

from services.video_analysis.minio_source import MinioVideoSource
from services.video_analysis.batch import BatchSummary, run_analysis_batch
from services.video_analysis.repository import VideoAnalysisRepository
from core.config import SchedulerConfig
from llm.catalog import LlmCatalog
from llm.migration import RuntimeConfigReferenceChecker, migrate_legacy_llm_settings
from llm.model_factory import LitellmModelFactory
from llm.transcription import LiteLlmTranscriber
from models.task_config import VideoAnalysisTaskConfig
from runtime_config.defaults import build_runtime_config_defaults
from runtime_config.store import RuntimeConfigStore
from storage import MinioDB, RedisDB, SQLAlchemyDB
from worker.video_analysis import (
    VideoAnalysisWorker,
    build_analysis_service,
)


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("必须大于 0")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="分析 MinIO 中的已清洗视频")
    parser.add_argument("--config", default="config.toml")
    parser.add_argument("--bucket", default="videos")
    parser.add_argument("--batch-size", type=positive_int, default=10)
    parser.add_argument("--model-id", type=positive_int, default=None)
    parser.add_argument("--max-attempts", type=positive_int, default=3)
    parser.add_argument(
        "--stale-timeout-seconds",
        type=positive_int,
        default=7200,
    )
    parser.add_argument(
        "--review-route",
        choices=["R", "G"],
        default=None,
    )
    return parser


def load_minio_config(config_path: str) -> dict:
    with open(config_path, "rb") as file:
        config = tomllib.load(file)
    if "minio" not in config:
        raise ValueError(f"配置文件缺少 [minio]：{config_path}")
    minio_config = config["minio"]
    if "secure" in minio_config and not isinstance(minio_config["secure"], bool):
        raise ValueError("[minio].secure 必须是布尔值")
    return minio_config


async def run(args: argparse.Namespace) -> BatchSummary:
    db = None
    minio = None
    config_redis = None
    primary_error: BaseException | None = None
    try:
        config = SchedulerConfig.from_toml(args.config)
        config.validate()
        pg = config.postgresql
        db = SQLAlchemyDB(
            username=pg.username,
            password=pg.password,
            host=pg.host,
            port=pg.port,
            database=pg.database,
            driver="postgresql",
            amode=True,
        )
        await db.aconnect()
        await db.ainit_db()
        await db.amigrate_db()

        config_redis = RedisDB(config.redis.url, amode=True)
        await config_redis.aconnect()
        defaults = build_runtime_config_defaults(config, args.config)
        config_store = RuntimeConfigStore(config_redis, defaults)
        await migrate_legacy_llm_settings(db, config_redis, defaults.legacy_llm)
        catalog = LlmCatalog(
            db,
            reference_checker=RuntimeConfigReferenceChecker(db, config_redis),
        )

        minio_config = load_minio_config(args.config)
        minio = MinioDB(
            endpoint=f"{minio_config['host']}:{minio_config['port']}",
            access_key=minio_config["username"],
            secret_key=minio_config["password"],
            secure=minio_config.get("secure", False),
            amode=True,
        )
        source = MinioVideoSource(minio, args.bucket)
        repository = VideoAnalysisRepository(db)
        worker = VideoAnalysisWorker(
            platform="video_analysis",
            repo=None,
            db=db,
            quota=None,
            source=source,
            config_store=config_store,
            catalog=catalog,
            model_factory=LitellmModelFactory(catalog),
            transcriber=LiteLlmTranscriber(),
            analysis_service_factory=build_analysis_service,
            stale_timeout_seconds=args.stale_timeout_seconds,
            analysis_repo=repository,
            batch_runner=run_analysis_batch,
        )
        result = await worker.run_batch(VideoAnalysisTaskConfig(
            batch_size=args.batch_size,
            max_attempts=args.max_attempts,
            llm_model_id=args.model_id,
            review_route=args.review_route,
        ))
        summary = BatchSummary(result.total, result.succeeded, result.failed, result.skipped)
        print(
            f"claimed={summary.claimed} succeeded={summary.succeeded} "
            f"failed={summary.failed} skipped={summary.skipped}"
        )
        return summary
    except BaseException as exc:
        primary_error = exc
        raise
    finally:
        close_error: BaseException | None = None
        cleanup_types: list[str] = []
        if minio is not None:
            try:
                await minio.aclose()
            except BaseException as exc:
                cleanup_types.append(type(exc).__name__)
                close_error = exc
        if db is not None:
            try:
                await db.aclose()
            except BaseException as exc:
                cleanup_types.append(type(exc).__name__)
                if close_error is None:
                    close_error = exc
        if config_redis is not None:
            try:
                await config_redis.aclose()
            except BaseException as exc:
                cleanup_types.append(type(exc).__name__)
                if close_error is None:
                    close_error = exc
        if primary_error is not None and cleanup_types:
            primary_error.add_note(
                "resource cleanup failed: " + ", ".join(cleanup_types)
            )
        if primary_error is None and close_error is not None:
            raise close_error


def exit_code_for(summary: BatchSummary) -> int:
    return 1 if summary.failed > 0 else 0


def main() -> None:
    args = build_parser().parse_args()
    try:
        summary = asyncio.run(run(args))
    except Exception as exc:
        print(
            f"视频分析批处理启动失败：{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2) from exc
    raise SystemExit(exit_code_for(summary))


if __name__ == "__main__":
    main()
