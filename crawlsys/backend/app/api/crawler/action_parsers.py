"""Action parser sample and revision management routes."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from types import NoneType, UnionType
from typing import Annotated, Any, Union, get_args, get_origin

from fastapi import APIRouter, Depends, Query, Response, status

from api.crawler.parser_schemas import (
    ParserAssistRead,
    ParserAssistRequest,
    ParserCapabilitiesRead,
    ParserModelFieldRead,
    ParserPreviewRead,
    ParserPreviewRequest,
    ParserRevisionCreateRequest,
    ParserRevisionList,
    ParserRevisionPatchRequest,
    ParserRevisionRead,
    ParserSampleCreateRequest,
    ParserSampleDetailRead,
    ParserSampleList,
    ParserSampleRead,
    ParserSuggestionRequest,
)
from api.deps import get_action_parser_service
import models  # noqa: F401 - ensure all GeneralBase subclasses are registered
from models.base import DATATYPE_TO_MODEL
from parser.definition import FieldType
from parser.dto import ParsedItem
from services.parser_configuration.assistant import AssistantActionParserService


router = APIRouter(
    prefix="/api/crawler/actions/{ba_id}", tags=["action-parsers"]
)
capabilities_router = APIRouter(
    prefix="/api/crawler/parser-capabilities", tags=["action-parsers"]
)

Offset = Annotated[int, Query(ge=0)]
Limit = Annotated[int, Query(ge=1, le=100)]

FIELD_TYPES: tuple[FieldType, ...] = (
    "string",
    "integer",
    "number",
    "boolean",
    "datetime",
    "object",
    "array",
)


def model_field_target(name: str) -> str:
    return f"/{name.replace('~', '~0').replace('/', '~1')}"


def parser_value_types(annotation: object) -> list[FieldType]:
    if annotation is Any:
        return list(FIELD_TYPES)
    origin = get_origin(annotation)
    if origin is Annotated:
        return parser_value_types(get_args(annotation)[0])
    if origin in (Union, UnionType):
        inferred = {
            field_type
            for member in get_args(annotation)
            if member is not NoneType
            for field_type in parser_value_types(member)
        }
        return [field_type for field_type in FIELD_TYPES if field_type in inferred] or list(
            FIELD_TYPES
        )
    scalar = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        datetime: "datetime",
    }.get(annotation)
    if scalar is not None:
        return [scalar]
    if annotation is dict or origin in (dict, Mapping):
        return ["object"]
    if annotation in (list, tuple, set, frozenset) or origin in (
        list,
        tuple,
        set,
        frozenset,
        Sequence,
    ):
        return ["array"]
    return list(FIELD_TYPES)


def parser_model_fields(datatype: str) -> list[ParserModelFieldRead]:
    dto = ParsedItem._DTO_BY_KIND[datatype]
    orm = DATATYPE_TO_MODEL[datatype]
    shared_names = sorted(set(dto.model_fields) & set(orm.__mapper__.attrs.keys()))
    return [
        ParserModelFieldRead(
            target=model_field_target(name),
            required=dto.model_fields[name].is_required(),
            value_types=parser_value_types(dto.model_fields[name].annotation),
        )
        for name in shared_names
        if name != "datatype"
    ]


@capabilities_router.get("", response_model=ParserCapabilitiesRead)
async def get_parser_capabilities() -> ParserCapabilitiesRead:
    datatypes = sorted(ParsedItem._DTO_BY_KIND.keys() & DATATYPE_TO_MODEL.keys())
    return ParserCapabilitiesRead(
        model_datatypes=datatypes,
        field_types=list(FIELD_TYPES),
        model_fields={datatype: parser_model_fields(datatype) for datatype in datatypes},
    )


@router.post(
    "/parser-samples",
    response_model=ParserSampleRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_parser_sample(
    ba_id: int,
    payload: ParserSampleCreateRequest,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.create_sample(
        ba_id=ba_id,
        params=payload.params,
        confirm_side_effect=payload.confirm_side_effect,
    )


@router.get("/parser-samples", response_model=ParserSampleList)
async def list_parser_samples(
    ba_id: int,
    offset: Offset = 0,
    limit: Limit = 100,
    service: AssistantActionParserService = Depends(get_action_parser_service),
) -> ParserSampleList:
    samples = await service.list_samples(ba_id=ba_id, offset=offset, limit=limit)
    return ParserSampleList(
        items=[ParserSampleRead.model_validate(sample) for sample in samples]
    )


@router.get("/parser-samples/{sample_id}", response_model=ParserSampleDetailRead)
async def get_parser_sample(
    ba_id: int,
    sample_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
) -> ParserSampleDetailRead:
    sample, preview = await service.get_sample_detail(ba_id=ba_id, sample_id=sample_id)
    metadata = ParserSampleRead.model_validate(sample)
    return ParserSampleDetailRead(
        **metadata.model_dump(),
        redacted_preview=preview,
    )


@router.delete(
    "/parser-samples/{sample_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_parser_sample(
    ba_id: int,
    sample_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
) -> Response:
    await service.delete_sample(ba_id=ba_id, sample_id=sample_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/parser-revisions",
    response_model=ParserRevisionRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def create_parser_revision(
    ba_id: int,
    payload: ParserRevisionCreateRequest,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.create_draft(
        ba_id=ba_id,
        definition=payload.definition,
        assist_receipt=payload.assist_receipt,
    )


@router.get(
    "/parser-revisions",
    response_model=ParserRevisionList,
    response_model_exclude_unset=True,
)
async def list_parser_revisions(
    ba_id: int,
    offset: Offset = 0,
    limit: Limit = 100,
    service: AssistantActionParserService = Depends(get_action_parser_service),
) -> ParserRevisionList:
    revisions = await service.list_revisions(ba_id=ba_id, offset=offset, limit=limit)
    return ParserRevisionList(
        items=[ParserRevisionRead.model_validate(revision) for revision in revisions]
    )


@router.get(
    "/parser-revisions/{revision_id}",
    response_model=ParserRevisionRead,
    response_model_exclude_unset=True,
)
async def get_parser_revision(
    ba_id: int,
    revision_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.get_revision(ba_id=ba_id, revision_id=revision_id)


@router.patch(
    "/parser-revisions/{revision_id}",
    response_model=ParserRevisionRead,
    response_model_exclude_unset=True,
)
async def patch_parser_revision(
    ba_id: int,
    revision_id: int,
    payload: ParserRevisionPatchRequest,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.patch_draft(
        ba_id=ba_id,
        revision_id=revision_id,
        expected_lock_version=payload.lock_version,
        definition=payload.definition,
        assist_receipt=payload.assist_receipt,
    )


@router.delete(
    "/parser-revisions/{revision_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_parser_revision(
    ba_id: int,
    revision_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
) -> Response:
    await service.delete_draft(ba_id=ba_id, revision_id=revision_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/parser-revisions/{revision_id}/preview",
    response_model=ParserPreviewRead,
    status_code=status.HTTP_201_CREATED,
)
async def preview_parser_revision(
    ba_id: int,
    revision_id: int,
    payload: ParserPreviewRequest,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.preview(
        ba_id=ba_id,
        revision_id=revision_id,
        expected_lock_version=payload.lock_version,
        sample_ids=payload.sample_ids,
    )


@router.post(
    "/parser-suggestions",
    response_model=ParserAssistRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def suggest_parser_definition(
    ba_id: int,
    payload: ParserSuggestionRequest,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.suggest_initial(
        ba_id=ba_id,
        sample_id=payload.sample_id,
        model_id=payload.model_id,
        output=payload.output,
    )


@router.post(
    "/parser-revisions/{revision_id}/assist",
    response_model=ParserAssistRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def assist_parser_revision(
    ba_id: int,
    revision_id: int,
    payload: ParserAssistRequest,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.assist(
        ba_id=ba_id,
        revision_id=revision_id,
        expected_lock_version=payload.lock_version,
        sample_id=payload.sample_id,
        model_id=payload.model_id,
        output=payload.output,
    )


@router.post(
    "/parser-revisions/{revision_id}/publish",
    response_model=ParserRevisionRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def publish_parser_revision(
    ba_id: int,
    revision_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.publish(ba_id=ba_id, revision_id=revision_id)


@router.post(
    "/parser-revisions/{revision_id}/archive",
    response_model=ParserRevisionRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def archive_parser_revision(
    ba_id: int,
    revision_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.archive(ba_id=ba_id, revision_id=revision_id)


@router.post(
    "/parser-revisions/{revision_id}/restore",
    response_model=ParserRevisionRead,
    response_model_exclude_unset=True,
    status_code=status.HTTP_201_CREATED,
)
async def restore_parser_revision(
    ba_id: int,
    revision_id: int,
    service: AssistantActionParserService = Depends(get_action_parser_service),
):
    return await service.restore(ba_id=ba_id, revision_id=revision_id)


__all__ = ["capabilities_router", "router"]
