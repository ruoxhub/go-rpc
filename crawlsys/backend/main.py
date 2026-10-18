# ruff: noqa: E402, I001, C408
# pyright: reportMissingImports=false, reportAttributeAccessIssue=false, reportCallIssue=false, reportArgumentType=false, reportPrivateImportUsage=false, reportUndefinedVariable=false
"""Bilibili crawler scheduler entry point."""

import asyncio
import os
import signal
import sys
import threading
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent)
_APP_DIR = str(Path(_BACKEND_DIR) / "app")
sys.path[:] = [
    _APP_DIR,
    _BACKEND_DIR,
    *(entry for entry in sys.path if entry not in {_APP_DIR, _BACKEND_DIR}),
]

import uvicorn

from uvicorn.supervisors import ChangeReload as _ChangeReload

from core.config import SchedulerConfig
from worker.registry import build_runtime
from common.logging import get_logger

if __package__:
    from .app.api.main import create_app
else:
    from api.main import create_app

logger = get_logger(__file__)


_CONFIG_PATH_ENV = "CRAWLER_CONFIG_PATH"


class _ThreadSafeReload(_ChangeReload):
    """ChangeReload variant that skips signal registration.

    `BaseReload.startup()` installs signal handlers, which fails with
    `ValueError: signal only works in main thread` when invoked from a
    daemon thread. The scheduler's main asyncio loop already handles
    SIGINT/SIGTERM, so the reloader's handlers are not needed here.

    Compatible with uvicorn >= 0.30 (tested on 0.41). Uses private API
    ``get_subprocess`` from ``uvicorn.supervisors.basereload`` — review
    this override when upgrading uvicorn.
    """

    def startup(self) -> None:
        import click
        from uvicorn.supervisors.basereload import (
            get_subprocess,
            logger as _reload_logger,
        )

        message = f"Started reloader process [{self.pid}] using {self.reloader_name}"
        color_message = "Started reloader process [{}] using {}".format(
            click.style(str(self.pid), fg="cyan", bold=True),
            click.style(str(self.reloader_name), fg="cyan", bold=True),
        )
        _reload_logger.info(message, extra={"color_message": color_message})

        self.process = get_subprocess(
            config=self.config, target=self.target, sockets=self.sockets
        )
        self.process.start()


def _app_factory() -> "FastAPI":  # noqa: F821
    """Module-level factory used by uvicorn (picklable on Windows spawn).

    In reload mode the child is a freshly-spawned process, so we re-read
    the config from the path stashed in `CRAWLER_CONFIG_PATH` by the parent.
    """
    config_path = os.environ.get(_CONFIG_PATH_ENV)
    if not config_path:
        raise RuntimeError(f"{_CONFIG_PATH_ENV} not set; cannot build web app")
    config = SchedulerConfig.from_toml(config_path)
    return create_app(config, config_path)


def _start_web_server(config: SchedulerConfig, config_path: str) -> threading.Thread:
    """Run the FastAPI JSON API on a dedicated daemon thread."""
    os.environ[_CONFIG_PATH_ENV] = str(Path(config_path).resolve())

    common = dict(host=config.web.host, port=config.web.port, log_level="info")

    def _run() -> None:
        app_target = "main:_app_factory" if config.web.debugger else _app_factory
        uvicorn_config = uvicorn.Config(
            app_target,
            factory=True,
            reload=config.web.debugger,
            reload_dirs=[_BACKEND_DIR] if config.web.debugger else None,
            **common,
        )
        server = uvicorn.Server(uvicorn_config)
        if config.web.debugger:
            sock = uvicorn_config.bind_socket()
            _ThreadSafeReload(uvicorn_config, target=server.run, sockets=[sock]).run()
        else:
            server.run()

    thread = threading.Thread(target=_run, name="web-server", daemon=True)
    thread.start()
    return thread


async def main(config_path: str = "config.toml"):
    config = SchedulerConfig.from_toml(config_path)
    config.validate()  # 启动时校验配置合法性（必填项、环境变量等）
    runtime = await build_runtime(config, config_path)
    workers = runtime.workers
    try:
        if not runtime.active_quota_count:
            logger.warning(
                "No enabled platform quota found; rpc_crawl uses the default quota while "
                "the other workers continue running."
            )

        web_thread = _start_web_server(config, config_path)
        logger.info(
            "JSON API service starting on %s:%s (thread=%s)",
            config.web.host,
            config.web.port,
            web_thread.name,
        )

        if sys.platform != "win32":
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, runtime.request_stop)

        logger.info(
            "Starting scheduler with %d worker(s): %s",
            len(workers),
            [worker.executor for worker in workers],
        )
        await _run_workers(workers)
    finally:
        await runtime.close()
        logger.info("Scheduler stopped, resources cleaned up.")


async def _run_workers(workers) -> None:
    tasks = [asyncio.create_task(worker.run()) for worker in workers]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


if __name__ == "__main__":
    asyncio.run(main())
