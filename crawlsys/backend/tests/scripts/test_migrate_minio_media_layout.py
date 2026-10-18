from types import SimpleNamespace

import pytest

from scripts.migrate_minio_media_layout import Migration, build_plan, migrate, target_object_name


@pytest.mark.parametrize(
    ("bucket", "source", "target"),
    [
        ("videos", "tiktok/123.mp4", ("tiktok", "123/video")),
        ("audios", "tiktok/audio/123.m4a", ("tiktok", "123/audio")),
        ("images", "tiktok/pic/123.jpg", ("tiktok", "123/pic")),
        ("images", "tiktok/pic/123", ("tiktok", "123/pic")),
        ("videos", "tiktok/123/video", None),
    ],
)
def test_target_object_name(bucket, source, target):
    assert target_object_name(bucket, source) == target


def test_build_plan_rejects_multiple_sources_for_same_target():
    class Client:
        def bucket_exists(self, bucket):
            return bucket == "videos"

        def list_objects(self, bucket, recursive):
            return [
                SimpleNamespace(object_name="tiktok/123.mp4"),
                SimpleNamespace(object_name="tiktok/123.webm"),
            ]

    with pytest.raises(RuntimeError, match="多个源对象"):
        build_plan(Client())


def test_migrate_rejects_same_size_target_with_different_etag():
    migration = Migration("videos", "tiktok", "tiktok/123.mp4", "123/video")

    class Client:
        def bucket_exists(self, bucket):
            return True

        def stat_object(self, bucket, object_name):
            etag = "source" if bucket == "videos" else "target"
            return SimpleNamespace(size=5, etag=etag)

    with pytest.raises(RuntimeError, match="内容不同"):
        migrate(Client(), [migration], delete_source=True)
