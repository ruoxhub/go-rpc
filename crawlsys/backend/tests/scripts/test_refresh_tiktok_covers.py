from services.video_download.naming import cover_object_name
from scripts.refresh_tiktok_covers import extract_cover_url


def test_extract_cover_url_uses_video_detail_content_cover():
    detail = {
        "itemInfo": {
            "itemStruct": {
                "id": "video-1",
                "video": {"cover": "https://example.com/fresh-cover.jpg"},
            }
        }
    }

    assert extract_cover_url(detail, "video-1") == "https://example.com/fresh-cover.jpg"


def test_cover_object_name_is_deterministic_and_safe():
    assert cover_object_name("video/1") == "video%2F1/pic"
