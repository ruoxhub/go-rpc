from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from services.video_download import (
    VideoDownloadResult,
    VideoDownloadService,
    derive_content_type,
    derive_object_name,
    derive_image_content_type,
)
from services.video_download.naming import cover_object_name, image_object_name
from storage import MinioDB


class AsyncMinio:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.uploads: list[dict] = []
        self.buckets: list[str] = []

    async def amake_bucket(self, bucket: str):
        self.buckets.append(bucket)

    async def aput_object(self, *args, **kwargs):
        stream = args[2]
        upload = {
            "args": args,
            "kwargs": kwargs,
            "position": stream.tell(),
            "body": stream.read(),
            "rolled": getattr(stream, "_rolled", False),
            "stream": stream,
        }
        self.uploads.append(upload)
        if self.error:
            raise self.error


def client_for(status: int = 200, body: bytes = b"video", content_type: str | None = "video/webm"):
    def handler(request: httpx.Request) -> httpx.Response:
        headers = {"content-type": content_type} if content_type else {}
        return httpx.Response(status, headers=headers, content=body, request=request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_object_name_prefers_content_type_and_sanitizes_inputs() -> None:
    assert derive_object_name(
        "tik/tok", "../123", "https://cdn/x.mp4?q=evil", "video/webm"
    ) == "..%2F123/video"
    assert "?" not in derive_object_name("tiktok", "123", "https://cdn/x.mp4?x=/../bad", None)


def test_object_name_falls_back_to_url_then_mp4() -> None:
    assert derive_object_name("tiktok", "123", "https://cdn/path/video.mov?x=1", None) == "123/video"
    assert derive_object_name("tiktok", "123", "https://cdn/path/?x=.webm", None) == "123/video"
    assert derive_content_type(None, ".mp4") == "video/mp4"
    assert derive_object_name("", "123", "https://cdn/video.mp4", None) == "123/video"


def test_derive_image_content_type_detects_ytdlp_image_file(tmp_path) -> None:
    image = tmp_path / "video.image"
    image.write_bytes(b"\xff\xd8\xff\xe0" + b"image")
    assert derive_image_content_type(image) == "image/jpeg"


def test_numbered_image_object_name_uses_content_directory() -> None:
    assert image_object_name("123", 2) == "123/image_2"
    with pytest.raises(ValueError, match="greater than zero"):
        image_object_name("123", 0)


@pytest.mark.parametrize("object_name", ["../video.mp4", "/video.mp4", "a/../../video.mp4"])
@pytest.mark.asyncio
async def test_explicit_object_name_rejects_path_traversal(object_name: str) -> None:
    async with client_for() as client:
        with pytest.raises(ValueError, match="路径穿越"):
            await VideoDownloadService(client, AsyncMinio(), "videos").download(
                "https://cdn/video", "tiktok", "123", object_name=object_name
            )


@pytest.mark.asyncio
async def test_http_failure_does_not_upload() -> None:
    minio = AsyncMinio()
    async with client_for(status=503) as client:
        service = VideoDownloadService(client, minio, "videos")
        with pytest.raises(httpx.HTTPStatusError):
            await service.download("https://cdn/video.mp4", "tiktok", "123")
    assert minio.uploads == []


@pytest.mark.asyncio
async def test_upload_failure_is_propagated() -> None:
    error = RuntimeError("upload failed")
    minio = AsyncMinio(error)
    async with client_for() as client:
        with pytest.raises(RuntimeError, match="upload failed"):
            await VideoDownloadService(client, minio, "videos").download(
                "https://cdn/video", "tiktok", "123"
            )
    assert minio.uploads[0]["stream"].closed


@pytest.mark.asyncio
async def test_success_returns_frozen_result_and_rewinds_stream() -> None:
    minio = AsyncMinio()
    async with client_for(body=b"abcdef") as client:
        result = await VideoDownloadService(client, minio, "videos").download(
            "https://cdn/video.mp4?token=x", "tiktok", "123"
        )
    assert result == VideoDownloadResult("123/video", 6, "video/webm")
    assert minio.buckets == ["tiktok"]
    with pytest.raises(AttributeError):
        result.size = 7  # type: ignore[misc]
    upload = minio.uploads[0]
    assert upload["position"] == 0
    assert upload["body"] == b"abcdef"
    assert upload["args"][3] == len(upload["body"])
    stream = upload["stream"]
    assert stream.closed


@pytest.mark.asyncio
async def test_download_cover_uses_images_bucket_and_pic_prefix() -> None:
    minio = AsyncMinio()
    async with client_for(body=b"image", content_type="image/jpeg") as client:
        service = VideoDownloadService(
            client, minio, "videos", cover_bucket="images"
        )
        result = await service.download_cover(
            "https://cdn/cover.jpg", "tiktok", "123"
        )

    assert result.object_name == "123/pic"
    assert minio.uploads[0]["args"][:2] == ("tiktok", "123/pic")
    assert cover_object_name("123") == "123/pic"


@pytest.mark.asyncio
async def test_ytdlp_download_uploads_video_audio_and_cover() -> None:
    class FakeYtDlp:
        async def download(self, url: str, output_dir: Path):
            video = output_dir / "video.mp4"
            audio = output_dir / "audio.m4a"
            cover = output_dir / "video.jpg"
            video.write_bytes(b"video")
            audio.write_bytes(b"audio")
            cover.write_bytes(b"\xff\xd8\xffcover")
            return SimpleNamespace(
                video_path=video, audio_path=audio, cover_path=cover
            )

    minio = AsyncMinio()
    async with client_for() as client:
        results = await VideoDownloadService(
            client,
            minio,
            "videos",
            audio_bucket="audios",
            cover_bucket="images",
            ytdlp_client=FakeYtDlp(),
        ).download_with_ytdlp("https://example/video/1", "tiktok", "123")

    assert [upload["args"][:2] for upload in minio.uploads] == [
        ("tiktok", "123/video"),
        ("tiktok", "123/pic"),
        ("tiktok", "123/audio"),
    ]
    assert [result.size for result in results] == [5, 5, 8]


@pytest.mark.asyncio
async def test_download_media_uses_unified_downloader_and_uploads_all_files(
    monkeypatch,
) -> None:
    calls = []

    def fake_download(output_dir: Path, **kwargs):
        calls.append(kwargs)
        video = output_dir / "123.webm"
        video.write_bytes(b"video")
        audio = output_dir / "123.m4a"
        audio.write_bytes(b"audio")
        cover = output_dir / "123.png"
        cover.write_bytes(b"image")
        return SimpleNamespace(video_path=video, audio_path=audio, cover_path=cover)

    monkeypatch.setattr(
        "services.video_download.service.download_media_files", fake_download
    )
    minio = AsyncMinio()
    async with client_for() as client:
        results = await VideoDownloadService(
            client, minio, "videos", proxy_url="http://proxy"
        ).download_media(
            "video-url", "music-url", "pic-url", "tiktok", "123"
        )

    assert calls == [{
        "content_id": "123",
        "video_url": "video-url",
        "music_url": "music-url",
        "pic_url": "pic-url",
        "proxy_url": "http://proxy",
    }]
    assert [upload["args"][:2] for upload in minio.uploads] == [
        ("tiktok", "123/video"),
        ("tiktok", "123/audio"),
        ("tiktok", "123/pic"),
    ]
    assert [result.object_name for result in results] == [
        "123/video", "123/audio", "123/pic"
    ]
    assert [result.content_type for result in results] == [
        "video/webm", "audio/mp4", "image/png"
    ]


@pytest.mark.asyncio
async def test_large_download_rolls_spool_to_disk_before_upload() -> None:
    minio = AsyncMinio()
    async with client_for(body=b"x" * 32) as client:
        await VideoDownloadService(client, minio, "videos", spool_max_size=8).download(
            "https://cdn/video.mp4", "tiktok", "123"
        )
    assert minio.uploads[0]["rolled"] is True


@pytest.mark.asyncio
async def test_stream_error_closes_temporary_stream(monkeypatch) -> None:
    from app.services.video_download import service as service_module

    streams = []
    original = tempfile.SpooledTemporaryFile

    def tracked_spool(*args, **kwargs):
        stream = original(*args, **kwargs)
        streams.append(stream)
        return stream

    class BrokenStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"partial"
            raise httpx.ReadError("stream interrupted")

    monkeypatch.setattr(service_module.tempfile, "SpooledTemporaryFile", tracked_spool)
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=BrokenStream(), request=request)
    )
    minio = AsyncMinio()
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(httpx.ReadError, match="interrupted"):
            await VideoDownloadService(client, minio, "videos").download(
                "https://cdn/video.mp4", "tiktok", "123"
            )
    assert streams and streams[0].closed
    assert minio.uploads == []


@pytest.mark.asyncio
async def test_download_uses_url_extension_when_header_is_missing() -> None:
    async with client_for(content_type=None) as client:
        result = await VideoDownloadService(client, AsyncMinio(), "videos").download(
            "https://cdn/video.mov?format=.bad", "tiktok", "123"
        )
    assert result.object_name == "123/video"
    assert result.content_type == "video/quicktime"


def test_target_scripts_use_shared_service() -> None:
    from scripts import clean_and_download_videos, download_video_input_minio

    assert clean_and_download_videos.VideoDownloadService is VideoDownloadService
    assert download_video_input_minio.VideoDownloadService is VideoDownloadService
    assert not hasattr(clean_and_download_videos, "_derive_ext")
    assert not hasattr(download_video_input_minio, "_derive_object_name")


@pytest.mark.parametrize(
    ("module_name", "expected_options"),
    [
        (
            "scripts.download_video_input_minio",
            {
                "--url",
                "--config",
                "--bucket",
                "--object-name",
                "--no-proxy",
                "--secure",
            },
        ),
        (
            "scripts.clean_and_download_videos",
            {
                "--config",
                "--platform",
                "--only-clean",
                "--skip-clean",
                "--source",
                "--min-grade",
                "--bucket",
                "--limit",
                "--offset",
                "--concurrency",
                "--rps",
                "--no-proxy",
            },
        ),
    ],
)
def test_script_help_preserves_cli_options(
    module_name, expected_options, monkeypatch, capsys
) -> None:
    module = __import__(module_name, fromlist=["main"])
    monkeypatch.setattr(sys, "argv", [module_name, "--help"])
    with pytest.raises(SystemExit) as exc_info:
        module.main()
    assert exc_info.value.code == 0
    help_text = capsys.readouterr().out
    actual_options = {
        part.split("=")[0] for part in help_text.split() if part.startswith("--")
    }
    assert expected_options <= actual_options


def test_single_download_cli_creates_bucket_once(monkeypatch) -> None:
    from scripts import download_video_input_minio as script

    class FakeMinio:
        def __init__(self, **kwargs):
            self.buckets = []

        def make_bucket(self, bucket):
            self.buckets.append(bucket)

    minio = FakeMinio()
    monkeypatch.setattr(script, "MinioDB", lambda **kwargs: minio)
    config = {"host": "h", "port": 1, "username": "u", "password": "p"}
    monkeypatch.setattr(script, "_load_config", lambda path: (config, None))
    monkeypatch.setattr(script, "download_and_upload", lambda **kwargs: "123.mp4")
    monkeypatch.setattr(sys, "argv", ["download_video_input_minio.py", "--bucket", "videos"])
    script.main()
    assert minio.buckets == ["videos"]


@pytest.mark.asyncio
async def test_empty_download_cleans_temporary_stream() -> None:
    minio = AsyncMinio()
    async with client_for(body=b"") as client:
        with pytest.raises(ValueError, match="为空"):
            await VideoDownloadService(client, minio, "videos").download(
                "https://cdn/video", "tiktok", "123"
            )
    assert minio.uploads == []


@pytest.mark.parametrize("content_type", ["text/html", "application/json"])
@pytest.mark.asyncio
async def test_known_non_video_content_type_is_rejected_without_upload(content_type) -> None:
    minio = AsyncMinio()
    async with client_for(content_type=content_type) as client:
        with pytest.raises(ValueError, match="不是视频"):
            await VideoDownloadService(client, minio, "videos").download(
                "https://cdn/video.mp4", "tiktok", "123"
            )
    assert minio.uploads == []


@pytest.mark.asyncio
async def test_sync_minio_upload_runs_through_to_thread(monkeypatch) -> None:
    minio = type(
        "SyncMinio",
        (),
        {
            "make_bucket": lambda self, *a, **kw: None,
            "put_object": lambda self, *a, **kw: None,
        },
    )()
    to_thread = AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs))
    monkeypatch.setattr(asyncio, "to_thread", to_thread)
    async with client_for() as client:
        await VideoDownloadService(client, minio, "videos").download(
            "https://cdn/video", "tiktok", "123"
        )
    assert to_thread.await_count == 2


@pytest.mark.asyncio
async def test_sync_mode_minio_db_uses_put_object_in_thread(monkeypatch) -> None:
    class SyncImpl:
        def __init__(self):
            self.calls = []

        def make_bucket(self, *args, **kwargs):
            self.calls.append((args, kwargs))

        def put_object(self, *args, **kwargs):
            self.calls.append((args, kwargs))

    minio = MinioDB.__new__(MinioDB)
    minio._amode = False
    minio._impl = SyncImpl()
    to_thread = AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs))
    monkeypatch.setattr(asyncio, "to_thread", to_thread)

    async with client_for() as client:
        await VideoDownloadService(client, minio, "videos").download(
            "https://cdn/video.mp4", "tiktok", "123"
        )

    assert to_thread.await_count == 2
    assert len(minio._impl.calls) == 2
