"""Cross-resource crawler API schema and contract tests."""
from datetime import datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from api.crawler.schemas import (
    ActionImportRequest,
    ActionImportResponse,
    ActionList,
    ActionRead,
    ActionUpdate,
    ActionSchemaResponse,
    KeywordCreate,
    KeywordList,
    KeywordRead,
    KeywordUpdate,
    PlatformCreate,
    PlatformList,
    PlatformRead,
    PlatformUpdate,
    TableColumnsResponse,
    TaskBatchStatusRequest,
    TaskBatchStatusResponse,
    TaskCreate,
    TaskList,
    TaskRead,
    TaskUpdate,
)
from models.platform import PlatformStatus
from models.task import TaskStatus


def test_crawler_request_schemas_apply_form_validation_rules():
    platform = PlatformCreate(
        bs_name="  TikTok  ",
        bs_platform_code="  tiktok  ",
        bs_concurrency=1,
        bs_rps=0.1,
        bs_burst=1,
        bs_cooldown=0,
    )
    assert platform.bs_name == "TikTok"
    assert platform.bs_platform_code == "tiktok"

    keyword = KeywordCreate(platform="  tiktok ", keyword="  AI ")
    assert keyword.model_dump() == {"platform": "tiktok", "keyword": "AI"}

    with pytest.raises(ValidationError):
        PlatformCreate(
            bs_name=" ",
            bs_platform_code="tiktok",
            bs_concurrency=0,
            bs_rps=0.1,
            bs_burst=1,
            bs_cooldown=0,
        )
    with pytest.raises(ValidationError):
        ActionImportRequest(platform_id=1, actions=[{"description": "missing name"}])
    with pytest.raises(ValidationError):
        TaskCreate(ba_id=1, loop_enabled=True, loop_interval_seconds=0)


def test_all_read_schemas_explicitly_enable_orm_attribute_conversion():
    now = datetime.now()
    platform = PlatformRead.model_validate(
        SimpleNamespace(
            bs_id=7,
            bs_name="TikTok",
            bs_platform_code="tiktok",
            bs_status=PlatformStatus.ENABLED,
        )
    )
    action = ActionRead.model_validate(
        SimpleNamespace(
            ba_id=8,
            bs_id=7,
            ba_action="SearchVideo",
            ba_enabled=True,
        )
    )
    keyword = KeywordRead.model_validate(
        SimpleNamespace(
            id=9,
            platform="tiktok",
            keyword="AI",
            is_crawled=False,
            created_at=now,
        )
    )
    task = TaskRead.model_validate(
        SimpleNamespace(
            task_id=10,
            platform="tiktok",
            action="SearchVideo",
            status=TaskStatus.PENDING,
            attempts=0,
            loop_enabled=False,
            schedule_type="manual",
            run_count=0,
            retry_max_attempts=0,
            retry_delay_seconds=60,
            retry_backoff_multiplier=2.0,
            retry_max_delay_seconds=3600,
            retry_count=0,
            pause_requested=False,
            created_at=now,
            updated_at=now,
        )
    )

    assert all(
        schema.model_config["from_attributes"] is True
        for schema in (PlatformRead, ActionRead, KeywordRead, TaskRead)
    )
    assert (platform.bs_id, action.ba_id, keyword.id, task.task_id) == (7, 8, 9, 10)


def test_list_schemas_use_items_envelope():
    now = datetime.now()
    assert PlatformList(items=[]).model_dump() == {"items": []}
    assert ActionList(items=[]).model_dump() == {"items": []}
    assert KeywordList(
        items=[
            {
                "id": 1,
                "platform": "tiktok",
                "keyword": "AI",
                "is_crawled": False,
                "created_at": now,
            }
        ]
    ).items[0].keyword == "AI"
    assert TaskList(items=[]).model_dump() == {"items": []}


def test_special_operation_and_metadata_schemas():
    imported = ActionImportRequest(
        platform_id=1,
        actions=[{"name": "SearchVideo", "params": [{"name": "keyword"}]}],
    )
    assert imported.actions[0].name == "SearchVideo"
    assert ActionImportResponse(created_count=2, updated_count=1).created_count == 2

    assert TaskBatchStatusRequest().platform is None
    assert TaskBatchStatusResponse(updated_count=3).updated_count == 3
    assert TableColumnsResponse(columns=["id"]).columns == ["id"]
    assert (
        ActionSchemaResponse(schema=[{"name": "keyword"}])
        .action_schema[0]["name"]
        == "keyword"
    )


def test_update_schemas_preserve_resource_specific_validation():
    platform = PlatformUpdate(
        bs_name=" TikTok ",
        bs_platform_code=" tiktok ",
        bs_concurrency=1,
        bs_rps=0.1,
        bs_burst=1,
        bs_cooldown=0,
    )
    action = ActionUpdate(ba_desc=" 新描述 ")
    keyword = KeywordUpdate(platform=" tiktok ", keyword=" AI ")
    task = TaskUpdate(ba_id=1, loop_enabled=True, loop_interval_seconds=60)

    assert platform.bs_name == "TikTok"
    assert action.model_dump(exclude_unset=True) == {"ba_desc": "新描述"}
    assert "bs_id" not in ActionUpdate.model_fields
    assert keyword.model_dump() == {"platform": "tiktok", "keyword": "AI"}
    assert task.loop_interval_seconds == 60

    with pytest.raises(ValidationError):
        ActionUpdate(ba_action=" ")


def test_string_lengths_are_checked_after_whitespace_is_stripped():
    platform = PlatformCreate(
        bs_name=f"  {'p' * 100}  ",
        bs_platform_code=f"  {'c' * 100}  ",
    )
    action = ActionUpdate(ba_action=f"  {'a' * 100}  ")
    keyword = KeywordCreate(
        platform=f"  {'k' * 100}  ",
        keyword=f"  {'w' * 1000}  ",
    )

    assert len(platform.bs_name) == 100
    assert len(action.ba_action or "") == 100
    assert len(keyword.keyword) == 1000


def test_disabled_loop_ignores_and_clears_submitted_interval():
    task = TaskCreate(
        ba_id=1,
        loop_enabled=False,
        loop_interval_seconds=0,
    )
    assert task.loop_interval_seconds is None


def test_action_schema_metadata_uses_alias_without_shadowing_base_model():
    response = ActionSchemaResponse(action_schema=[{"name": "keyword"}])
    assert "schema" not in ActionSchemaResponse.model_fields
    assert response.model_dump(by_alias=True) == {
        "schema": [{"name": "keyword"}],
    }


def test_action_schema_metadata_accepts_json_schema_object_and_boolean():
    object_schema = {"type": "object", "properties": {"keyword": {"type": "string"}}}

    assert ActionSchemaResponse(schema=object_schema).model_dump(by_alias=True) == {
        "schema": object_schema,
    }
    assert ActionSchemaResponse(schema=False).model_dump(by_alias=True) == {
        "schema": False,
    }
