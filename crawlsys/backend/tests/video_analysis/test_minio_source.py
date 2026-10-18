from pathlib import Path

import pytest

from services.video_analysis.minio_source import (
    AmbiguousVideoObjectError,
    DownloadedMinioVideo,
    MinioVideoSource,
    VideoObjectNotFoundError,
)
from services.video_download import derive_object_name, video_object_stem


class FakeObject:
    def __init__(self, object_name: str):
        self.object_name = object_name


class FakeMinio:
    def __init__(
        self,
        object_names: list[str],
        payload: bytes = b"video",
        download_error: Exception | None = None,
        write_sdk_partial_on_error: bool = False,
    ):
        self.object_names = object_names
        self.payload = payload
        self.download_error = download_error
        self.write_sdk_partial_on_error = write_sdk_partial_on_error
        self.list_calls: list[tuple[str, str, bool]] = []
        self.download_calls: list[tuple[str, str, str]] = []

    async def alist_objects(self, bucket, *, prefix, recursive):
        self.list_calls.append((bucket, prefix, recursive))
        return [
            FakeObject(name)
            for name in self.object_names
            if name.startswith(prefix)
        ]

    async def afget_object(self, bucket, object_name, file_path, **kwargs):
        self.download_calls.append((bucket, object_name, file_path, kwargs))
        output_path = (
            Path(kwargs["tmp_file_path"])
            if self.download_error is not None
            and self.write_sdk_partial_on_error
            else Path(file_path)
        )
        output_path.write_bytes(self.payload)
        if self.download_error is not None:
            raise self.download_error


@pytest.mark.asyncio
async def test_download_matches_exact_stem_and_records_minio_calls(tmp_path):
    minio = FakeMinio(
        [
            "tiktok/1234.mp4",
            "tiktok/123.mp4",
            "tiktok/nested/123.mov",
        ]
    )
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id="123", target_dir=tmp_path / "input"
    )

    expected_path = tmp_path / "input" / "123.mp4"
    assert source.bucket == "videos"
    assert result == DownloadedMinioVideo("tiktok/123.mp4", expected_path, "videos")
    assert expected_path.read_bytes() == b"video"
    assert minio.list_calls == [
        ("tiktok", "123/video", True),
        ("videos", "tiktok/123", True),
    ]
    assert minio.download_calls[0][:2] == ("videos", "tiktok/123.mp4")
    assert minio.download_calls[0][2] != str(expected_path)
    assert Path(minio.download_calls[0][2]).parent == expected_path.parent
    assert not Path(minio.download_calls[0][2]).exists()
    sdk_temp = Path(minio.download_calls[0][3]["tmp_file_path"])
    assert sdk_temp.parent == expected_path.parent
    assert not sdk_temp.exists()


@pytest.mark.asyncio
async def test_download_raises_when_exact_object_is_missing(tmp_path):
    source = MinioVideoSource(
        FakeMinio(["tiktok/1234.mp4", "other/123.mp4"]), "videos"
    )

    with pytest.raises(VideoObjectNotFoundError, match="123"):
        await source.download(
            platform="tiktok", content_id="123", target_dir=tmp_path
        )


@pytest.mark.asyncio
async def test_download_raises_when_multiple_extensions_match(tmp_path):
    source = MinioVideoSource(
        FakeMinio(["tiktok/123.mp4", "tiktok/123.webm"]), "videos"
    )

    with pytest.raises(AmbiguousVideoObjectError, match="123"):
        await source.download(
            platform="tiktok", content_id="123", target_dir=tmp_path
        )


@pytest.mark.asyncio
async def test_download_uses_safe_id_only_for_local_filename(tmp_path):
    minio = FakeMinio(["tiktok/a%3Ab-c.mp4", "tiktok/a_b-c.mp4"])
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id="a:b-c", target_dir=tmp_path
    )

    assert result.local_path == tmp_path / "a_b-c.mp4"
    assert result.object_name == "tiktok/a%3Ab-c.mp4"
    assert minio.list_calls == [
        ("tiktok", "a%3Ab-c/video", True),
        ("videos", "tiktok/a%3Ab-c", True),
    ]


@pytest.mark.asyncio
async def test_download_uses_video_suffix_when_object_has_no_suffix(tmp_path):
    minio = FakeMinio(["tiktok/123"])
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id="123", target_dir=tmp_path
    )

    assert result.object_name == "tiktok/123"
    assert result.local_path == tmp_path / "123.video"
    assert result.local_path.read_bytes() == b"video"


@pytest.mark.asyncio
async def test_download_removes_empty_file_and_raises_not_found(tmp_path):
    minio = FakeMinio(["tiktok/123.mp4"], payload=b"")
    source = MinioVideoSource(minio, "videos")
    target = tmp_path / "123.mp4"

    with pytest.raises(VideoObjectNotFoundError, match="empty"):
        await source.download(
            platform="tiktok", content_id="123", target_dir=tmp_path
        )

    assert not target.exists()


@pytest.mark.asyncio
async def test_download_failure_removes_partial_and_preserves_existing_final(tmp_path):
    final = tmp_path / "123.mp4"
    final.write_bytes(b"old")
    minio = FakeMinio(
        ["tiktok/123.mp4"],
        payload=b"partial",
        download_error=RuntimeError("download failed"),
        write_sdk_partial_on_error=True,
    )
    source = MinioVideoSource(minio, "videos")

    with pytest.raises(RuntimeError, match="download failed"):
        await source.download(
            platform="tiktok", content_id="123", target_dir=tmp_path
        )

    assert final.read_bytes() == b"old"
    assert list(tmp_path.glob("*.partial")) == []
    assert list(tmp_path.glob("*.partial.minio")) == []
    assert "tmp_file_path" in minio.download_calls[0][3]


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["", ".", ".."])
async def test_download_rejects_unsafe_platform(platform, tmp_path):
    minio = FakeMinio([])
    source = MinioVideoSource(minio, "videos")

    with pytest.raises(ValueError, match="platform"):
        await source.download(
            platform=platform, content_id="123", target_dir=tmp_path
        )

    assert minio.list_calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize("content_id", ["", ".", ".."])
async def test_download_rejects_unsafe_content_id_without_listing(
    content_id, tmp_path
):
    minio = FakeMinio([])
    source = MinioVideoSource(minio, "videos")

    with pytest.raises(ValueError, match="content_id"):
        await source.download(
            platform="tiktok", content_id=content_id, target_dir=tmp_path
        )

    assert minio.list_calls == []


@pytest.mark.asyncio
async def test_download_sanitizes_all_unsafe_content_characters(tmp_path):
    minio = FakeMinio(["tiktok/%3A%3F%3F.mp4"])
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id=":??", target_dir=tmp_path
    )

    assert result.local_path == tmp_path / "___.mp4"
    assert minio.list_calls == [
        ("tiktok", "%3A%3F%3F/video", True),
        ("videos", "tiktok/%3A%3F%3F", True),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("content_id", ["a:b", "a?b"])
async def test_download_matches_encoded_content_id_without_safe_name_collision(
    content_id, tmp_path
):
    stem = video_object_stem("tiktok", content_id)
    minio = FakeMinio([f"{stem}.mp4", "tiktok/a_b.mp4"])
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id=content_id, target_dir=tmp_path
    )

    assert result.object_name == f"{stem}.mp4"
    assert result.local_path.name == "a_b.mp4"
    assert minio.list_calls == [
        ("tiktok", f"{stem.removeprefix('tiktok/')}/video", True),
        ("videos", stem, True),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("platform", "content_id"),
    [
        ("抖音", "视频.一"),
        ("tik/tok", "a/b"),
        ("tik?tok", "a?b"),
    ],
)
async def test_download_roundtrips_shared_object_naming(
    platform, content_id, tmp_path
):
    object_name = derive_object_name(
        platform, content_id, "https://cdn/video.mp4", "video/mp4"
    )
    source = MinioVideoSource(FakeMinio([object_name]), "videos")

    result = await source.download(
        platform=platform, content_id=content_id, target_dir=tmp_path
    )

    assert result.object_name == object_name
    assert ".." not in object_name.split("/")


def test_shared_object_names_do_not_collide_or_traverse():
    slash = video_object_stem("tiktok", "a/b")
    question = video_object_stem("tiktok", "a?b")

    assert slash == "tiktok/a%2Fb"
    assert question == "tiktok/a%3Fb"
    assert slash != question


@pytest.mark.asyncio
async def test_download_falls_back_to_legacy_unicode_object_name(tmp_path):
    minio = FakeMinio(["tiktok/视频一.mp4"])
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id="视频一", target_dir=tmp_path
    )

    assert result.object_name == "tiktok/视频一.mp4"
    assert [call[1] for call in minio.list_calls] == [
        "%E8%A7%86%E9%A2%91%E4%B8%80/video",
        "tiktok/%E8%A7%86%E9%A2%91%E4%B8%80",
        "tiktok/视频一",
    ]


@pytest.mark.asyncio
async def test_download_prefers_new_name_when_new_and_legacy_both_exist(tmp_path):
    new_name = "tiktok/%E8%A7%86%E9%A2%91%E4%B8%80.mp4"
    minio = FakeMinio([new_name, "tiktok/视频一.mp4"])
    source = MinioVideoSource(minio, "videos")

    result = await source.download(
        platform="tiktok", content_id="视频一", target_dir=tmp_path
    )

    assert result.object_name == new_name
    assert [call[1] for call in minio.list_calls] == [
        "%E8%A7%86%E9%A2%91%E4%B8%80/video",
        "tiktok/%E8%A7%86%E9%A2%91%E4%B8%80"
    ]


@pytest.mark.asyncio
async def test_download_does_not_use_legacy_fallback_for_slash(tmp_path):
    minio = FakeMinio(["tiktok/a/b.mp4"])
    source = MinioVideoSource(minio, "videos")

    with pytest.raises(VideoObjectNotFoundError):
        await source.download(
            platform="tiktok", content_id="a/b", target_dir=tmp_path
        )

    assert [call[1] for call in minio.list_calls] == [
        "a%2Fb/video",
        "tiktok/a%2Fb",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("object_name", "expected_name"),
    [
        ("tiktok/123.bad-extension", "123.video"),
        ("tiktok/123.abcdefghijkl", "123.video"),
        ("tiktok/123.mp4:stream", "123.video"),
        ("tiktok/123.mp4", "123.mp4"),
    ],
)
async def test_download_allows_only_safe_local_suffix(
    object_name, expected_name, tmp_path
):
    source = MinioVideoSource(FakeMinio([object_name]), "videos")

    result = await source.download(
        platform="tiktok", content_id="123", target_dir=tmp_path
    )

    assert result.local_path.name == expected_name


@pytest.mark.asyncio
async def test_download_prefixes_windows_reserved_local_name(tmp_path):
    source = MinioVideoSource(FakeMinio(["tiktok/CON.mp4"]), "videos")

    result = await source.download(
        platform="tiktok", content_id="CON", target_dir=tmp_path
    )

    assert result.object_name == "tiktok/CON.mp4"
    assert result.local_path.name == "_CON.mp4"


@pytest.mark.asyncio
async def test_download_atomically_replaces_symlink_instead_of_following_it(tmp_path):
    victim = tmp_path / "victim.mp4"
    victim.write_bytes(b"keep")
    final = tmp_path / "123.mp4"
    try:
        final.symlink_to(victim)
    except (NotImplementedError, OSError):
        pytest.skip("symlinks are unavailable")
    source = MinioVideoSource(FakeMinio(["tiktok/123.mp4"]), "videos")

    result = await source.download(
        platform="tiktok", content_id="123", target_dir=tmp_path
    )

    assert result.local_path == final
    assert not final.is_symlink()
    assert final.read_bytes() == b"video"
    assert victim.read_bytes() == b"keep"
