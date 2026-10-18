"""PostgreSQL access for the grading cleaner."""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sqlalchemy import text

from storage import SQLAlchemyDB
from runtime_config.filters import compile_filters
from runtime_config.models import FilterRule


@dataclass(frozen=True)
class ContentCandidate:
    id: int
    content_id: str | None
    platform: str
    pub_time: datetime | None
    view_count: int | None
    download_time: datetime | None
    created_time: datetime | None
    change_time: datetime


@dataclass(frozen=True)
class MaterialRecord:
    platform: str
    content_id: str
    grade_rank: int
    grade_reason: str
    grade_time: datetime
    snap_view_count: int | None
    snap_pub_time: datetime | None
    snap_hours: float | None
    clean_status: str
    expire_time: datetime


@dataclass(frozen=True, slots=True)
class CleanCursorPosition:
    watermark_ts: datetime
    watermark_id: int


_CURSOR_EPOCH = CleanCursorPosition(datetime(1900, 1, 1), 0)

_MATERIAL_UPSERT_SQL = text(
    """
    INSERT INTO t_material_clean
      (datatype, platform, content_id, grade_rank, grade_reason,
       grade_time, snap_view_count, snap_pub_time, snap_hours,
       clean_status, expire_time)
    VALUES
      ('clean', :platform, :content_id, :grade_rank, :grade_reason,
       :grade_time, :snap_view_count, :snap_pub_time, :snap_hours,
       :clean_status, :expire_time)
    ON CONFLICT (platform, content_id) DO UPDATE SET
      grade_rank = CASE
          WHEN t_material_clean.grade_rank = -1
               AND EXCLUDED.grade_rank > 0
          THEN EXCLUDED.grade_rank
          WHEN EXCLUDED.grade_rank = -1
          THEN t_material_clean.grade_rank
          ELSE LEAST(EXCLUDED.grade_rank, t_material_clean.grade_rank)
      END,
      grade_reason = CASE
          WHEN (
              t_material_clean.grade_rank = -1
              AND EXCLUDED.grade_rank > 0
          ) OR (
              EXCLUDED.grade_rank > 0
              AND EXCLUDED.grade_rank < t_material_clean.grade_rank
          )
          THEN EXCLUDED.grade_reason
          ELSE t_material_clean.grade_reason
      END,
      grade_time = EXCLUDED.grade_time,
      snap_view_count = EXCLUDED.snap_view_count,
      snap_pub_time = EXCLUDED.snap_pub_time,
      snap_hours = EXCLUDED.snap_hours,
      clean_status = CASE
          WHEN (
              t_material_clean.grade_rank = -1
              AND EXCLUDED.grade_rank > 0
          ) OR (
              EXCLUDED.grade_rank > 0
              AND EXCLUDED.grade_rank < t_material_clean.grade_rank
          )
          THEN EXCLUDED.clean_status
          ELSE t_material_clean.clean_status
      END,
      updated_time = now()
    """
)

_CURSOR_UPSERT_SQL = text(
    """
    INSERT INTO t_video_clean_cursor
      (consumer_key, platform, policy_hash, watermark_ts, watermark_id)
    VALUES
      (:consumer_key, :platform, :policy_hash, :watermark_ts, :watermark_id)
    ON CONFLICT (consumer_key, platform) DO UPDATE SET
      policy_hash = EXCLUDED.policy_hash,
      watermark_ts = EXCLUDED.watermark_ts,
      watermark_id = EXCLUDED.watermark_id,
      updated_time = now()
    WHERE t_video_clean_cursor.policy_hash <> EXCLUDED.policy_hash
       OR (EXCLUDED.watermark_ts, EXCLUDED.watermark_id) >
          (t_video_clean_cursor.watermark_ts, t_video_clean_cursor.watermark_id)
    """
)


def as_naive_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


class CleanerRepository:
    def __init__(self, db: SQLAlchemyDB):
        self._db = db

    async def scan_batch(
        self,
        platform: str,
        watermark_ts: datetime,
        watermark_id: int,
        batch_size: int,
        filters: list[FilterRule] | None = None,
    ) -> list[ContentCandidate]:
        compiled_filters = compile_filters(filters or [])
        filter_sql = f"\n              AND ({compiled_filters.sql})" if compiled_filters.sql else ""
        statement = text(
            f"""
            SELECT id, content_id, platform, pub_time, view_count,
                   download_time, created_time,
                   COALESCE(updated_time, created_time) AS change_time
            FROM t_busi_content
            WHERE platform = :platform
              AND (
                    COALESCE(updated_time, created_time) > :wm_ts
                 OR (
                        COALESCE(updated_time, created_time) = :wm_ts
                    AND id > :wm_id
                 )
              )
              {filter_sql}
            ORDER BY COALESCE(updated_time, created_time) ASC, id ASC
            LIMIT :batch_size
            """
        )
        params = {
            "platform": platform,
            "wm_ts": as_naive_utc(watermark_ts),
            "wm_id": watermark_id,
            "batch_size": batch_size,
            **compiled_filters.params,
        }
        async with self._db.asession_scope() as session:
            result = await session.execute(statement, params)
            return [ContentCandidate(**dict(row)) for row in result.mappings().all()]

    async def upsert_materials(self, rows: list[MaterialRecord]) -> int:
        if not rows:
            return 0
        async with self._db.asession_scope() as session:
            await self._upsert_materials(session, rows)
        return len(rows)

    async def load_cursor(
        self, consumer_key: str, platform: str, policy_hash: str
    ) -> CleanCursorPosition:
        statement = text(
            """
            SELECT policy_hash, watermark_ts, watermark_id
            FROM t_video_clean_cursor
            WHERE consumer_key = :consumer_key AND platform = :platform
            """
        )
        async with self._db.asession_scope() as session:
            result = await session.execute(
                statement,
                {"consumer_key": consumer_key, "platform": platform},
            )
            row = result.mappings().one_or_none()
        if row is None or row["policy_hash"] != policy_hash:
            return _CURSOR_EPOCH
        return CleanCursorPosition(row["watermark_ts"], row["watermark_id"])

    async def commit_batch(
        self,
        consumer_key: str,
        platform: str,
        policy_hash: str,
        rows: list[MaterialRecord],
        cursor: CleanCursorPosition,
    ) -> int:
        async with self._db.asession_scope() as session:
            await self._upsert_materials(session, rows)
            await session.execute(
                _CURSOR_UPSERT_SQL,
                {
                    "consumer_key": consumer_key,
                    "platform": platform,
                    "policy_hash": policy_hash,
                    "watermark_ts": as_naive_utc(cursor.watermark_ts),
                    "watermark_id": cursor.watermark_id,
                },
            )
        return len(rows)

    async def _upsert_materials(self, session, rows: list[MaterialRecord]) -> None:
        if not rows:
            return
        params = []
        for row in rows:
            values = asdict(row)
            for name in ("grade_time", "snap_pub_time", "expire_time"):
                values[name] = as_naive_utc(values[name])
            params.append(values)
        await session.execute(_MATERIAL_UPSERT_SQL, params)

    async def purge_expired(self, now: datetime) -> int:
        statement = text(
            "DELETE FROM t_material_clean WHERE expire_time < :now"
        )
        async with self._db.asession_scope() as session:
            result = await session.execute(
                statement,
                {"now": as_naive_utc(now)},
            )
            return result.rowcount
