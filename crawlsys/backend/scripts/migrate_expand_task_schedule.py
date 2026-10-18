"""Idempotent migration: extend t_crawl_task / t_busi_task_logs with schedule & retry fields.

Usage:
    cd backend && python -m scripts.migrate_expand_task_schedule

Idempotent: columns use ADD COLUMN IF NOT EXISTS, constraints query
pg_constraint before ALTER TABLE, and the index uses CREATE INDEX IF NOT EXISTS.
Existing rows keep working: every task gets schedule_type='manual'
(column NOT NULL DEFAULT), and legacy loop_enabled tasks become 'interval'.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from sqlalchemy import text

from core.config import SchedulerConfig
from storage import SQLAlchemyDB


def _add_constraint(table: str, name: str, check: str) -> str:
    return f"""DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = '{name}' AND conrelid = 'public.{table}'::regclass
    ) THEN
        ALTER TABLE public.{table} ADD CONSTRAINT {name} CHECK ({check});
    END IF;
END
$$"""

_MIGRATION_DDL = [
    # --- 新增调度字段 ---
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS schedule_type VARCHAR(20) NOT NULL DEFAULT 'manual'",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS cron_expression VARCHAR(100)",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS run_once_at TIMESTAMPTZ",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS schedule_start_at TIMESTAMPTZ",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS schedule_end_at TIMESTAMPTZ",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS max_runs INTEGER",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS run_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS last_run_status VARCHAR(20)",
    # --- 重试字段 ---
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS retry_max_attempts INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS retry_delay_seconds INTEGER NOT NULL DEFAULT 60",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS retry_backoff_multiplier DOUBLE PRECISION NOT NULL DEFAULT 2",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS retry_max_delay_seconds INTEGER NOT NULL DEFAULT 3600",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMPTZ",
    # --- 手动/合并触发与暂停 ---
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS run_now_requested_at TIMESTAMPTZ",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS pause_requested BOOLEAN NOT NULL DEFAULT FALSE",
    # --- 本次物理尝试的触发快照 ---
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS active_trigger VARCHAR(20)",
    "ALTER TABLE public.t_crawl_task ADD COLUMN IF NOT EXISTS active_scheduled_at TIMESTAMPTZ",
    # --- 日志可观测字段 ---
    "ALTER TABLE public.t_busi_task_logs ADD COLUMN IF NOT EXISTS btl_active_trigger VARCHAR(20)",
    "ALTER TABLE public.t_busi_task_logs ADD COLUMN IF NOT EXISTS btl_active_scheduled_at TIMESTAMPTZ",
    "ALTER TABLE public.t_busi_task_logs ADD COLUMN IF NOT EXISTS btl_retry_count INTEGER NOT NULL DEFAULT 0",
    # --- 枚举检查约束 ---
    _add_constraint("t_crawl_task", "ck_task_schedule_type", "schedule_type IN ('manual', 'once', 'interval', 'cron')"),
    _add_constraint("t_crawl_task", "ck_task_last_run_status", "last_run_status IS NULL OR last_run_status IN ('success', 'failed')"),
    _add_constraint("t_crawl_task", "ck_task_active_trigger", "active_trigger IS NULL OR active_trigger IN ('scheduled', 'retry', 'manual', 'coalesced')"),
    # --- 非负次数约束 ---
    _add_constraint("t_crawl_task", "ck_task_run_count_non_negative", "run_count >= 0"),
    _add_constraint("t_crawl_task", "ck_task_retry_count_non_negative", "retry_count >= 0"),
    _add_constraint("t_crawl_task", "ck_task_retry_max_attempts_non_negative", "retry_max_attempts >= 0"),
    _add_constraint("t_crawl_task", "ck_task_retry_backoff_multiplier_ge_1", "retry_backoff_multiplier >= 1"),
    _add_constraint("t_busi_task_logs", "ck_task_log_active_trigger", "btl_active_trigger IS NULL OR btl_active_trigger IN ('scheduled', 'retry', 'manual', 'coalesced')"),
    _add_constraint("t_busi_task_logs", "ck_task_log_retry_count_non_negative", "btl_retry_count >= 0"),
    # --- 到期领取索引 ---
    "CREATE INDEX IF NOT EXISTS idx_task_due ON public.t_crawl_task (status, next_retry_at, next_run_at)",
]

#: 旧数据回填：legacy loop 任务迁移为 interval；其余保持默认 manual。
_MIGRATION_DML = [
    "UPDATE public.t_crawl_task SET schedule_type = 'interval' WHERE loop_enabled = TRUE AND schedule_type = 'manual'",
]

MIGRATION_STATEMENTS = [*_MIGRATION_DDL, *_MIGRATION_DML]


async def run_migration(db) -> None:
    async with db.asession_scope() as session:
        for statement in MIGRATION_STATEMENTS:
            await session.execute(text(statement))


async def main() -> None:
    config = SchedulerConfig.from_toml("config.toml")
    pg = config.postgresql
    db = SQLAlchemyDB(
        username=pg.username, password=pg.password,
        host=pg.host, port=pg.port, database=pg.database,
        amode=True, driver="postgresql",
    )
    await db.aconnect()
    try:
        await run_migration(db)
        print("Done.")
    finally:
        await db.aclose()


if __name__ == "__main__":
    asyncio.run(main())
