"""视频素材分级清洗 Worker。"""
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from cleaner.engine import Grade, GradeRule, PlatformThresholds, grade
from cleaner.repository import CleanCursorPosition, CleanerRepository, MaterialRecord
from models import BusTask
from models.task_config import TaskConfig, VideoCleanTaskConfig
from runtime_config.models import FilterRule

from .base import BaseWorker
from .media_logging import log_media_event
from .result import WorkerResult

logger = logging.getLogger(__name__)


_TIKTOK_AIGC_FILTER = FilterRule(
    field="extend_data.aigcLabelType", operator=">", value=0
)


def _clean_filters(platform: str, policy: Any) -> list[FilterRule]:
    filters = list(getattr(policy, "filters", None) or [])
    if platform == "tiktok" and _TIKTOK_AIGC_FILTER not in filters:
        filters.append(_TIKTOK_AIGC_FILTER)
    return filters


def clean_policy_hash(
    thresholds: PlatformThresholds,
    filters: list[FilterRule],
    *,
    suspect_seconds: int,
    ttl_days: int,
) -> str:
    payload = {
        "p1": [[rule.max_hours, rule.min_views] for rule in thresholds.p1],
        "p2": [[rule.max_hours, rule.min_views] for rule in thresholds.p2],
        "p3": [[rule.max_hours, rule.min_views] for rule in thresholds.p3],
        "filters": [
            {"field": rule.field, "operator": rule.operator, "value": rule.value}
            for rule in filters
        ],
        "suspect_seconds": suspect_seconds,
        "ttl_days": ttl_days,
    }
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class VideoCleanWorker(BaseWorker):
    executor = "video_clean"

    def __init__(self, *args: Any, cleaner_repo: CleanerRepository | None = None,
                 platform_provider: Any = None, cleaner_config: Any = None,
                 **kwargs: Any):
        super().__init__(*args, **kwargs)
        dynamic = self.config_store is not None
        if dynamic and (platform_provider is None or cleaner_config is not None):
            raise ValueError("dynamic cleaner requires config_store and platform_provider only")
        if not dynamic and (cleaner_config is None or platform_provider is not None):
            raise ValueError("static cleaner requires cleaner_config only")
        self.cleaner_repo = cleaner_repo or CleanerRepository(self.db)
        self.platform_provider = platform_provider
        self._legacy_cleaner_config = cleaner_config

    async def execute_business(self, task: BusTask) -> WorkerResult:
        config = task.config if isinstance(task.config, TaskConfig) else TaskConfig.model_validate(task.config or {})
        return await self.run_batch(
            config.clean,
            task_id=task.task_id,
            consumer_key=f"task:{task.task_id}",
        )

    async def run_batch(
        self,
        options: VideoCleanTaskConfig | None = None,
        *,
        task_id: int | None = None,
        consumer_key: str | None = None,
    ) -> WorkerResult:
        options = options or VideoCleanTaskConfig()
        consumer_key = consumer_key or f"worker:{self.platform}"
        cfg = (await self.config_store.get_cleaner() if self.config_store is not None
               else self._legacy_cleaner_config)
        if not cfg.enabled:
            return WorkerResult()
        batch_size = options.batch_size or cfg.batch_size
        if options.platforms:
            platforms = options.platforms
        else:
            if self.platform_provider is None:
                platforms = self._legacy_cleaner_config.platforms
            else:
                rows = await self.platform_provider.find_all_enabled()
                platforms = [row.bs_platform_code for row in rows]
        total = succeeded = failed = skipped = 0
        now = datetime.now(timezone.utc)
        for platform in platforms:
            policy = (await self.config_store.get_platform_policy(platform)
                      if self.config_store is not None
                      else cfg.thresholds.get(platform))
            if policy is None:
                skipped += 1
                continue
            thresholds = policy if isinstance(policy, PlatformThresholds) else PlatformThresholds(
                p1=[GradeRule(rule.max_hours, rule.min_views) for rule in policy.p1],
                p2=[GradeRule(rule.max_hours, rule.min_views) for rule in policy.p2],
                p3=[GradeRule(rule.max_hours, rule.min_views) for rule in policy.p3],
            )
            filters = _clean_filters(platform, policy)
            policy_hash = clean_policy_hash(
                thresholds,
                filters,
                suspect_seconds=cfg.suspect_seconds,
                ttl_days=cfg.ttl_days,
            )
            cursor = await self.cleaner_repo.load_cursor(
                consumer_key, platform, policy_hash
            )
            for _ in range(cfg.max_batches_per_platform):
                batch = await self.cleaner_repo.scan_batch(
                    platform,
                    cursor.watermark_ts,
                    cursor.watermark_id,
                    batch_size,
                    filters,
                )
                if not batch:
                    break
                batch_id = uuid.uuid4().hex
                batch_started_at = time.monotonic()
                total += len(batch)
                rows = []
                for candidate in batch:
                    if not candidate.content_id:
                        skipped += 1
                        continue
                    result = grade(candidate.pub_time, candidate.view_count, thresholds, now=now,
                                   download_time=candidate.download_time, suspect_seconds=cfg.suspect_seconds)
                    if result.grade is Grade.UNRATED:
                        skipped += 1
                        continue
                    rows.append(MaterialRecord(
                        platform=candidate.platform, content_id=candidate.content_id,
                        grade_rank=result.grade.value, grade_reason=result.reason, grade_time=now,
                        snap_view_count=candidate.view_count, snap_pub_time=candidate.pub_time,
                        snap_hours=result.hours,
                        clean_status="manual_review" if result.grade is Grade.MANUAL_REVIEW else "graded",
                        expire_time=now + timedelta(days=cfg.ttl_days),
                    ))
                try:
                    last = batch[-1]
                    next_cursor = CleanCursorPosition(last.change_time, last.id)
                    succeeded += await self.cleaner_repo.commit_batch(
                        consumer_key,
                        platform,
                        policy_hash,
                        rows,
                        next_cursor,
                    )
                except Exception as exc:
                    log_media_event(
                        logger,
                        logging.ERROR,
                        task_id=task_id,
                        consumer_key=consumer_key,
                        platform=platform,
                        content_id=None,
                        batch_id=batch_id,
                        claim_token_prefix=None,
                        attempt_count=None,
                        outcome="failed",
                        latency_ms=max(
                            0, int((time.monotonic() - batch_started_at) * 1000)
                        ),
                        exception_type=type(exc).__name__,
                        error=exc,
                    )
                    failed += len(batch)
                    break
                cursor = next_cursor
                if len(batch) < batch_size:
                    break
        await self.cleaner_repo.purge_expired(datetime.now(timezone.utc))
        return WorkerResult(total=total, succeeded=succeeded, failed=failed, skipped=skipped)
