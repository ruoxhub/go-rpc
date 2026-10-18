from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, TYPE_CHECKING, TypedDict
from sqlalchemy import DateTime, String, Text, TIMESTAMP
from common.logging import get_logger
from storage import SQLAlchemyDB
from filter import Bloom
from common.retry import retry_async, RETRYABLE_EXCEPTIONS
# 直接从 models.base 取注册表，避免 via core 包触发 core.__init__ → Worker → pipeline 循环导入
from models.base import UNIQUE_FIELD_MAPPING, UPDATE_FIELD_MAPPING, DATATYPE_TO_MODEL

if TYPE_CHECKING:
    from models import Base


logger = get_logger(__file__)


def _resolve_update_key_fields(model_class: type, unique_field: str) -> list[str]:
    table = model_class.__table__
    if "platform" in table.columns and unique_field in table.columns:
        return ["platform", unique_field]
    return [unique_field]


class PipelineStats(TypedDict):
    inserted: int
    updated: int
    skipped: int
    errors: int


class PipelineNotInitializedError(Exception):
    """管道未初始化异常"""
    pass


class InvalidDataTypeError(ValueError):
    """无效的数据类型异常"""
    pass

class CrawlerPipeline:
    """通用处理器管道 - 集成布隆过滤器去重和数据库插入/更新

    支持多业务模型 (BusUser, BusPost, BusVideo, BusComment 等) 和多平台 (platform) 的去重策略。

    去重 Key 格式：{datatype}:{platform}
    - datatype: 数据类型标识，如 user、post、video、comment
    - platform: 平台标识，如 tiktok、twitter、facebook

    特性:
    - 即时处理，无缓冲区延迟
    - 支持批量布隆过滤器检查 (process_items)
    - 完善的异常处理和资源管理
    """

    # ==================== 类常量定义 ====================
    DATATYPE_TO_MODEL = DATATYPE_TO_MODEL
    UNIQUE_FIELD_MAPPING = UNIQUE_FIELD_MAPPING
    UPDATE_FIELD_MAPPING = UPDATE_FIELD_MAPPING

    # ==================== 初始化与生命周期 ====================

    def __init__(
        self,
        filter: Bloom | None,
        store: SQLAlchemyDB | None,
    ):
        """初始化通用管道"""
        self._filter: Bloom | None = filter
        self._store: SQLAlchemyDB | None = store
        self._string_col_cache: dict[str, list[str]] = {}


    async def close(self) -> None:
        """关闭管道，清理资源"""
        try:
            self._filter = None
            self._store = None
            self._string_col_cache.clear()
            logger.info("管道关闭完成")
        except Exception as e:
            logger.error(f"管道关闭时发生错误：{e}")


    def _sanitize_string_fields(self, item: Base) -> None:
        """剥离 ORM 实例中所有 VARCHAR/TEXT 列的 NUL 字节（\\x00）。

        PostgreSQL 的 text/varchar 不接受 NUL；Bilibili 等平台的原始数据偶发
        含 NUL（如评论内容 '\\x00\\x00'），不清洗将导致 asyncpg 抛
        CharacterNotInRepertoireError，整批事务失败并被 Worker 无限重试。
        """
        table_name = item.__tablename__
        str_cols = self._string_col_cache.get(table_name)
        if str_cols is None:
            try:
                str_cols = [
                    col.name for col in item.__table__.columns
                    if isinstance(col.type, (String, Text))
                ]
            except AttributeError:
                str_cols = []
            self._string_col_cache[table_name] = str_cols

        for col_name in str_cols:
            value = getattr(item, col_name, None)
            if isinstance(value, str) and "\x00" in value:
                setattr(item, col_name, value.replace("\x00", ""))

    def _normalize_datetime_fields(self, item: Base) -> None:
        """将带时区的时间戳转为 naive UTC 时间，满足 PostgreSQL TIMESTAMP WITHOUT TIME ZONE。"""
        table_name = getattr(item, "__tablename__", None)
        if not table_name:
            return
        dt_cols = getattr(self, "_datetime_col_cache", {}).get(table_name)
        if dt_cols is None:
            if not hasattr(self, "_datetime_col_cache"):
                self._datetime_col_cache = {}
            try:
                dt_cols = [
                    col.name for col in item.__table__.columns
                    if isinstance(col.type, (DateTime, TIMESTAMP))
                ]
            except AttributeError:
                dt_cols = []
            self._datetime_col_cache[table_name] = dt_cols

        for col_name in dt_cols:
            val = getattr(item, col_name, None)
            if isinstance(val, datetime) and val.tzinfo is not None:
                # 转换至 UTC 并移除时区信息
                setattr(item, col_name, val.astimezone(timezone.utc).replace(tzinfo=None))


    # ==================== 核心处理方法 ====================

    def _ensure_initialized(self) -> None:
        """确保管道已正确初始化"""
        if self._filter is None or self._store is None:
            raise PipelineNotInitializedError(
                "Pipeline not initialized: filter or store is None"
            )


    async def _process_item(
        self,
        item: Base,
        stats: PipelineStats,
        insert_batch_buffer: list[Base],
        update_batch_buffer: list[Base],
        seen_in_batch: set | None = None,
    ) -> Base | None:
        """处理单个数据项：通过 acheck 判断去重，路由到 insert 或 update 缓冲区"""

        if not item:
            return None

        self._sanitize_string_fields(item)
        self._normalize_datetime_fields(item)

        datatype = getattr(item, "datatype", None)
        platform = getattr(item, 'platform', None)

        unique_field = UNIQUE_FIELD_MAPPING.get(datatype)
        item_unique_val = getattr(item, unique_field, None) if unique_field else None

        if item_unique_val is None:
            logger.warning(f"item 缺少唯一字段 '{unique_field}'，跳过去重检查")
            stats["skipped"] += 1
            return None

        prefix = f"{datatype}:{platform}"
        val = str(item_unique_val)
        cache_key = f"{prefix}:{val}"

        # 检查同批次内是否有重复项
        if seen_in_batch is not None and cache_key in seen_in_batch:
            is_new = False
        else:
            try:
                is_new = not (await self._filter.acheck(val, prefix))
            except Exception as e:
                logger.error(f"布隆过滤器操作失败：{e}，按新元素回退插入")
                is_new = True

            if is_new and seen_in_batch is not None:
                seen_in_batch.add(cache_key)

        if is_new:
            insert_batch_buffer.append(item)
        else:
            update_batch_buffer.append(item)

    async def process_item(self, item: Base) -> PipelineStats:
        """处理单个数据项"""
        self._ensure_initialized()

        insert_batch_buffer: list[Base] = []
        update_batch_buffer: list[Base] = []
        stats: PipelineStats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

        await self._process_item(item, stats, insert_batch_buffer, update_batch_buffer)

        if insert_batch_buffer:
            await self._insert_items(insert_batch_buffer, stats)

        if update_batch_buffer:
            await self._update_items(update_batch_buffer, stats)

        return stats

    async def process_items(
        self,
        items: list[Base],
    ) -> PipelineStats:
        """批量处理数据项

        Args:
            items: SQLAlchemy 模型实例列表

        Returns:
            统计信息字典
        """
        self._ensure_initialized()

        if not items:
            return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

        stats: PipelineStats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

        # 1. 清洗 + 提取去重信息
        prepared: list[tuple[Base, str, str, str]] = []
        for item in items:
            self._sanitize_string_fields(item)
            self._normalize_datetime_fields(item)
            datatype = getattr(item, "datatype", None)
            platform = getattr(item, "platform", None)
            unique_field = UNIQUE_FIELD_MAPPING.get(datatype)
            val = getattr(item, unique_field, None) if unique_field else None
            if val is None:
                stats["skipped"] += 1
                continue
            prefix = f"{datatype}:{platform}"
            prepared.append((item, prefix, str(val), f"{prefix}:{val}"))

        if not prepared:
            return stats

        # 2. 按 prefix 分组，批量查询布隆过滤器
        prefix_vals: dict[str, list[str]] = defaultdict(list)
        for _, prefix, val, _ in prepared:
            prefix_vals[prefix].append(val)

        bloom_results: dict[str, dict[str, bool]] = {}
        for prefix, vals in prefix_vals.items():
            try:
                bloom_results[prefix] = await self._filter.abatch_check(vals, prefix)
            except Exception as e:
                logger.error(f"布隆过滤器批量检查失败 (prefix: {prefix}): {e}，全部视为新元素")
                bloom_results[prefix] = {}
                stats["errors"] += 1

        # 3. 分流到 insert / update 缓冲区（同批次内去重）
        insert_batch_buffer: list[Base] = []
        update_batch_buffer: list[Base] = []
        seen_in_batch: set[str] = set()

        for item, prefix, val, cache_key in prepared:
            exists = bloom_results.get(prefix, {}).get(val, False)
            if not exists and cache_key not in seen_in_batch:
                insert_batch_buffer.append(item)
                seen_in_batch.add(cache_key)
            else:
                update_batch_buffer.append(item)

        # 4. 执行写入
        if insert_batch_buffer:
            await self._insert_items(insert_batch_buffer, stats)
        if update_batch_buffer:
            await self._update_items(update_batch_buffer, stats)

        logger.debug(f"批量处理完成：{stats}")
        return stats


    @retry_async(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        exceptions=RETRYABLE_EXCEPTIONS,
    )
    async def _insert_items(
        self,
        items: list[Base],
        stats: PipelineStats
    ) -> None:
        """批量插入数据项（带重试）"""
        if not items:
            return

        await self._store.abulk_upsert(items)
        stats["inserted"] += len(items)
        logger.debug(f"成功插入 {len(items)} 条记录")

        # 插入成功后，批量将 key 添加到布隆过滤器
        prefix_to_vals = defaultdict(list)
        for item in items:
            datatype = getattr(item, "datatype", None)
            platform = getattr(item, "platform", None)
            unique_field = UNIQUE_FIELD_MAPPING.get(datatype)
            item_unique_val = getattr(item, unique_field, None) if unique_field else None
            if item_unique_val is not None:
                prefix = f"{datatype}:{platform}"
                prefix_to_vals[prefix].append(str(item_unique_val))

        for prefix, vals in prefix_to_vals.items():
            try:
                await self._filter.abatch_add(vals, prefix)
            except Exception as e:
                logger.error(f"批量写入布隆过滤器失败 (prefix: {prefix}): {e}")

    @retry_async(
        max_attempts=3,
        base_delay=0.5,
        max_delay=10.0,
        exceptions=RETRYABLE_EXCEPTIONS,
    )
    async def _update_items(
        self,
        items: list[Base],
        stats: PipelineStats
    ) -> None:
        """批量更新数据项（带重试）

        Args:
            items: SQLAlchemy 模型实例列表
            stats: 统计信息字典
        """
        if not items:
            return

        # 按模型类分组
        grouped_items: dict[type[Base], list[dict[str, Any]]] = defaultdict(list)

        for item in items:
            # 只把非 None 的值放入更新字典，避免把 Optional 字段或缺失的默认字段（如 repost_count）
            # 设置成 NULL，导致 NOT NULL 约束违反（尤其是更新路径下 parser 只提供部分字段时）。
            item_dict = {
                c.name: getattr(item, c.name)
                for c in item.__table__.columns
                if getattr(item, c.name) is not None
            }
            # Core abulk_update 不触发 ORM onupdate；回刷任务依赖 updated_time 前进做公平选片。
            if "updated_time" in item.__table__.columns and "updated_time" not in item_dict:
                item_dict["updated_time"] = datetime.now(timezone.utc).replace(tzinfo=None)
            grouped_items[item.__class__].append(item_dict)

        # 按分组执行批量更新
        for model_class, data_list in grouped_items.items():
            # WHERE 条件使用唯一字段（如 challenge_id），而非 update_fields（那些是 SET 的目标列）。
            # 此前误用 UPDATE_FIELD_MAPPING 作为 key_fields，导致 TkChallenge 的 WHERE 变成
            # title=? AND desc=?...（非唯一），SET 变成 challenge_id=?（不应更新唯一键）。
            datatype = data_list[0].get("datatype") if data_list else None
            unique_field = UNIQUE_FIELD_MAPPING.get(datatype)
            key_fields = (
                _resolve_update_key_fields(model_class, unique_field)
                if unique_field else None
            )

            if not key_fields:
                logger.warning(f"未找到 datatype '{datatype}' 的唯一字段映射，跳过更新")
                stats["skipped"] += len(data_list)
                continue

            updated_count = await self._store.abulk_update(
                class_model=model_class,
                data=data_list,
                key_fields=key_fields,
            )
            stats["updated"] += updated_count
            logger.debug(f"更新 {model_class.__name__} 类型 {updated_count} 条记录")
