from __future__ import annotations

import asyncio
import inspect
import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from tools.ytdlp import YtDlpClient
from tools.video_downloader import download_media as download_media_files

from .naming import audio_object_stem, cover_object_name, video_object_name


@dataclass(frozen=True)
class VideoDownloadResult:
    object_name: str
    size: int
    content_type: str


def _extension(content_type: str | None, url: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized.startswith("video/"):
        guessed = mimetypes.guess_extension(normalized)
        if guessed:
            return ".mp4" if guessed == ".m4v" else guessed

    suffix = PurePosixPath(urlparse(url).path).suffix.lower()
    if suffix and 2 <= len(suffix) <= 5 and suffix[1:].isalnum():
        return suffix
    return ".mp4"


def derive_content_type(content_type: str | None, extension: str) -> str:
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized.startswith("video/"):
        return normalized
    guessed, _ = mimetypes.guess_type(f"video{extension}")
    return guessed if guessed and guessed.startswith("video/") else "video/mp4"


def derive_image_content_type(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    if guessed and guessed.startswith("image/"):
        return guessed
    header = path.read_bytes()[:16]
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("无法识别 yt-dlp 封面格式")


def derive_audio_content_type(path: Path) -> str:
    guessed = mimetypes.guess_type(path.name)[0]
    return guessed if guessed and guessed.startswith("audio/") else "audio/mp4"


def derive_object_name(
    platform: str,
    content_id: str,
    url: str,
    content_type: str | None,
) -> str:
    return video_object_name(content_id)


def _validate_object_name(object_name: str) -> str:
    normalized = object_name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not normalized or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("MinIO 对象名不能包含绝对路径或路径穿越")
    return normalized


class VideoDownloadService:
    """使用复用的 HTTP 与 MinIO 客户端下载并上传视频。"""

    def __init__(
        self,
        http_client: httpx.AsyncClient,
        minio: Any,
        bucket: str,
        *,
        cover_bucket: str | None = None,
        audio_bucket: str | None = None,
        ytdlp_client: YtDlpClient | None = None,
        proxy_url: str = "",
        spool_max_size: int = 8 << 20,
    ) -> None:
        self._http_client = http_client
        self._minio = minio
        self._bucket = bucket
        self._cover_bucket = cover_bucket
        self._audio_bucket = audio_bucket
        self._ytdlp_client = ytdlp_client or YtDlpClient()
        self._proxy_url = proxy_url
        self._spool_max_size = spool_max_size
        self._ready_buckets: set[str] = set()

    async def download_media(
        self,
        video_url: str,
        music_url: str | None,
        pic_url: str | None,
        platform: str,
        content_id: str,
    ) -> tuple[VideoDownloadResult, VideoDownloadResult, VideoDownloadResult]:
        """使用统一 download_media 下载直链资源并上传 MinIO。"""
        if not music_url or not pic_url:
            raise ValueError("download_media requires video, music and cover URLs")
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            downloaded = await asyncio.to_thread(
                download_media_files,
                output_dir,
                content_id=content_id,
                video_url=video_url,
                music_url=music_url or "",
                pic_url=pic_url or "",
                proxy_url=self._proxy_url,
            )
            paths = (
                (downloaded.video_path, video_object_name(content_id)),
                (downloaded.audio_path, audio_object_stem(content_id)),
                (downloaded.cover_path, cover_object_name(content_id)),
            )
            results: list[VideoDownloadResult] = []
            for path, target in paths:
                if path is None or not path.is_file():
                    missing = path.name if path is not None else target
                    raise RuntimeError(f"download_media 未生成文件：{missing}")
                content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                with path.open("rb") as stream:
                    size = path.stat().st_size
                    await self._upload(target, stream, size, content_type, bucket=platform)
                results.append(VideoDownloadResult(target, size, content_type))
        return results[0], results[1], results[2]

    async def download(
        self,
        url: str,
        platform: str,
        content_id: str,
        *,
        object_name: str | None = None,
    ) -> VideoDownloadResult:
        with tempfile.SpooledTemporaryFile(max_size=self._spool_max_size, mode="w+b") as stream:
            async with self._http_client.stream("GET", url) as response:
                response.raise_for_status()
                header_type = response.headers.get("content-type")
                normalized_header = (header_type or "").split(";", 1)[0].strip().lower()
                if normalized_header and not (
                    normalized_header.startswith("video/")
                    or normalized_header == "application/octet-stream"
                ):
                    raise ValueError(f"下载内容不是视频：Content-Type={header_type}")
                extension = _extension(header_type, url)
                content_type = derive_content_type(header_type, extension)
                size = 0
                async for chunk in response.aiter_bytes(chunk_size=1 << 20):
                    stream.write(chunk)
                    size += len(chunk)

            if size == 0:
                raise ValueError("下载到的视频为空")

            target = _validate_object_name(
                object_name or derive_object_name(platform, content_id, url, header_type)
            )
            stream.seek(0)
            await self._upload(target, stream, size, content_type, bucket=platform)
            return VideoDownloadResult(target, size, content_type)

    async def download_cover(
        self, url: str, platform: str, content_id: str
    ) -> VideoDownloadResult:
        if self._cover_bucket is None:
            raise ValueError("cover bucket is not configured")
        response = await self._http_client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if not content_type.startswith("image/"):
            raise ValueError(f"下载内容不是图片：Content-Type={content_type or None}")
        if not response.content:
            raise ValueError("下载到的封面为空")
        target = cover_object_name(content_id)
        with tempfile.SpooledTemporaryFile(max_size=self._spool_max_size, mode="w+b") as stream:
            stream.write(response.content)
            stream.seek(0)
            await self._upload(
                target, stream, len(response.content), content_type, bucket=platform
            )
        return VideoDownloadResult(target, len(response.content), content_type)

    async def download_with_ytdlp(
        self, url: str, platform: str, content_id: str
    ) -> tuple[VideoDownloadResult, VideoDownloadResult, VideoDownloadResult]:
        """使用 yt-dlp 下载视频、独立音频与站点提供的缩略图。"""
        if self._cover_bucket is None:
            raise ValueError("cover bucket is not configured")
        if self._audio_bucket is None:
            raise ValueError("audio bucket is not configured")

        with tempfile.TemporaryDirectory() as temp_dir:
            downloaded = await self._ytdlp_client.download(url, Path(temp_dir))
            video_path = downloaded.video_path
            audio_path = downloaded.audio_path
            image_path = downloaded.cover_path
            video_type = derive_content_type(
                mimetypes.guess_type(video_path.name)[0], video_path.suffix
            )
            image_type = derive_image_content_type(image_path)
            video_target = derive_object_name(
                platform, content_id, video_path.as_uri(), video_type
            )
            cover_target = cover_object_name(content_id)
            audio_target = audio_object_stem(content_id)
            with video_path.open("rb") as stream:
                video_size = video_path.stat().st_size
                await self._upload(
                    video_target, stream, video_size, video_type, bucket=platform
                )
            with image_path.open("rb") as stream:
                image_size = image_path.stat().st_size
                await self._upload(
                    cover_target, stream, image_size, image_type,
                    bucket=platform,
                )
            with audio_path.open("rb") as stream:
                audio_size = audio_path.stat().st_size
                audio_type = derive_audio_content_type(audio_path)
                await self._upload(
                    audio_target, stream, audio_size, audio_type,
                    bucket=platform,
                )
        return (
            VideoDownloadResult(video_target, video_size, video_type),
            VideoDownloadResult(audio_target, audio_size, audio_type),
            VideoDownloadResult(cover_target, image_size, image_type),
        )

    async def _upload(
        self, object_name: str, stream: Any, size: int, content_type: str,
        *, bucket: str | None = None,
    ) -> None:
        target_bucket = bucket or self._bucket
        if target_bucket not in self._ready_buckets:
            async_make_bucket = getattr(self._minio, "amake_bucket", None)
            is_async = getattr(self._minio, "is_async", None)
            if async_make_bucket is not None and is_async is not False:
                await async_make_bucket(target_bucket)
            else:
                await asyncio.to_thread(self._minio.make_bucket, target_bucket)
            self._ready_buckets.add(target_bucket)
        args = (target_bucket, object_name, stream, size)
        kwargs = {"content_type": content_type}
        async_upload = getattr(self._minio, "aput_object", None)
        is_async = getattr(self._minio, "is_async", None)
        if async_upload is not None and (
            is_async is True
            or (is_async is None and inspect.iscoroutinefunction(async_upload))
        ):
            await async_upload(*args, **kwargs)
            return
        await asyncio.to_thread(self._minio.put_object, *args, **kwargs)
