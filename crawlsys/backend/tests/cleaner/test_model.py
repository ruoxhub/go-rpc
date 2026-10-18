from sqlalchemy import BigInteger

from models.base import DATATYPE_TO_MODEL, UNIQUE_FIELD_MAPPING
from models.material import MaterialClean
from models.worker_state import VideoCleanCursor


def test_material_clean_table_contract():
    table = MaterialClean.__table__

    assert table.name == "t_material_clean"
    assert table.schema == "public"
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.datatype.nullable is False
    assert table.c.datatype.server_default.arg == "clean"
    assert table.c.platform.nullable is False
    assert table.c.content_id.nullable is False
    assert table.c.grade_rank.nullable is False
    assert table.c.expire_time.nullable is False
    assert {index.name for index in table.indexes} >= {
        "idx_mc_expire",
        "idx_mc_grade_rank",
        "uq_material_clean_platform_content",
    }


def test_material_clean_is_registered_as_pipeline_datatype():
    assert DATATYPE_TO_MODEL["clean"] is MaterialClean
    assert UNIQUE_FIELD_MAPPING["clean"] == "content_id"


def test_video_clean_cursor_has_consumer_platform_unique_key():
    columns = VideoCleanCursor.__table__.c
    assert set(columns.keys()) >= {
        "consumer_key",
        "platform",
        "policy_hash",
        "watermark_ts",
        "watermark_id",
        "updated_time",
    }
    assert any(
        index.unique
        and tuple(index.columns.keys()) == ("consumer_key", "platform")
        for index in VideoCleanCursor.__table__.indexes
    )


def test_material_clean_has_download_lease_fields():
    columns = MaterialClean.__table__.c
    assert set(columns.keys()) >= {
        "download_claim_token",
        "download_claimed_at",
        "download_attempt_count",
        "download_next_retry_at",
        "download_last_error",
    }
    assert columns.download_attempt_count.default.arg == 0
    assert columns.download_attempt_count.server_default.arg == "0"
    assert "idx_mc_download_claim" in {index.name for index in MaterialClean.__table__.indexes}
