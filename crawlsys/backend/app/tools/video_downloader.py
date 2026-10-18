"""Download a single reference video with the optional yt-dlp dependency."""

from __future__ import annotations

import mimetypes
from pathlib import Path
from urllib.parse import urlparse

from httpx import Client, Timeout

from models.results import DownloadedVideo


def is_video_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def detect_platform(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if "tiktok.com" in host:
        return "tiktok"
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "instagram.com" in host:
        return "instagram"
    if "vimeo.com" in host:
        return "vimeo"
    if "twitter.com" in host or host.endswith("x.com"):
        return "twitter"
    return "other"


_EXTENSIONS_BY_TYPE = {
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "video/quicktime": ".mov",
    "video/x-matroska": ".mkv",
    "video/mpeg": ".mpeg",
    "video/mp2t": ".ts",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/flac": ".flac",
    "audio/webm": ".webm",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


def _sniff_extension(expected_kind: str, header: bytes) -> str | None:
    if expected_kind == "image":
        if header.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if header.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
            return ".webp"
        if header[4:12] in {b"ftypavif", b"ftypavis"}:
            return ".avif"
        return None
    if expected_kind == "audio":
        if header.startswith(b"ID3") or (
            len(header) >= 2
            and header[0] == 0xFF
            and header[1] & 0xE0 == 0xE0
        ):
            return ".mp3"
        if header.startswith(b"OggS"):
            return ".ogg"
        if header.startswith(b"fLaC"):
            return ".flac"
        if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
            return ".wav"
        if header[4:8] == b"ftyp":
            return ".m4a"
        if header.startswith(b"\x1aE\xdf\xa3"):
            return ".webm"
        return None
    if header[4:8] == b"ftyp":
        return ".mp4"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return ".webm"
    return None


def _resolve_extension(expected_kind: str, content_type: str | None, header: bytes) -> str:
    kind_label = {"video": "视频", "audio": "音频", "image": "图片"}[expected_kind]
    normalized = (content_type or "").split(";", 1)[0].strip().lower()
    if (
        normalized.startswith("text/")
        or normalized in {"application/json", "application/xml"}
        or normalized.endswith(("+json", "+xml"))
    ):
        raise RuntimeError(f"下载响应不是有效{kind_label}")
    if normalized.startswith(f"{expected_kind}/"):
        extension = _EXTENSIONS_BY_TYPE.get(normalized) or mimetypes.guess_extension(normalized)
        if extension:
            return ".jpg" if extension == ".jpe" else extension
    if expected_kind == "audio" and normalized == "video/mp4":
        extension = _sniff_extension(expected_kind, header)
        if extension is not None:
            return extension
    if normalized and normalized != "application/octet-stream":
        raise RuntimeError(f"下载响应不是有效{kind_label}")
    extension = _sniff_extension(expected_kind, header)
    if extension is None:
        raise RuntimeError(f"下载响应不是有效{kind_label}")
    return extension


def download_media(
    output_dir: Path,
    max_height: int = 720,
    max_duration_seconds: int = 600,
    *,
    content_id: str = "",
    video_url: str = "",
    music_url: str = "",
    pic_url: str = "",
    proxy_url: str = "",
) -> DownloadedVideo:
    output_dir.mkdir(parents=True, exist_ok=True)
    if not video_url:
        raise ValueError("video_url 不能为空")

    media_id = content_id or "media"
    video_path: Path | None = None
    audio_path: Path | None = None
    cover_path: Path | None = None
    targets = [
        ("视频", "video", video_url),
        ("音频", "audio", music_url),
        ("封面", "image", pic_url),
    ]
    created_paths: list[Path] = []
    try:
        with Client(
            proxy=proxy_url or None,
            trust_env=False,
            follow_redirects=True,
            timeout=Timeout(connect=10.0, read=300.0, write=10.0, pool=10.0),
            headers={"User-Agent": "Mozilla/5.0 (compatible; crawler-v1/1.0)"},
        ) as client:
            for label, expected_kind, url in targets:
                if not url:
                    continue
                temporary = output_dir / f".{media_id}-{expected_kind}.part"
                with client.stream("GET", url) as response:
                    response.raise_for_status()
                    content_type = getattr(response, "headers", {}).get("content-type")
                    with temporary.open("wb") as file:
                        for chunk in response.iter_bytes(chunk_size=1 << 16):
                            file.write(chunk)
                if temporary.stat().st_size == 0:
                    temporary.unlink()
                    raise RuntimeError(f"下载完成但输出{label}为空。")
                with temporary.open("rb") as file:
                    header = file.read(32)
                try:
                    extension = _resolve_extension(expected_kind, content_type, header)
                except RuntimeError as error:
                    host = urlparse(url).hostname or "unknown"
                    normalized_type = (content_type or "missing").split(";", 1)[0]
                    raise RuntimeError(
                        f"{error}; host={host}; content_type={normalized_type}; "
                        f"signature={header[:12].hex()}"
                    ) from None
                target = output_dir / f"{media_id}{extension}"
                if target in created_paths:
                    target = output_dir / f"{media_id}.{expected_kind}{extension}"
                temporary.replace(target)
                created_paths.append(target)
                if expected_kind == "video":
                    video_path = target
                elif expected_kind == "audio":
                    audio_path = target
                else:
                    cover_path = target
    except Exception:
        for path in created_paths:
            path.unlink(missing_ok=True)
        for path in output_dir.glob(f".{media_id}-*.part"):
            path.unlink(missing_ok=True)
        raise

    if video_path is None:
        raise RuntimeError("下载完成但未生成视频文件。")

    return DownloadedVideo(
        video_path=video_path.resolve(),
        platform=detect_platform(video_url),
        title=content_id or video_path.stem,
        duration_seconds=None,
        source_url=video_url,
        audio_path=audio_path.resolve() if audio_path else None,
        cover_path=cover_path.resolve() if cover_path else None,
    )


def download_video(
    url: str,
    output_dir: Path,
    max_height: int = 720,
    max_duration_seconds: int = 600,
    *,
    content_id: str = "",
    media_url: str = "",
    proxy_url: str = "",
) -> DownloadedVideo:
    """兼容旧调用；直链下载统一委托给 download_media。"""
    if media_url:
        result = download_media(
            output_dir,
            content_id=content_id,
            video_url=media_url,
            proxy_url=proxy_url,
        )
        return DownloadedVideo(
            video_path=result.video_path,
            platform=detect_platform(url),
            title=result.title,
            duration_seconds=result.duration_seconds,
            source_url=url,
        )

    try:
        import yt_dlp
    except ImportError as error:
        raise RuntimeError(
            "分析 URL 需要可选依赖 yt-dlp，请运行 pip install yt-dlp。"
        ) from error

    options = {
        "format": (
            f"bestvideo[height<={max_height}]+bestaudio/"
            f"best[height<={max_height}]/best"
        ),
        "merge_output_format": "mp4",
        "outtmpl": str(output_dir / "%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if proxy_url:
        options["proxy"] = proxy_url
    with yt_dlp.YoutubeDL(options) as downloader:
        info = downloader.extract_info(url, download=False)
        if not info:
            raise RuntimeError("yt-dlp 未能读取视频信息。")
        duration = info.get("duration")
        if duration and float(duration) > max_duration_seconds:
            raise RuntimeError(
                f"视频时长 {duration}s 超过限制 {max_duration_seconds}s。"
            )
        info = downloader.extract_info(url, download=True)
        prepared_path = Path(downloader.prepare_filename(info))

    candidates = [
        prepared_path.with_suffix(".mp4"),
        prepared_path,
        *output_dir.glob(f"{info.get('id', '')}.*"),
    ]
    video_path = next((path for path in candidates if path.is_file()), None)
    if video_path is None:
        raise RuntimeError("下载完成但未找到输出视频。")
    return DownloadedVideo(
        video_path=video_path.resolve(),
        platform=detect_platform(url),
        title=str(info.get("title") or video_path.stem),
        duration_seconds=float(duration) if duration else None,
        source_url=url,
    )
