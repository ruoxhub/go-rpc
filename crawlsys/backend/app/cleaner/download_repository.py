"""待下载清洗素材的查询与原子状态更新。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import text

from common.errors import redact_secrets
from storage import SQLAlchemyDB


@dataclass(frozen=True)
class DownloadCandidate:
    material_id: int
    platform: str
    content_id: str
    media_id: int | None
    media_url: str
    pic_url: str | None = None
    page_url: str | None = None
    music_url: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadJob:
    candidate: DownloadCandidate | None
    material_id: int
    platform: str
    content_id: str
    claim_token: str
    attempt_count: int
    input_error: str | None = None


class _ConcurrentUpdate(Exception):
    pass


class VideoDownloadRepository:
    def __init__(self, db: SQLAlchemyDB):
        self._db = db

    async def fetch_batch(
        self, *, min_grade: int, batch_size: int, platform: str | None = None,
        source: str = "media", offset: int = 0,
    ) -> list[DownloadCandidate]:
        platform_sql = "AND mc.platform = :platform" if platform else ""
        statement = text(f"""
            SELECT mc.id AS material_id, mc.platform, mc.content_id,
                   c.extend, c.pic AS content_pic_url
            FROM t_material_clean mc
            INNER JOIN t_busi_content c
              ON c.platform = mc.platform AND c.content_id = mc.content_id
            WHERE mc.clean_status = 'graded'
              AND mc.is_delete = 0
              AND mc.grade_rank BETWEEN 1 AND :min_grade
              AND COALESCE(c.is_download, false) = false
              AND c.extend IS NOT NULL AND c.extend <> ''
              {platform_sql}
            ORDER BY mc.grade_rank ASC, mc.id ASC
            LIMIT :batch_size OFFSET :offset
        """)
        if batch_size <= 0:
            return []

        candidates: list[DownloadCandidate] = []
        valid_seen = 0
        raw_offset = 0
        async with self._db.asession_scope() as session:
            while len(candidates) < batch_size:
                params = {
                    "min_grade": min_grade,
                    "batch_size": batch_size,
                    "offset": raw_offset,
                }
                if platform:
                    params["platform"] = platform
                rows = (await session.execute(statement, params)).mappings().all()
                if not rows:
                    break
                raw_offset += len(rows)
                for row in rows:
                    candidate = self._to_candidate(row)
                    if candidate is None:
                        continue
                    if valid_seen < offset:
                        valid_seen += 1
                        continue
                    candidates.append(candidate)
                    if len(candidates) == batch_size:
                        break
                if len(rows) < batch_size:
                    break
        return candidates

    async def claim_batch(
        self,
        *,
        min_grade: int,
        batch_size: int,
        platform: str | None,
        offset: int,
        claim_token: str,
        now: datetime,
        stale_before: datetime,
        max_attempts: int,
    ) -> list[DownloadJob]:
        if batch_size <= 0:
            return []
        platform_sql = "AND mc.platform = :platform" if platform else ""
        statement = text(f"""
            WITH candidates AS (
                SELECT mc.id AS material_id, mc.platform, mc.content_id,
                       mc.grade_rank, c.extend, c.pic AS content_pic_url
                FROM t_material_clean AS mc
                INNER JOIN t_busi_content AS c
                  ON c.platform = mc.platform AND c.content_id = mc.content_id
                WHERE mc.clean_status = 'graded'
                  AND mc.is_delete = 0
                  AND mc.grade_rank BETWEEN 1 AND :min_grade
                  AND COALESCE(c.is_download, false) = false
                  AND mc.download_attempt_count < :max_attempts
                  AND (
                      mc.download_next_retry_at IS NULL
                      OR mc.download_next_retry_at <= :now
                  )
                  AND (
                      mc.download_claim_token IS NULL
                      OR mc.download_claimed_at < :stale_before
                  )
                  {platform_sql}
                ORDER BY mc.grade_rank ASC, mc.id ASC
                FOR UPDATE OF mc SKIP LOCKED
                LIMIT :batch_size OFFSET :offset
            ),
            claimed AS (
                UPDATE t_material_clean AS mc
                SET download_claim_token = :claim_token,
                    download_claimed_at = :now,
                    download_attempt_count = mc.download_attempt_count + 1,
                    updated_time = :now
                FROM candidates AS candidate
                WHERE mc.id = candidate.material_id
                RETURNING candidate.material_id, candidate.platform,
                          candidate.content_id, candidate.grade_rank,
                          candidate.extend, candidate.content_pic_url,
                          mc.download_claim_token AS claim_token,
                          mc.download_attempt_count AS attempt_count
            )
            SELECT material_id, platform, content_id, extend, content_pic_url,
                   claim_token, attempt_count
            FROM claimed
            ORDER BY grade_rank ASC, material_id ASC
        """)
        params = {
            "min_grade": min_grade,
            "batch_size": batch_size,
            "offset": offset,
            "claim_token": claim_token,
            "now": now,
            "stale_before": stale_before,
            "max_attempts": max_attempts,
        }
        if platform:
            params["platform"] = platform
        async with self._db.asession_scope() as session:
            rows = (await session.execute(statement, params)).mappings().all()
        return [self._to_job(row) for row in rows]

    @staticmethod
    def _to_candidate(row) -> DownloadCandidate | None:
        return VideoDownloadRepository._parse_candidate(row)[0]

    @staticmethod
    def _parse_candidate(row) -> tuple[DownloadCandidate | None, str | None]:
        try:
            extend = row["extend"]
            if isinstance(extend, str):
                extend = json.loads(extend)
        except (TypeError, ValueError):
            return None, "invalid content extend JSON"
        if not isinstance(extend, dict):
            return None, "content extend must be an object"
        pic_url = extend.get("pic_url") or row["content_pic_url"]
        if not extend.get("video_url") or not extend.get("music_url") or not pic_url:
            return None, "missing video, audio, or cover URL"
        return DownloadCandidate(
            material_id=row["material_id"],
            platform=row["platform"],
            content_id=row["content_id"],
            media_id=None,
            media_url=extend["video_url"],
            music_url=extend["music_url"],
            pic_url=pic_url,
        ), None

    @classmethod
    def _to_job(cls, row) -> DownloadJob:
        candidate, input_error = cls._parse_candidate(row)
        return DownloadJob(
            candidate=candidate,
            material_id=row["material_id"],
            platform=row["platform"],
            content_id=row["content_id"],
            claim_token=row["claim_token"],
            attempt_count=row["attempt_count"],
            input_error=input_error,
        )

    async def mark_succeeded(self, job: DownloadJob) -> bool:
        try:
            async with self._db.asession_scope() as session:
                material = await session.execute(text("""
                    UPDATE t_material_clean
                    SET clean_status = 'downloaded', download_claim_token = NULL,
                        download_claimed_at = NULL, download_next_retry_at = NULL,
                        download_last_error = NULL, updated_time = now()
                    WHERE id = :material_id AND download_claim_token = :claim_token
                    RETURNING platform, content_id
                """), {
                    "material_id": job.material_id,
                    "claim_token": job.claim_token,
                })
                owner = material.mappings().first()
                if owner is None:
                    return False
                content = await session.execute(text("""
                    UPDATE t_busi_content
                    SET is_download = true, updated_time = now()
                    WHERE platform = :platform AND content_id = :content_id
                """), dict(owner))
                if content.rowcount != 1:
                    raise _ConcurrentUpdate
        except _ConcurrentUpdate:
            return False
        return True

    async def mark_failed(
        self,
        job: DownloadJob,
        error: str,
        next_retry_at: datetime | None,
        *,
        max_attempts: int,
        permanent: bool = False,
    ) -> bool:
        async with self._db.asession_scope() as session:
            result = await session.execute(text("""
                UPDATE t_material_clean
                SET download_claim_token = NULL, download_claimed_at = NULL,
                    download_attempt_count = CASE
                        WHEN :permanent THEN :max_attempts
                        ELSE download_attempt_count
                    END,
                    download_next_retry_at = :next_retry_at,
                    download_last_error = :error,
                    updated_time = now()
                WHERE id = :material_id AND download_claim_token = :claim_token
            """), {
                "material_id": job.material_id,
                "claim_token": job.claim_token,
                "permanent": permanent,
                "max_attempts": max_attempts,
                "next_retry_at": None if permanent else next_retry_at,
                "error": redact_secrets(error)[:500],
            })
        return result.rowcount == 1

    async def release_claim(self, job: DownloadJob) -> bool:
        async with self._db.asession_scope() as session:
            result = await session.execute(text("""
                UPDATE t_material_clean
                SET download_claim_token = NULL, download_claimed_at = NULL,
                    updated_time = now()
                WHERE id = :material_id AND download_claim_token = :claim_token
            """), {
                "material_id": job.material_id,
                "claim_token": job.claim_token,
            })
        return result.rowcount == 1

    async def mark_downloaded(self, candidate: DownloadCandidate) -> bool:
        """仅当素材和内容仍待处理时，在同一事务完成两个更新。"""
        try:
            async with self._db.asession_scope() as session:
                content = await session.execute(text("""
                    UPDATE t_busi_content SET is_download = true, updated_time = now()
                    WHERE platform = :platform AND content_id = :content_id
                      AND COALESCE(is_download, false) = false
                      AND EXISTS (
                        SELECT 1 FROM t_material_clean
                        WHERE id = :material_id AND clean_status = 'graded'
                      )
                """), {
                    "platform": candidate.platform,
                    "content_id": candidate.content_id,
                    "material_id": candidate.material_id,
                })
                if content.rowcount != 1:
                    raise _ConcurrentUpdate
                material = await session.execute(text("""
                    UPDATE t_material_clean
                    SET clean_status = 'downloaded', updated_time = now()
                    WHERE id = :material_id AND clean_status = 'graded'
                """), {"material_id": candidate.material_id})
                if material.rowcount != 1:
                    raise _ConcurrentUpdate
        except _ConcurrentUpdate:
            return False
        return True
