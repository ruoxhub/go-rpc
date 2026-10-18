import argparse
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from services.video_analysis.batch import BatchSummary
from scripts import analyze_clean_videos as script
from worker.result import WorkerResult


def make_args(**overrides):
    values = dict(
        config="config.toml", bucket="videos", batch_size=10,
        model_id=None, max_attempts=3, stale_timeout_seconds=7200,
        review_route=None,
    )
    values.update(overrides)
    return argparse.Namespace(**values)


def test_parser_uses_catalog_model_id_and_rejects_non_positive_values():
    parser = script.build_parser()
    assert vars(parser.parse_args([])) == vars(make_args())
    assert parser.parse_args(["--model-id", "12"]).model_id == 12
    with pytest.raises(SystemExit):
        parser.parse_args(["--model-id", "0"])


def test_load_minio_config_validates_required_section(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text("[redis]\nurl='redis://localhost'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="minio"):
        script.load_minio_config(str(path))


@pytest.mark.asyncio
async def test_run_uses_runtime_catalog_and_model_id(monkeypatch, capsys):
    pg = SimpleNamespace(username="u", password="p", host="h", port=5432, database="d")
    config = SimpleNamespace(
        postgresql=pg, redis=SimpleNamespace(url="redis://test"),
        validate=Mock(),
    )
    monkeypatch.setattr(script.SchedulerConfig, "from_toml", Mock(return_value=config))
    db = SimpleNamespace(
        aconnect=AsyncMock(), ainit_db=AsyncMock(), amigrate_db=AsyncMock(), aclose=AsyncMock()
    )
    redis = SimpleNamespace(aconnect=AsyncMock(), aclose=AsyncMock())
    minio = SimpleNamespace(aclose=AsyncMock())
    monkeypatch.setattr(script, "SQLAlchemyDB", Mock(return_value=db))
    monkeypatch.setattr(script, "RedisDB", Mock(return_value=redis))
    monkeypatch.setattr(script, "build_runtime_config_defaults", Mock(return_value=SimpleNamespace(legacy_llm=object())))
    monkeypatch.setattr(script, "RuntimeConfigStore", Mock(return_value="store"))
    monkeypatch.setattr(script, "migrate_legacy_llm_settings", AsyncMock())
    monkeypatch.setattr(script, "RuntimeConfigReferenceChecker", Mock(return_value="checker"))
    catalog = object()
    monkeypatch.setattr(script, "LlmCatalog", Mock(return_value=catalog))
    model_factory = object()
    monkeypatch.setattr(script, "LitellmModelFactory", Mock(return_value=model_factory))
    monkeypatch.setattr(script, "LiteLlmTranscriber", Mock(return_value="transcriber"))
    monkeypatch.setattr(script, "load_minio_config", Mock(return_value={
        "host": "minio", "port": 9000, "username": "a", "password": "s"
    }))
    monkeypatch.setattr(script, "MinioDB", Mock(return_value=minio))
    monkeypatch.setattr(script, "MinioVideoSource", Mock(return_value="source"))
    monkeypatch.setattr(script, "VideoAnalysisRepository", Mock(return_value="repo"))
    worker = SimpleNamespace(run_batch=AsyncMock(return_value=WorkerResult(2, 1, 1, 0)))
    worker_factory = Mock(return_value=worker)
    monkeypatch.setattr(script, "VideoAnalysisWorker", worker_factory)

    result = await script.run(make_args(model_id=12))

    assert result == BatchSummary(2, 1, 1, 0)
    assert worker_factory.call_args.kwargs["config_store"] == "store"
    assert worker_factory.call_args.kwargs["model_factory"] is model_factory
    assert worker.run_batch.await_args.args[0].llm_model_id == 12
    redis.aclose.assert_awaited_once()
    minio.aclose.assert_awaited_once()
    db.aclose.assert_awaited_once()
    assert "claimed=2" in capsys.readouterr().out


def test_exit_code_and_main_failure(monkeypatch, capsys):
    assert script.exit_code_for(BatchSummary(1, 1, 0, 0)) == 0
    assert script.exit_code_for(BatchSummary(1, 0, 1, 0)) == 1
    monkeypatch.setattr(script, "build_parser", Mock(return_value=SimpleNamespace(
        parse_args=Mock(return_value=make_args())
    )))
    def fail_run(coroutine):
        coroutine.close()
        raise RuntimeError("boom")

    monkeypatch.setattr(script.asyncio, "run", Mock(side_effect=fail_run))
    with pytest.raises(SystemExit) as caught:
        script.main()
    assert caught.value.code == 2
    assert "RuntimeError" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_redis_migration_failure_closes_redis_and_database(monkeypatch):
    pg = SimpleNamespace(username="u", password="p", host="h", port=5432, database="d")
    config = SimpleNamespace(
        postgresql=pg, redis=SimpleNamespace(url="redis://test"), validate=Mock()
    )
    db = SimpleNamespace(
        aconnect=AsyncMock(), ainit_db=AsyncMock(), amigrate_db=AsyncMock(),
        aclose=AsyncMock(),
    )
    redis = SimpleNamespace(aconnect=AsyncMock(), aclose=AsyncMock())
    monkeypatch.setattr(script.SchedulerConfig, "from_toml", Mock(return_value=config))
    monkeypatch.setattr(script, "SQLAlchemyDB", Mock(return_value=db))
    monkeypatch.setattr(script, "RedisDB", Mock(return_value=redis))
    defaults = SimpleNamespace(legacy_llm=object())
    monkeypatch.setattr(script, "build_runtime_config_defaults", Mock(return_value=defaults))
    monkeypatch.setattr(
        script, "migrate_legacy_llm_settings",
        AsyncMock(side_effect=RuntimeError("migration failed")),
    )

    with pytest.raises(RuntimeError, match="migration failed"):
        await script.run(make_args())

    redis.aclose.assert_awaited_once()
    db.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_cleanup_failures_do_not_mask_primary_and_all_closes_run(monkeypatch):
    pg = SimpleNamespace(username="u", password="p", host="h", port=5432, database="d")
    config = SimpleNamespace(
        postgresql=pg, redis=SimpleNamespace(url="redis://test"), validate=Mock()
    )
    db = SimpleNamespace(
        aconnect=AsyncMock(), ainit_db=AsyncMock(), amigrate_db=AsyncMock(),
        aclose=AsyncMock(side_effect=ValueError("db secret")),
    )
    redis = SimpleNamespace(
        aconnect=AsyncMock(), aclose=AsyncMock(side_effect=OSError("redis secret"))
    )
    monkeypatch.setattr(script.SchedulerConfig, "from_toml", Mock(return_value=config))
    monkeypatch.setattr(script, "SQLAlchemyDB", Mock(return_value=db))
    monkeypatch.setattr(script, "RedisDB", Mock(return_value=redis))
    monkeypatch.setattr(
        script, "build_runtime_config_defaults", Mock(side_effect=RuntimeError("primary"))
    )

    with pytest.raises(RuntimeError, match="primary") as caught:
        await script.run(make_args())

    db.aclose.assert_awaited_once()
    redis.aclose.assert_awaited_once()
    assert caught.value.__notes__ == [
        "resource cleanup failed: ValueError, OSError"
    ]
    assert "secret" not in caught.value.__notes__[0]
