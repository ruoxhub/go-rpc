import unittest
from datetime import datetime
from app.parser.bilibili.parser import (
    parse_video_item,
    parse_search,
    parse_get_user_info,
    parse_get_comment,
    parse_get_user_contents,
    parse_get_content,
)


class TestBilibiliParser(unittest.TestCase):
    def test_parse_video_item_normal(self):
        item = {
            "bvid": "BV1test123",
            "aid": 112233,
            "mid": "998877",
            "author": "测试UP主",
            "title": "测试视频标题 <em class=\"keyword\">Python</em>",
            "description": "这是测试视频简介",
            "pic": "//i0.hdslb.com/bfs/archive/test.jpg",
            "upic": "//i0.hdslb.com/bfs/face/test.jpg",
            "duration": "05:30",
            "pubdate": 1700000000,
            "play": 12345,
            "video_review": 678,
            "favorites": 89,
            "like": 456,
        }
        content, user = parse_video_item(item)
        self.assertIsNotNone(content)
        self.assertEqual(content["content_id"], "BV1test123")
        self.assertEqual(content["title"], "测试视频标题 Python")
        self.assertEqual(content["author"], "测试UP主")
        self.assertEqual(content["duration"], 330)
        self.assertTrue(content["pic"].startswith("https://"))
        self.assertEqual(content["datatype"], "content")
        self.assertEqual(content["platform"], "bilibili")

        self.assertIsNotNone(user)
        self.assertEqual(user["user_id"], "998877")
        self.assertEqual(user["username"], "测试UP主")
        self.assertTrue(user["avatar"].startswith("https://"))
        self.assertEqual(user["datatype"], "user")

    def test_parse_search_empty(self):
        records = list(parse_search({}))
        self.assertEqual(len(records), 0)

    def test_parse_search_items(self):
        mock_resp = {
            "code": 0,
            "data": {
                "result": [
                    {
                        "result_type": "video",
                        "data": [
                            {
                                "bvid": "BV1abc",
                                "aid": 101,
                                "mid": "202",
                                "author": "UP1",
                                "title": "Video 1",
                                "pubdate": 1700000000,
                            }
                        ]
                    }
                ]
            }
        }
        records = list(parse_search(mock_resp))
        self.assertEqual(len(records), 2)
        types = [r["datatype"] for r in records]
        self.assertIn("content", types)
        self.assertIn("user", types)

    def test_parse_get_user_info(self):
        mock_user_resp = {
            "code": 0,
            "data": {
                "mid": 8047632,
                "name": "哔哩哔哩弹幕网",
                "face": "//i0.hdslb.com/bfs/face/official.jpg",
                "sign": "官方账号",
                "sex": "保密",
                "level": 6,
            }
        }
        records = list(parse_get_user_info(mock_user_resp))
        self.assertEqual(len(records), 1)
        user = records[0]
        self.assertEqual(user["datatype"], "user")
        self.assertEqual(user["user_id"], "8047632")
        self.assertEqual(user["username"], "哔哩哔哩弹幕网")
        self.assertTrue(user["avatar"].startswith("https://"))

    def test_parse_get_comment(self):
        mock_comment_resp = {
            "code": 0,
            "data": {
                "replies": [
                    {
                        "rpid": 11111,
                        "oid": 22222,
                        "mid": 33333,
                        "member": {"uname": "评论人A"},
                        "content": {"message": "好视频！"},
                        "like": 10,
                        "rcount": 1,
                        "ctime": 1700000000,
                        "replies": [
                            {
                                "rpid": 11112,
                                "oid": 22222,
                                "mid": 44444,
                                "parent": 11111,
                                "member": {"uname": "回复人B"},
                                "content": {"message": "赞同+1"},
                                "like": 2,
                                "rcount": 0,
                                "ctime": 1700000050,
                            }
                        ]
                    }
                ]
            }
        }
        records = list(parse_get_comment(mock_comment_resp))
        self.assertEqual(len(records), 2)
        self.assertEqual(records[0]["comment_id"], "11111")
        self.assertEqual(records[0]["content"], "好视频！")
        self.assertEqual(records[1]["comment_id"], "11112")
        self.assertEqual(records[1]["parent_comment_id"], "11111")


if __name__ == "__main__":
    unittest.main()
