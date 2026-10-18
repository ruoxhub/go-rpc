from __future__ import annotations

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Awaitable, Callable, Mapping

from sqlalchemy import delete, func, select, update

from core.param_schema import InvalidActionParamSchema, normalize_action_param_schema
from models.action import Action
from models.action_parser import (
    ActionParserRevision,
    ActionParserRevisionSample,
    ActionParserSample,
)
from models.task import BusTask
from models.platform import platformSource
from models.task_config import TaskConfig
from parser.compatibility import SinkCompatibilityError, validate_sink_compatibility
from parser.definition import (
    ParserDefinition,
    definition_sha256,
    validate_parser_definition,
)
from services.parser_configuration.errors import ParserConfigurationError
from storage.sql import SQLAlchemyDB
from storage.exceptions import AlreadyExistsError, SQLOperationError


SampleObjectDelete = Callable[[ActionParserSample], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ActionRuntimeDefinition:
    params_schema: dict[str, Any] | bool | None
    parser_revision_id: int | None
    parser_definition: ParserDefinition | None


@dataclass(frozen=True, slots=True)
class ActionContext:
    ba_id: int
    platform: str
    action: str
    params_schema: dict[str, Any] | bool | None
    sample_safe: bool


class ActionParserRepository:
    def __init__(self, db: SQLAlchemyDB) -> None:
        self.db = db

    async def require_action_context(self, ba_id: int) -> ActionContext:
        async with self._session() as session:
            row = (
                await session.execute(
                    select(
                        Action.ba_id,
                        platformSource.bs_platform_code,
                        Action.ba_action,
                        Action.ba_params_schema,
                        Action.ba_sample_safe,
                    )
                    .join(platformSource, platformSource.bs_id == Action.bs_id)
                    .where(Action.ba_id == ba_id)
                )
            ).one_or_none()
        if row is None or not row.bs_platform_code:
            raise ParserConfigurationError(
                "action_not_found", "action not found", status_code=404
            )
        try:
            raw_schema = json.loads(row.ba_params_schema) if row.ba_params_schema else None
            params_schema = normalize_action_param_schema(raw_schema)
        except (json.JSONDecodeError, TypeError, InvalidActionParamSchema):
            raise ParserConfigurationError(
                "action_param_schema_invalid",
                "action parameter schema is invalid",
                status_code=422,
                details={"ba_id": ba_id},
            ) from None
        return ActionContext(
            ba_id=row.ba_id,
            platform=row.bs_platform_code,
            action=row.ba_action,
            params_schema=params_schema,
            sample_safe=row.ba_sample_safe,
        )

    async def create_sample(self, sample: ActionParserSample) -> ActionParserSample:
        async with self._session() as session:
            await self._lock_action(session, sample.ba_id)
            session.add(sample)
            await session.flush()
            await session.refresh(sample)
            return sample

    async def get_sample(self, ba_id: int, sample_id: int) -> ActionParserSample:
        async with self._session() as session:
            sample = (
                await session.execute(
                    select(ActionParserSample).where(
                        ActionParserSample.ba_id == ba_id,
                        ActionParserSample.sample_id == sample_id,
                    )
                )
            ).scalar_one_or_none()
        if sample is None:
            raise ParserConfigurationError(
                "sample_not_found", "sample not found", status_code=404
            )
        return sample

    async def list_samples(
        self, ba_id: int, offset: int = 0, limit: int = 100
    ) -> list[ActionParserSample]:
        async with self._session() as session:
            return list(
                (
                    await session.execute(
                        select(ActionParserSample)
                        .where(ActionParserSample.ba_id == ba_id)
                        .order_by(ActionParserSample.sample_id)
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

    async def require_samples(
        self, ba_id: int, sample_ids: list[int]
    ) -> list[ActionParserSample]:
        async with self._session() as session:
            samples = list(
                (
                    await session.execute(
                        select(ActionParserSample).where(
                            ActionParserSample.ba_id == ba_id,
                            ActionParserSample.sample_id.in_(sample_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
        by_id = {sample.sample_id: sample for sample in samples}
        if len(by_id) != len(sample_ids):
            raise ParserConfigurationError(
                "sample_not_found", "sample not found", status_code=404
            )
        return [by_id[sample_id] for sample_id in sample_ids]

    async def sample_reference_count(self, sample_id: int) -> int:
        source_count, validation_count = await self.count_sample_references(sample_id)
        return source_count + validation_count

    async def delete_sample(
        self,
        ba_id: int,
        sample_id: int,
        *,
        delete_objects: SampleObjectDelete,
    ) -> None:
        async with self._session() as session:
            sample = (
                await session.execute(
                    select(ActionParserSample)
                    .where(
                        ActionParserSample.ba_id == ba_id,
                        ActionParserSample.sample_id == sample_id,
                    )
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if sample is None:
                raise ParserConfigurationError(
                    "sample_not_found", "sample not found", status_code=404
                )
            source_count, validation_count = await self._sample_reference_counts(
                session, sample_id
            )
            if source_count or validation_count:
                raise ParserConfigurationError("sample_in_use", "sample is in use")
            await delete_objects(sample)
            await session.delete(sample)

    async def delete_sample_metadata(self, ba_id: int, sample_id: int) -> None:
        async with self._session() as session:
            result = await session.execute(
                delete(ActionParserSample).where(
                    ActionParserSample.ba_id == ba_id,
                    ActionParserSample.sample_id == sample_id,
                )
            )
            if result.rowcount != 1:
                raise ParserConfigurationError(
                    "sample_not_found", "sample not found", status_code=404
                )

    async def get_revision(
        self, ba_id: int, revision_id: int
    ) -> ActionParserRevision:
        async with self._session() as session:
            revision = (
                await session.execute(
                    select(ActionParserRevision).where(
                        ActionParserRevision.ba_id == ba_id,
                        ActionParserRevision.revision_id == revision_id,
                    )
                )
            ).scalar_one_or_none()
        if revision is None:
            raise self._revision_not_found()
        return revision

    async def get_draft(
        self, ba_id: int, revision_id: int
    ) -> ActionParserRevision:
        revision = await self.get_revision(ba_id, revision_id)
        if revision.status != "draft":
            raise self._invalid_transition()
        return revision

    async def list_revisions(
        self, ba_id: int, offset: int = 0, limit: int = 100
    ) -> list[ActionParserRevision]:
        async with self._session() as session:
            return list(
                (
                    await session.execute(
                        select(ActionParserRevision)
                        .where(ActionParserRevision.ba_id == ba_id)
                        .order_by(ActionParserRevision.revision_no.desc())
                        .offset(offset)
                        .limit(limit)
                    )
                )
                .scalars()
                .all()
            )

    async def delete_action_configuration(
        self,
        ba_id: int,
        *,
        delete_objects: SampleObjectDelete | None = None,
    ) -> None:
        async with self._session() as session:
            await self._lock_action(session, ba_id)
            if delete_objects is not None:
                samples = await session.stream_scalars(
                    select(ActionParserSample)
                    .where(ActionParserSample.ba_id == ba_id)
                    .order_by(ActionParserSample.sample_id)
                    .execution_options(yield_per=1_000)
                )
                async for sample in samples:
                    await delete_objects(sample)
            revision_ids = select(ActionParserRevision.revision_id).where(
                ActionParserRevision.ba_id == ba_id
            )
            await session.execute(
                delete(ActionParserRevisionSample).where(
                    ActionParserRevisionSample.revision_id.in_(revision_ids)
                )
            )
            await session.execute(
                update(ActionParserRevision)
                .where(ActionParserRevision.ba_id == ba_id)
                .values(restored_from_revision_id=None, source_sample_id=None)
            )
            await session.execute(
                delete(ActionParserRevision).where(ActionParserRevision.ba_id == ba_id)
            )
            await session.execute(
                delete(ActionParserSample).where(ActionParserSample.ba_id == ba_id)
            )
            await session.execute(
                update(BusTask).where(BusTask.ba_id == ba_id).values(ba_id=None)
            )
            await session.execute(delete(Action).where(Action.ba_id == ba_id))

    async def load_runtime(
        self,
        ba_id: int,
        *,
        include_parser: bool,
    ) -> ActionRuntimeDefinition:
        async with self._session() as session:
            result = await session.execute(
                select(
                    Action.ba_params_schema,
                    ActionParserRevision.revision_id,
                    ActionParserRevision.definition,
                )
                .outerjoin(
                    ActionParserRevision,
                    (ActionParserRevision.ba_id == Action.ba_id)
                    & (ActionParserRevision.status == "published"),
                )
                .where(Action.ba_id == ba_id)
            )
            row = result.one_or_none()
        if row is None:
            raise ParserConfigurationError(
                "action_not_found", "action not found", status_code=404
            )

        try:
            raw_schema = json.loads(row.ba_params_schema) if row.ba_params_schema else None
            params_schema = normalize_action_param_schema(raw_schema)
        except (json.JSONDecodeError, TypeError, InvalidActionParamSchema):
            raise ParserConfigurationError(
                "action_param_schema_invalid",
                "action parameter schema is invalid",
                status_code=422,
                details={"ba_id": ba_id},
            ) from None

        if not include_parser or row.revision_id is None:
            return ActionRuntimeDefinition(params_schema, None, None)
        try:
            definition = validate_parser_definition(row.definition)
        except (TypeError, ValueError):
            raise ParserConfigurationError(
                "parser_definition_invalid",
                "published parser definition is invalid",
                status_code=422,
                details={"ba_id": ba_id, "revision_id": row.revision_id},
            ) from None
        return ActionRuntimeDefinition(params_schema, row.revision_id, definition)

    async def create_draft(
        self,
        ba_id: int,
        *,
        definition: Any,
        source: str = "manual",
        source_sample_id: int | None = None,
        generation_metadata: dict[str, Any] | None = None,
    ) -> ActionParserRevision:
        parsed, definition_hash = self._validated_definition(definition)
        async with self._session() as session:
            await self._lock_action(session, ba_id)
            revisions = await self._lock_revisions(session, ba_id)
            if any(revision.status == "draft" for revision in revisions):
                raise ParserConfigurationError(
                    "draft_already_exists", "draft already exists"
                )
            revision = ActionParserRevision(
                ba_id=ba_id,
                revision_no=max((item.revision_no for item in revisions), default=0) + 1,
                status="draft",
                definition=parsed.model_dump(mode="json", exclude_unset=True),
                definition_sha256=definition_hash,
                source=source,
                source_sample_id=source_sample_id,
                generation_metadata=generation_metadata,
            )
            session.add(revision)
            await session.flush()
            await session.refresh(revision)
            return revision

    async def patch_draft(
        self,
        revision_id: int,
        *,
        expected_lock_version: int,
        definition: Any,
        source: str,
        source_sample_id: int | None,
        generation_metadata: dict[str, Any] | None,
    ) -> ActionParserRevision:
        parsed, definition_hash = self._validated_definition(definition)
        async with self._session() as session:
            result = await session.execute(
                update(ActionParserRevision)
                .where(
                    ActionParserRevision.revision_id == revision_id,
                    ActionParserRevision.status == "draft",
                    ActionParserRevision.lock_version == expected_lock_version,
                )
                .values(
                    definition=parsed.model_dump(mode="json", exclude_unset=True),
                    definition_sha256=definition_hash,
                    source=source,
                    source_sample_id=source_sample_id,
                    generation_metadata=generation_metadata,
                    validation_report=None,
                    lock_version=ActionParserRevision.lock_version + 1,
                )
            )
            if result.rowcount != 1:
                raise ParserConfigurationError(
                    "revision_conflict", "revision was modified or is not a draft"
                )
            await session.execute(
                delete(ActionParserRevisionSample).where(
                    ActionParserRevisionSample.revision_id == revision_id
                )
            )
            revision = await session.get(ActionParserRevision, revision_id)
            if revision is None:
                raise ParserConfigurationError(
                    "revision_conflict", "updated draft no longer exists"
                )
            return revision

    async def save_preview(
        self,
        revision_id: int,
        *,
        expected_lock_version: int,
        expected_definition_sha256: str,
        validation_report: dict[str, Any],
        sample_hashes: Mapping[int, str],
    ) -> ActionParserRevision:
        async with self._session() as session:
            revision = (
                await session.execute(
                    select(ActionParserRevision)
                    .where(ActionParserRevision.revision_id == revision_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if (
                revision is None
                or revision.status != "draft"
                or revision.lock_version != expected_lock_version
                or revision.definition_sha256 != expected_definition_sha256
                or self._current_definition_hash(revision) != expected_definition_sha256
                or not sample_hashes
                or set(validation_report.get("sample_ids", ())) != set(sample_hashes)
                or validation_report.get("definition_sha256")
                != expected_definition_sha256
            ):
                raise ParserConfigurationError(
                    "revision_conflict", "preview does not match the current draft"
                )

            samples = list(
                (
                    await session.execute(
                        select(ActionParserSample)
                        .where(
                            ActionParserSample.sample_id.in_(sample_hashes),
                            ActionParserSample.ba_id == revision.ba_id,
                        )
                        .with_for_update()
                    )
                )
                .scalars()
                .all()
            )
            if len(samples) != len(sample_hashes) or any(
                sample.response_sha256 != sample_hashes[sample.sample_id]
                for sample in samples
            ):
                raise ParserConfigurationError(
                    "revision_conflict", "preview samples have changed"
                )
            await session.execute(
                delete(ActionParserRevisionSample).where(
                    ActionParserRevisionSample.revision_id == revision_id
                )
            )
            session.add_all(
                ActionParserRevisionSample(
                    revision_id=revision_id,
                    sample_id=sample.sample_id,
                    sample_sha256=sample.response_sha256,
                )
                for sample in samples
            )
            revision.validation_report = validation_report
            await session.flush()
            return revision

    async def publish(self, revision_id: int) -> ActionParserRevision:
        async with self._session() as session:
            ba_id = await self._revision_ba_id(session, revision_id)
            await self._lock_action(session, ba_id)
            revisions = await self._lock_revisions(session, ba_id)
            draft = next(
                (item for item in revisions if item.revision_id == revision_id), None
            )
            if draft is None or draft.status != "draft":
                raise self._invalid_transition()

            definition, report = self._validated_publish_snapshot(draft)
            joins = list(
                (
                    await session.execute(
                        select(ActionParserRevisionSample).where(
                            ActionParserRevisionSample.revision_id == revision_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            report_sample_ids = set(report.get("sample_ids", ()))
            if (
                not report_sample_ids
                or not joins
                or report_sample_ids != {join.sample_id for join in joins}
            ):
                raise self._invalid_transition()
            samples = list(
                (
                    await session.execute(
                        select(ActionParserSample).where(
                            ActionParserSample.sample_id.in_(report_sample_ids),
                            ActionParserSample.ba_id == ba_id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            current_hashes = {sample.sample_id: sample.response_sha256 for sample in samples}
            if len(samples) != len(joins) or any(
                current_hashes.get(join.sample_id) != join.sample_sha256 for join in joins
            ):
                raise self._invalid_transition()

            task_configs = (
                await session.execute(select(BusTask.config).where(BusTask.ba_id == ba_id))
            ).scalars().all()
            try:
                for task_config in task_configs:
                    validate_sink_compatibility(
                        definition,
                        task_config if isinstance(task_config, TaskConfig) else TaskConfig.model_validate(task_config or {}),
                    )
            except (SinkCompatibilityError, ValueError):
                raise ParserConfigurationError(
                    "sink_incompatible",
                    "parser output is incompatible with an action task",
                    status_code=422,
                ) from None

            for revision in revisions:
                if revision.status == "published":
                    revision.status = "archived"
            draft.status = "published"
            draft.published_at = datetime.now()
            await session.flush()
            await session.refresh(draft)
            return draft

    async def archive(
        self,
        ba_id: int,
        revision_id: int,
    ) -> ActionParserRevision:
        async with self._session() as session:
            await self._lock_action(session, ba_id)
            revisions = await self._lock_revisions(session, ba_id)
            revision = next(
                (item for item in revisions if item.revision_id == revision_id), None
            )
            if revision is None:
                raise self._revision_not_found()
            if revision.status != "published":
                raise self._invalid_transition()
            revision.status = "archived"
            await session.flush()
            await session.refresh(revision)
            return revision

    async def delete_draft(self, revision_id: int) -> None:
        async with self._session() as session:
            result = await session.execute(
                delete(ActionParserRevision).where(
                    ActionParserRevision.revision_id == revision_id,
                    ActionParserRevision.status == "draft",
                )
            )
            if result.rowcount != 1:
                raise self._invalid_transition()

    async def restore_as_draft(
        self, revision_id: int, *, ba_id: int | None = None
    ) -> ActionParserRevision:
        async with self._session() as session:
            target_ba_id = await self._revision_ba_id(session, revision_id)
            if ba_id is not None and ba_id != target_ba_id:
                raise self._invalid_transition()
            ba_id = target_ba_id
            await self._lock_action(session, ba_id)
            revisions = await self._lock_revisions(session, ba_id)
            archived = next(
                (item for item in revisions if item.revision_id == revision_id), None
            )
            if archived is None:
                raise self._revision_not_found()
            if archived.status != "archived" or any(
                item.status == "draft" for item in revisions
            ):
                raise self._invalid_transition()
            restored = ActionParserRevision(
                ba_id=ba_id,
                revision_no=max(item.revision_no for item in revisions) + 1,
                status="draft",
                definition=archived.definition,
                definition_sha256=archived.definition_sha256,
                source="restore",
                restored_from_revision_id=revision_id,
            )
            session.add(restored)
            await session.flush()
            await session.refresh(restored)
            return restored

    async def list_validation_samples(self, revision_id: int) -> list[int]:
        async with self._session() as session:
            result = await session.execute(
                select(ActionParserRevisionSample.sample_id)
                .where(ActionParserRevisionSample.revision_id == revision_id)
                .order_by(ActionParserRevisionSample.sample_id)
            )
            return list(result.scalars().all())

    async def count_sample_references(self, sample_id: int) -> tuple[int, int]:
        async with self._session() as session:
            return await self._sample_reference_counts(session, sample_id)

    @staticmethod
    async def _sample_reference_counts(session, sample_id: int) -> tuple[int, int]:
        source_count = await session.scalar(
            select(func.count())
            .select_from(ActionParserRevision)
            .where(ActionParserRevision.source_sample_id == sample_id)
        )
        validation_count = await session.scalar(
            select(func.count())
            .select_from(ActionParserRevisionSample)
            .where(ActionParserRevisionSample.sample_id == sample_id)
        )
        return int(source_count or 0), int(validation_count or 0)

    @staticmethod
    async def _revision_ba_id(session, revision_id: int) -> int:
        ba_id = await session.scalar(
            select(ActionParserRevision.ba_id).where(
                ActionParserRevision.revision_id == revision_id
            )
        )
        if ba_id is None:
            raise ActionParserRepository._invalid_transition()
        return ba_id

    @asynccontextmanager
    async def _session(self):
        try:
            async with self.db.asession_scope() as session:
                yield session
        except SQLOperationError as error:
            if isinstance(error.original_error, ParserConfigurationError):
                raise error.original_error from None
            raise
        except AlreadyExistsError:
            raise ParserConfigurationError(
                "revision_conflict", "parser revision transaction conflicted"
            ) from None

    async def _lock_action(self, session, ba_id: int) -> Action:
        action = (
            await session.execute(
                select(Action).where(Action.ba_id == ba_id).with_for_update()
            )
        ).scalar_one_or_none()
        if action is None:
            raise ParserConfigurationError(
                "action_not_found", "action not found", status_code=404
            )
        return action

    @staticmethod
    async def _lock_revisions(session, ba_id: int) -> list[ActionParserRevision]:
        return list(
            (
                await session.execute(
                    select(ActionParserRevision)
                    .where(ActionParserRevision.ba_id == ba_id)
                    .order_by(ActionParserRevision.revision_no)
                    .with_for_update()
                )
            )
            .scalars()
            .all()
        )

    @staticmethod
    def _validated_definition(definition: Any) -> tuple[ParserDefinition, str]:
        try:
            parsed = validate_parser_definition(definition)
        except (TypeError, ValueError):
            raise ParserConfigurationError(
                "parser_definition_invalid",
                "parser definition is invalid",
                status_code=422,
            ) from None
        return parsed, definition_sha256(parsed)

    @staticmethod
    def _current_definition_hash(revision: ActionParserRevision) -> str | None:
        try:
            return definition_sha256(validate_parser_definition(revision.definition))
        except (TypeError, ValueError):
            return None

    def _validated_publish_snapshot(
        self, revision: ActionParserRevision
    ) -> tuple[ParserDefinition, dict[str, Any]]:
        report = revision.validation_report
        try:
            definition = validate_parser_definition(revision.definition)
        except (TypeError, ValueError):
            raise ParserConfigurationError(
                "parser_definition_invalid",
                "parser definition is invalid",
                status_code=422,
                details={
                    "ba_id": revision.ba_id,
                    "revision_id": revision.revision_id,
                },
            ) from None
        if (
            not isinstance(report, dict)
            or report.get("passed") is not True
            or definition_sha256(definition) != revision.definition_sha256
            or report.get("definition_sha256") != revision.definition_sha256
        ):
            raise self._invalid_transition()
        return definition, report

    @staticmethod
    def _invalid_transition() -> ParserConfigurationError:
        return ParserConfigurationError(
            "invalid_revision_transition", "invalid parser revision transition"
        )

    @staticmethod
    def _revision_not_found() -> ParserConfigurationError:
        return ParserConfigurationError(
            "revision_not_found", "revision not found", status_code=404
        )


__all__ = ["ActionContext", "ActionParserRepository", "ActionRuntimeDefinition"]
