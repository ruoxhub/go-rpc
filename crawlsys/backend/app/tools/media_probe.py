"""Lightweight media inspection backed by ffprobe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from models.video_analysis_runtime import MediaProbe


def probe_media(path: Path, ffprobe: str) -> MediaProbe:
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=15,
    )
    payload = json.loads(result.stdout)
    media_format = payload.get("format", {})
    streams = payload.get("streams", [])
    audio = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        {},
    )

    def optional_int(value: object) -> int | None:
        return int(value) if value not in (None, "") else None

    return MediaProbe(
        duration_seconds=round(float(media_format.get("duration", 0)), 3),
        format_name=media_format.get("format_name"),
        size_bytes=int(media_format.get("size", path.stat().st_size)),
        bit_rate=optional_int(media_format.get("bit_rate")),
        stream_count=len(streams),
        audio_codec=audio.get("codec_name"),
        audio_sample_rate=optional_int(audio.get("sample_rate")),
        audio_channels=optional_int(audio.get("channels")),
    )
