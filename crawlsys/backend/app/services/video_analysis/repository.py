"""PostgreSQL repository for video-analysis job state transitions."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import text

from storage import SQLAlchemyDB
from storage.exceptions import SQLOperationError

from .batch import ModelSnapshot


@dataclass(frozen=True)
class AnalysisJob:
    material_id: int
    platform: str
    content_id: str
    attempt_count: int


class VideoAnalysisRepository:
    def __init__(self, db: SQLAlchemyDB):
        self._db = db

    async def claim_batch(
        self,
        *,
        batch_size: int,
        bucket: str,
        model: ModelSnapshot,
        max_attempts: int,
        now: datetime,
    ) -> list[AnalysisJob]:
        statement = text(
            """
            WITH candidates AS (
                SELECT mc.id AS material_id, mc.platform, mc.content_id
                FROM t_material_clean AS mc
                LEFT JOIN t_video_analysis_result AS var
                  ON var.platform = mc.platform
                 AND var.content_id = mc.content_id
                WHERE mc.is_delete = 0
                  AND mc.clean_status = 'downloaded'
                  AND mc.is_analysis IN (0, 3)
                  AND COALESCE(var.attempt_count, 0) < :max_attempts
                  AND EXISTS (
                      SELECT 1
                      FROM t_busi_content AS content
                      WHERE content.platform = mc.platform
                        AND content.content_id = mc.content_id
                        AND content.is_download = true
                  )
                ORDER BY mc.grade_rank ASC, mc.id ASC
                FOR UPDATE OF mc SKIP LOCKED
                LIMIT :batch_size
            ),
            claimed AS (
                UPDATE t_material_clean AS mc
                SET is_analysis = 2,
                    updated_time = :now
                FROM candidates AS candidate
                WHERE mc.id = candidate.material_id
                RETURNING candidate.material_id,
                          candidate.platform,
                          candidate.content_id
            ),
            upserted AS (
                INSERT INTO t_video_analysis_result
                    (platform, content_id, minio_bucket, status, attempt_count,
                     llm_model_id, model, started_time, finished_time, analysis_result,
                     error_message, updated_time)
                SELECT platform, content_id, :bucket, 'processing', 1,
                       :llm_model_id, :model, :now, NULL, NULL, NULL, :now
                FROM claimed
                ON CONFLICT (platform, content_id) DO UPDATE SET
                    minio_bucket = EXCLUDED.minio_bucket,
                    status = 'processing',
                    attempt_count =
                        t_video_analysis_result.attempt_count + 1,
                    llm_model_id = EXCLUDED.llm_model_id,
                    model = EXCLUDED.model,
                    started_time = EXCLUDED.started_time,
                    finished_time = NULL,
                    analysis_result = NULL,
                    error_message = NULL,
                    updated_time = EXCLUDED.updated_time
                RETURNING platform, content_id, attempt_count
            )
            SELECT claimed.material_id, claimed.platform, claimed.content_id,
                   upserted.attempt_count
            FROM claimed
            JOIN upserted
              ON upserted.platform = claimed.platform
             AND upserted.content_id = claimed.content_id
            """
        )
        params = {
            "batch_size": batch_size,
            "bucket": bucket,
            "llm_model_id": model.id,
            "model": model.name,
            "max_attempts": max_attempts,
            "now": now,
        }
        async with self._db.asession_scope() as session:
            result = await session.execute(statement, params)
            return [AnalysisJob(**dict(row)) for row in result.mappings().all()]

    async def mark_succeeded(
        self,
        *,
        job: AnalysisJob,
        object_name: str,
        result: dict[str, Any],
        finished_at: datetime,
        bucket: str | None = None,
    ) -> None:
        result_statement = text(
            """
            UPDATE t_video_analysis_result
            SET status = 'succeeded',
                minio_bucket = COALESCE(:bucket, minio_bucket),
                minio_object_name = :object_name,
                analysis_result = CAST(:result AS JSONB),
                error_message = NULL,
                finished_time = :finished_at,
                updated_time = :finished_at
            WHERE platform = :platform
              AND content_id = :content_id
              AND status = 'processing'
              AND attempt_count = :attempt_count
            """
        )
        params = {
            "platform": job.platform,
            "content_id": job.content_id,
            "attempt_count": job.attempt_count,
            "bucket": bucket,
            "object_name": object_name,
            "result": json.dumps(result, ensure_ascii=False),
            "finished_at": finished_at,
        }
        await self._finish(
            result_statement,
            params,
            material_id=job.material_id,
            material_state=1,
            finished_at=finished_at,
        )

    async def mark_failed(
        self,
        *,
        job: AnalysisJob,
        object_name: str | None,
        error_message: str,
        finished_at: datetime,
        bucket: str | None = None,
    ) -> None:
        result_statement = text(
            """
            UPDATE t_video_analysis_result
            SET status = 'failed',
                minio_bucket = COALESCE(:bucket, minio_bucket),
                minio_object_name =
                    COALESCE(:object_name, minio_object_name),
                error_message = :error_message,
                finished_time = :finished_at,
                updated_time = :finished_at
            WHERE platform = :platform
              AND content_id = :content_id
              AND status = 'processing'
              AND attempt_count = :attempt_count
            """
        )
        params = {
            "platform": job.platform,
            "content_id": job.content_id,
            "attempt_count": job.attempt_count,
            "bucket": bucket,
            "object_name": object_name,
            "error_message": error_message,
            "finished_at": finished_at,
        }
        await self._finish(
            result_statement,
            params,
            material_id=job.material_id,
            material_state=3,
            finished_at=finished_at,
        )

    async def mark_cancelled(
        self,
        jobs: list[AnalysisJob],
        *,
        finished_at: datetime,
    ) -> int:
        """恢复本轮仍处于 processing 的任务，不覆盖已完成或新 attempt。"""
        if not jobs:
            return 0
        statement = text(
            """
            WITH requested AS (
                SELECT *
                FROM jsonb_to_recordset(CAST(:jobs AS JSONB)) AS item(
                    material_id BIGINT,
                    platform TEXT,
                    content_id TEXT,
                    attempt_count INTEGER
                )
            ),
            cancelled AS (
                UPDATE t_video_analysis_result AS result
                SET status = 'failed',
                    error_message = 'AnalysisCancelled',
                    finished_time = :finished_at,
                    updated_time = :finished_at
                FROM requested
                WHERE result.platform = requested.platform
                  AND result.content_id = requested.content_id
                  AND result.attempt_count = requested.attempt_count
                  AND result.status = 'processing'
                RETURNING requested.material_id
            ),
            reset_materials AS (
                UPDATE t_material_clean AS material
                SET is_analysis = 3,
                    updated_time = :finished_at
                FROM cancelled
                WHERE material.id = cancelled.material_id
                  AND material.is_analysis = 2
                RETURNING material.id
            )
            SELECT COUNT(*) FROM cancelled
            """
        )
        payload = [
            {
                "material_id": job.material_id,
                "platform": job.platform,
                "content_id": job.content_id,
                "attempt_count": job.attempt_count,
            }
            for job in jobs
        ]
        async with self._db.asession_scope() as session:
            result = await session.execute(
                statement,
                {"jobs": json.dumps(payload), "finished_at": finished_at},
            )
            return result.scalar_one()

    async def _finish(
        self,
        result_statement: Any,
        params: dict[str, Any],
        *,
        material_id: int,
        material_state: int,
        finished_at: datetime,
    ) -> None:
        if material_state == 1:
            material_statement = text(
                """
                UPDATE t_material_clean
                SET is_analysis = 1,
                    updated_time = :finished_at
                WHERE id = :material_id
                  AND is_analysis = 2
                """
            )
        else:
            material_statement = text(
                """
                UPDATE t_material_clean
                SET is_analysis = 3,
                    updated_time = :finished_at
                WHERE id = :material_id
                  AND is_analysis = 2
                """
            )
        async with self._db.asession_scope() as session:
            result_update = await session.execute(result_statement, params)
            if result_update.rowcount != 1:
                raise SQLOperationError(
                    "video analysis result was not in processing state"
                )
            material_update = await session.execute(
                material_statement,
                {
                    "material_id": material_id,
                    "finished_at": finished_at,
                },
            )
            if material_update.rowcount != 1:
                raise SQLOperationError(
                    "video analysis material was not in processing state"
                )

    async def reap_stale(
        self,
        *,
        cutoff: datetime,
        finished_at: datetime,
    ) -> int:
        statement = text(
            """
            WITH stale AS (
                UPDATE t_video_analysis_result
                SET status = 'failed',
                    error_message =
                        'AnalysisTimeout: processing exceeded stale timeout',
                    finished_time = :finished_at,
                    updated_time = :finished_at
                WHERE status = 'processing'
                  AND started_time < :cutoff
                RETURNING platform, content_id
            ),
            reset_materials AS (
                UPDATE t_material_clean AS mc
                SET is_analysis = 3,
                    updated_time = :finished_at
                FROM stale
                WHERE mc.platform = stale.platform
                  AND mc.content_id = stale.content_id
                  AND mc.is_analysis = 2
                RETURNING mc.id
            )
            SELECT COUNT(*) FROM stale
            """
        )
        async with self._db.asession_scope() as session:
            result = await session.execute(
                statement,
                {"cutoff": cutoff, "finished_at": finished_at},
            )
            return result.scalar_one()
