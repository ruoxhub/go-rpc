from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any, Callable, Iterator, Protocol, cast

from common.logging import get_logger
from core.config import ParserConfigurationConfig
from core.param_schema import (
    ActionParamsValidationError,
    InvalidActionParamSchema,
    validate_action_params,
)
from core.rpc import RpcClient
from core.rpc_errors import (
    BlockedRpcError,
    InvalidRpcJsonError,
    PermanentRpcError,
    RateLimitedRpcError,
    RetryableRpcError,
    RpcError,
    RpcResponseTooLargeError,
)
from models.action_parser import ActionParserRevision, ActionParserSample
from parser import definition_sha256, general_parser, validate_parser_definition
from parser.configured import ParseReport
from parser.definition import ParserOutput
from parser.exceptions import ConfiguredParserError, ParserCallConfigurationError
from parser.sanitizer import (
    JsonResourceLimitError,
    canonical_json_bytes,
    json_hmac_sha256,
    sanitize_json,
)
from services.parser_configuration.errors import ParserConfigurationError
from services.parser_configuration.rate_limit import (
    ParserRateLimitExceeded,
    RedisParserRateLimiter,
)
from services.parser_configuration.repository import ActionParserRepository
from services.parser_configuration.storage import ParserSampleObjectStore

if TYPE_CHECKING:
    from worker.rate_limit import PlatformLimiter


logger: Any = get_logger(__file__)
_SANITIZER_VERSION = "v1"
_ALLOWED_LOG_FIELDS = frozenset(
    {
        "ba_id",
        "platform",
        "action",
        "sample_id",
        "revision_id",
        "revision_no",
        "rpc_duration_ms",
        "ai_duration_ms",
        "response_bytes",
        "source_records",
        "valid_records",
        "invalid_records",
        "error_code",
    }
)


def _safe_log_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key in _ALLOWED_LOG_FIELDS}


def _log_event(level: str, message: str, fields: dict[str, Any]) -> None:
    safe_fields = _safe_log_fields(fields)
    target = logger.bind(**safe_fields) if hasattr(logger, "bind") else logger
    kwargs = {} if hasattr(logger, "bind") else {"extra": safe_fields}
    try:
        getattr(target, level)(message, **kwargs)
    except TypeError:
        getattr(target, level)(message)


class _PreviewParseResult(Protocol):
    @property
    def report(self) -> ParseReport: ...

    def __iter__(self) -> Iterator[dict[str, Any]]: ...


@dataclass(frozen=True, slots=True)
class PreviewReport:
    definition_sha256: str
    samples: tuple[dict[str, Any], ...]
    sample_ids: tuple[int, ...]
    source_records: int
    valid_records: int
    invalid_records: int
    passed: bool
    errors: tuple[dict[str, Any], ...]
    errors_truncated: bool
    preview: tuple[Any, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["samples"] = list(self.samples)
        value["sample_ids"] = list(self.sample_ids)
        value["errors"] = list(self.errors)
        value["preview"] = list(self.preview)
        return value


class ActionParserService:
    def __init__(
        self,
        *,
        repository: ActionParserRepository,
        rpc: RpcClient,
        limiter_for: Callable[[str], PlatformLimiter],
        rate_limiter: RedisParserRateLimiter,
        object_store: ParserSampleObjectStore,
        config: ParserConfigurationConfig,
    ) -> None:
        self._repository = repository
        self._rpc = rpc
        self._limiter_for = limiter_for
        self._rate_limiter = rate_limiter
        self._object_store = object_store
        self._config = config
        self._sample_hmac_key = config.sample_hmac_key.encode("utf-8")

    async def create_sample(
        self,
        *,
        ba_id: int,
        params: dict[str, Any],
        confirm_side_effect: bool,
    ) -> ActionParserSample:
        action = await self._repository.require_action_context(ba_id)
        if not action.sample_safe and not confirm_side_effect:
            raise ParserConfigurationError(
                "sample_confirmation_required",
                "sampling this action requires confirmation",
                status_code=409,
            )
        if not self._sample_hmac_key:
            raise ParserConfigurationError(
                "sample_hmac_unavailable",
                "sample HMAC is not configured",
                status_code=503,
            )
        try:
            validate_action_params(action.params_schema, params)
        except ActionParamsValidationError as error:
            raise ParserConfigurationError(
                "action_params_invalid",
                "action parameters are invalid",
                status_code=422,
                details={"path": error.path, "validator": error.validator},
            ) from None
        except InvalidActionParamSchema:
            raise ParserConfigurationError(
                "action_param_schema_invalid",
                "action parameter schema is invalid",
                status_code=422,
            ) from None

        try:
            await self._rate_limiter.require(
                operation="sample",
                ba_id=ba_id,
                global_limit=self._config.sample_global_limit_per_minute,
                action_limit=self._config.sample_action_limit_per_minute,
            )
        except ParserRateLimitExceeded as error:
            raise ParserConfigurationError(
                "sample_rate_limited",
                "sample rate limit exceeded",
                status_code=429,
                details={"retry_after_seconds": error.retry_after_seconds},
            ) from None

        started = time.monotonic()
        response = await self._invoke_sample(action.platform, action.action, params)
        rpc_duration_ms = max(0, int((time.monotonic() - started) * 1000))
        if not isinstance(response, (dict, list)):
            raise ParserConfigurationError(
                "sample_rpc_invalid_json",
                "RPC response must be a JSON object or array",
                status_code=502,
            )
        try:
            redacted_params = sanitize_json(
                params,
                max_depth=self._config.json_max_depth,
                max_nodes=self._config.json_max_nodes,
            ).value
            redacted_response = sanitize_json(
                response,
                max_depth=self._config.json_max_depth,
                max_nodes=self._config.json_max_nodes,
            ).value
            raw_bytes = canonical_json_bytes(response)
            redacted_bytes = canonical_json_bytes(redacted_response)
            params_hmac = json_hmac_sha256(params, self._sample_hmac_key)
        except (JsonResourceLimitError, TypeError, ValueError, RecursionError):
            raise ParserConfigurationError(
                "sample_rpc_invalid_json",
                "RPC response exceeds JSON limits",
                status_code=502,
            ) from None

        stored = await self._object_store.write_pair(
            ba_id=ba_id, raw=raw_bytes, redacted=redacted_bytes
        )
        metadata = ActionParserSample(
            ba_id=ba_id,
            request_params_redacted=redacted_params,
            request_params_hmac_sha256=params_hmac,
            request_hmac_key_version=self._config.sample_hmac_key_version,
            raw_object_key=stored.raw_object_key,
            redacted_object_key=stored.redacted_object_key,
            response_sha256=stored.response_sha256,
            response_bytes=stored.response_bytes,
            sanitizer_version=_SANITIZER_VERSION,
            rpc_duration_ms=rpc_duration_ms,
        )
        try:
            return await self._repository.create_sample(metadata)
        except Exception:
            try:
                await self._object_store.delete_pair(
                    stored.raw_object_key, stored.redacted_object_key
                )
            except Exception:
                _log_event(
                    "error",
                    "parser_sample_cleanup_failed",
                    {"ba_id": ba_id, "error_code": "sample_cleanup_failed"},
                )
            raise

    async def _invoke_sample(
        self, platform: str, action: str, params: dict[str, Any]
    ) -> Any:
        limiter = self._limiter_for(platform)
        try:
            async with limiter:
                result = await self._rpc.invoke(
                    platform,
                    action,
                    params,
                    max_response_bytes=self._config.sample_max_response_bytes,
                )
            limiter.record_success()
            return result
        except RateLimitedRpcError as error:
            limiter.record_rate_limit(error.retry_after_seconds)
            raise ParserConfigurationError(
                "sample_rate_limited",
                "RPC rate limit exceeded",
                status_code=429,
                details={"retry_after_seconds": error.retry_after_seconds},
            ) from None
        except BlockedRpcError:
            limiter.record_block()
            raise ParserConfigurationError(
                "sample_rpc_blocked", "RPC request was blocked", status_code=502
            ) from None
        except RetryableRpcError:
            limiter.record_transient_failure()
            raise ParserConfigurationError(
                "sample_rpc_unavailable", "RPC request failed", status_code=502
            ) from None
        except RpcResponseTooLargeError:
            raise ParserConfigurationError(
                "sample_rpc_too_large", "RPC response is too large", status_code=502
            ) from None
        except InvalidRpcJsonError:
            raise ParserConfigurationError(
                "sample_rpc_invalid_json", "RPC response is invalid", status_code=502
            ) from None
        except PermanentRpcError:
            raise ParserConfigurationError(
                "sample_rpc_failed", "RPC request failed", status_code=502
            ) from None
        except RpcError:
            raise ParserConfigurationError(
                "sample_rpc_failed", "RPC request failed", status_code=502
            ) from None

    async def get_sample(self, *, ba_id: int, sample_id: int) -> Any:
        _, value = await self.get_sample_detail(ba_id=ba_id, sample_id=sample_id)
        return value

    async def get_sample_detail(
        self, *, ba_id: int, sample_id: int
    ) -> tuple[ActionParserSample, dict[str, Any] | list[Any]]:
        await self._repository.require_action_context(ba_id)
        sample = await self._repository.get_sample(ba_id, sample_id)
        try:
            payload = await self._object_store.read_redacted(sample.redacted_object_key)
        except ParserConfigurationError:
            raise
        except Exception:
            raise ParserConfigurationError(
                "sample_storage_failed", "Failed to read parser sample"
            ) from None
        try:
            value = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
            raise ParserConfigurationError(
                "sample_object_corrupt", "sample object is corrupt", status_code=502
            ) from None
        if not isinstance(value, (dict, list)):
            raise ParserConfigurationError(
                "sample_object_corrupt", "sample object is corrupt", status_code=502
            )
        return sample, value

    async def list_samples(
        self, *, ba_id: int, offset: int = 0, limit: int = 100
    ) -> list[ActionParserSample]:
        await self._repository.require_action_context(ba_id)
        return await self._repository.list_samples(ba_id, offset, limit)

    async def delete_sample(self, *, ba_id: int, sample_id: int) -> None:
        await self._repository.require_action_context(ba_id)

        async def delete_objects(sample: ActionParserSample) -> None:
            try:
                await self._object_store.delete_pair(
                    sample.raw_object_key, sample.redacted_object_key
                )
            except Exception:
                _log_event(
                    "error",
                    "parser_sample_cleanup_failed",
                    {
                        "ba_id": ba_id,
                        "sample_id": sample_id,
                        "error_code": "sample_cleanup_failed",
                    },
                )
                raise

        await self._repository.delete_sample(
            ba_id, sample_id, delete_objects=delete_objects
        )

    async def create_draft(
        self, *, ba_id: int, definition: Any
    ) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        return await self._repository.create_draft(
            ba_id,
            definition=definition,
            source="manual",
            source_sample_id=None,
            generation_metadata=None,
        )

    async def get_draft(self, *, ba_id: int, revision_id: int) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        return await self._repository.get_draft(ba_id, revision_id)

    async def get_revision(
        self, *, ba_id: int, revision_id: int
    ) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        return await self._repository.get_revision(ba_id, revision_id)

    async def list_revisions(
        self, *, ba_id: int, offset: int = 0, limit: int = 100
    ) -> list[ActionParserRevision]:
        await self._repository.require_action_context(ba_id)
        return await self._repository.list_revisions(ba_id, offset, limit)

    async def patch_draft(
        self,
        *,
        ba_id: int,
        revision_id: int,
        expected_lock_version: int,
        definition: Any,
    ) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        await self._repository.get_draft(ba_id, revision_id)
        return await self._repository.patch_draft(
            revision_id,
            expected_lock_version=expected_lock_version,
            definition=definition,
            source="manual",
            source_sample_id=None,
            generation_metadata=None,
        )

    async def delete_draft(self, *, ba_id: int, revision_id: int) -> None:
        await self._repository.require_action_context(ba_id)
        await self._repository.get_draft(ba_id, revision_id)
        await self._repository.delete_draft(revision_id)

    async def publish(self, *, ba_id: int, revision_id: int) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        await self._repository.get_draft(ba_id, revision_id)
        return await self._repository.publish(revision_id)

    async def archive(self, *, ba_id: int, revision_id: int) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        return await self._repository.archive(ba_id, revision_id)

    async def restore(self, *, ba_id: int, revision_id: int) -> ActionParserRevision:
        await self._repository.require_action_context(ba_id)
        return await self._repository.restore_as_draft(revision_id, ba_id=ba_id)

    async def preview(
        self,
        *,
        ba_id: int,
        revision_id: int,
        expected_lock_version: int,
        sample_ids: list[int],
    ) -> PreviewReport:
        action = await self._repository.require_action_context(ba_id)
        ordered_ids = list(dict.fromkeys(sample_ids))
        if not ordered_ids:
            raise ParserConfigurationError(
                "preview_samples_required",
                "at least one sample is required",
                status_code=422,
            )
        draft = await self._repository.get_draft(ba_id, revision_id)
        if draft.lock_version != expected_lock_version:
            raise ParserConfigurationError(
                "revision_conflict", "revision was modified or is not a draft"
            )
        samples = await self._repository.require_samples(ba_id, ordered_ids)
        try:
            definition = validate_parser_definition(draft.definition)
        except (TypeError, ValueError):
            raise ParserConfigurationError(
                "parser_definition_invalid",
                "parser definition is invalid",
                status_code=422,
            ) from None

        source_records = valid_records = invalid_records = 0
        errors: list[dict[str, Any]] = []
        preview: list[Any] = []
        fatal = False
        sample_hashes: dict[int, str] = {}
        sample_snapshots: list[dict[str, Any]] = []
        for sample in samples:
            sample_hashes[sample.sample_id] = sample.response_sha256
            sample_snapshots.append(
                {"sample_id": sample.sample_id, "sample_sha256": sample.response_sha256}
            )
            try:
                raw_bytes = await self._object_store.read_raw(sample.raw_object_key)
            except ParserConfigurationError as error:
                if error.code == "sample_object_missing":
                    fatal = True
                    errors.append({"sample_id": sample.sample_id, "code": error.code})
                    continue
                raise
            except Exception:
                raise ParserConfigurationError(
                    "sample_storage_failed", "Failed to read parser sample"
                ) from None
            if hashlib.sha256(raw_bytes).hexdigest() != sample.response_sha256:
                fatal = True
                errors.append(
                    {"sample_id": sample.sample_id, "code": "sample_object_corrupt"}
                )
                continue
            try:
                raw_json = json.loads(raw_bytes)
            except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
                fatal = True
                errors.append(
                    {"sample_id": sample.sample_id, "code": "sample_object_corrupt"}
                )
                continue
            try:
                parsed = cast(
                    _PreviewParseResult,
                    general_parser.parse(
                        action.platform,
                        raw_json,
                        action.action,
                        definition=definition,
                        as_dto=False,
                    ),
                )
                records = list(parsed)
                parse_report = parsed.report
            except (ConfiguredParserError, ParserCallConfigurationError) as error:
                fatal = True
                report = getattr(error, "report", None)
                if report is not None:
                    source_records += report.source_records
                    valid_records += report.valid_records
                    invalid_records += report.invalid_records
                    errors.extend(self._report_errors(sample.sample_id, report.errors))
                errors.append({"sample_id": sample.sample_id, "code": error.code})
                continue
            source_records += parse_report.source_records
            valid_records += parse_report.valid_records
            invalid_records += parse_report.invalid_records
            errors.extend(self._report_errors(sample.sample_id, parse_report.errors))
            for record in records:
                if len(preview) >= self._config.preview_max_records:
                    break
                serializable_record = {
                    key: val.isoformat() if isinstance(val, datetime) else val
                    for key, val in record.items()
                } if isinstance(record, dict) else record
                try:
                    preview.append(
                        sanitize_json(
                            serializable_record,
                            max_depth=self._config.json_max_depth,
                            max_nodes=self._config.json_max_nodes,
                        ).value
                    )
                except (JsonResourceLimitError, TypeError, ValueError, RecursionError):
                    fatal = True
                    errors.append(
                        {
                            "sample_id": sample.sample_id,
                            "code": "preview_record_invalid",
                        }
                    )

        errors_truncated = len(errors) > self._config.preview_max_errors
        report = PreviewReport(
            definition_sha256=definition_sha256(definition),
            samples=tuple(sample_snapshots),
            sample_ids=tuple(ordered_ids),
            source_records=source_records,
            valid_records=valid_records,
            invalid_records=invalid_records,
            passed=valid_records > 0 and not fatal,
            errors=tuple(errors[: self._config.preview_max_errors]),
            errors_truncated=errors_truncated,
            preview=tuple(preview),
        )
        await self._repository.save_preview(
            revision_id,
            expected_lock_version=expected_lock_version,
            expected_definition_sha256=draft.definition_sha256,
            validation_report=report.as_dict(),
            sample_hashes=sample_hashes,
        )
        if not report.passed:
            raise ParserConfigurationError(
                "parser_preview_failed", "parser preview failed", status_code=422
            )
        return report

    @staticmethod
    def _report_errors(sample_id: int, errors: Any) -> list[dict[str, Any]]:
        return [
            {
                "sample_id": sample_id,
                "record_index": error.record_index,
                "target": error.target,
                "code": error.code,
            }
            for error in errors
        ]

    async def delete_action(self, ba_id: int) -> None:
        async def delete_objects(sample: ActionParserSample) -> None:
            await self._object_store.delete_pair(
                sample.raw_object_key, sample.redacted_object_key
            )

        await self._repository.delete_action_configuration(
            ba_id, delete_objects=delete_objects
        )

    async def assist(
        self,
        *,
        ba_id: int,
        revision_id: int,
        expected_lock_version: int,
        sample_id: int,
        model_id: int,
        output: ParserOutput,
    ) -> None:
        await self._repository.require_action_context(ba_id)
        await self._repository.get_draft(ba_id, revision_id)
        await self._repository.get_sample(ba_id, sample_id)
        raise ParserConfigurationError(
            "ai_unavailable", "AI parser assistance is unavailable", status_code=503
        )


__all__ = ["ActionParserService", "PreviewReport"]
