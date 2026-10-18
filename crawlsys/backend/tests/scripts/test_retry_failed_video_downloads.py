from scripts.retry_failed_video_downloads import (
    SELECT_FAILED_SQL,
    _derive_ext,
    extract_video_url,
)


def test_extract_video_url_returns_target_video_media():
    detail = {
        "itemInfo": {
            "itemStruct": {
                "id": "123",
                "author": {"id": "user-1"},
                "video": {
                    "PlayAddrStruct": {
                        "UrlList": ["https://old.example/video", "https://new.example/video"]
                    }
                },
            }
        }
    }

    assert extract_video_url(detail, "123") == "https://new.example/video"


def test_extract_video_url_rejects_detail_without_video_url():
    detail = {"itemInfo": {"itemStruct": {"id": "123", "video": {}}}}

    try:
        extract_video_url(detail, "123")
    except ValueError as error:
        assert "CDN" in str(error)
    else:
        raise AssertionError("缺少视频地址时应抛出 ValueError")


def test_failed_query_filters_all_graded_materials():
    sql = str(SELECT_FAILED_SQL).lower()

    assert "from t_material_clean mc" in sql
    assert "mc.clean_status = 'graded'" in sql
    assert "mc.is_delete = 0" in sql
    assert "join t_busi_content c" in sql
    assert "mc.platform = 'tiktok'" in sql


def test_derive_ext_falls_back_for_tiktok_cdn_path():
    assert _derive_ext("https://cdn.example/path/?signature=x") == ".mp4"
    assert _derive_ext("https://cdn.example/video.mp4?signature=x") == ".mp4"
