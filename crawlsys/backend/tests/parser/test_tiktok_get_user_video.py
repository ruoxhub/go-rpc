from datetime import datetime

from parser import general_parser
from parser.tiktok.getUserVideo import parse_get_user_video


SAMPLE_RESPONSE = {
    "itemList": [
        {
            "id": "7520000000000000000",
            "desc": "demo video",
            "createTime": 1710000000,
            "author": {
                "id": "123",
                "uniqueId": "demo_user",
                "nickname": "Demo User",
            },
            "video": {
                "cover": "https://example.com/cover.jpg",
                "playAddr": "https://example.com/video.mp4",
                "duration": 12,
            },
            "music": {"playUrl": "https://example.com/audio.mp3"},
            "statsV2": {
                "shareCount": "1",
                "repostCount": "2",
                "commentCount": "3",
                "diggCount": "4",
                "playCount": "5",
                "collectCount": "6",
            },
        }
    ]
}


def test_get_user_video_reuses_video_parser():
    items = list(parse_get_user_video(SAMPLE_RESPONSE))

    assert [item["datatype"] for item in items] == ["content", "user"]
    assert items[0]["content_id"] == "7520000000000000000"
    assert items[0]["platform"] == "tiktok"
    assert items[0]["pub_time"] == datetime(2024, 3, 9, 16, 0)


def test_general_parser_registers_get_user_video():
    items = list(
        general_parser.parse("tiktok", SAMPLE_RESPONSE, "getUserVideo", as_dto=False)
    )

    assert items[0]["datatype"] == "content"
