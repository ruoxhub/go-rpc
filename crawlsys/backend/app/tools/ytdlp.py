"""yt-dlp 媒体下载客户端。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class YtDlpDownload:
    video_path: Path
    audio_path: Path
    cover_path: Path


class YtDlpClient:
    """在线程中运行 yt-dlp。"""

    def __init__(self, *, proxy_url: str | None = None) -> None:
        self._proxy_url = proxy_url or None

    async def download(self, url: str, output_dir: Path) -> YtDlpDownload:
        return await asyncio.to_thread(self._download_sync, url, output_dir)

    def _download_sync(self, url: str, output_dir: Path) -> YtDlpDownload:
        try:
            import yt_dlp
        except ImportError as exc:
            raise RuntimeError("yt-dlp is required") from exc

        output_dir.mkdir(parents=True, exist_ok=True)
        common: dict[str, Any] = {
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "writethumbnail": True,
        }
        if self._proxy_url:
            common["proxy"] = self._proxy_url

        video_template = output_dir / "video.%(ext)s"
        with yt_dlp.YoutubeDL({
            **common,
            "format": "bestvideo+bestaudio/best",
            "merge_output_format": "mp4",
            "outtmpl": str(video_template),
        }) as downloader:
            downloader.extract_info(url, download=True)

        audio_template = output_dir / "audio.%(ext)s"
        with yt_dlp.YoutubeDL({
            **common,
            "writethumbnail": False,
            "format": "bestaudio/best",
            "outtmpl": str(audio_template),
        }) as downloader:
            downloader.extract_info(url, download=True)

        video_path = self._find_media(output_dir, "video", {".jpg", ".jpeg", ".png", ".webp", ".avif"})
        audio_path = self._find_media(output_dir, "audio", set())
        cover_path = self._find_cover(output_dir)
        return YtDlpDownload(video_path, audio_path, cover_path)

    @staticmethod
    def _find_media(output_dir: Path, stem: str, excluded: set[str]) -> Path:
        path = next(
            (item for item in output_dir.glob(f"{stem}.*")
             if item.is_file() and item.suffix.lower() not in excluded),
            None,
        )
        if path is None or path.stat().st_size == 0:
            raise RuntimeError(f"yt-dlp 下载完成但未找到{stem}")
        return path

    @staticmethod
    def _find_cover(output_dir: Path) -> Path:
        path = next(
            (item for item in output_dir.glob("video.*")
             if item.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".avif"}),
            None,
        )
        if path is None or path.stat().st_size == 0:
            raise RuntimeError("yt-dlp 下载完成但未找到封面")
        return path
