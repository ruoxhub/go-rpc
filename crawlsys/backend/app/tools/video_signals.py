"""Deterministic FFmpeg-based signals for short-video analysis."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from models.results import AudioSignals, SceneBoundary, VideoSignals


def _run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def parse_scene_timestamps(
    stderr: str,
    duration: float,
    min_scene_length: float = 0.5,
) -> list[SceneBoundary]:
    change_points = [0.0]
    for match in re.finditer(r"pts_time:(\d+(?:\.\d+)?)", stderr):
        timestamp = min(float(match.group(1)), duration)
        if timestamp - change_points[-1] >= min_scene_length:
            change_points.append(timestamp)
    if duration - change_points[-1] < min_scene_length and len(change_points) > 1:
        change_points.pop()
    change_points.append(duration)
    return [
        SceneBoundary(round(start, 3), round(end, 3))
        for start, end in zip(change_points, change_points[1:])
    ]


def detect_scenes(
    video_path: Path,
    ffmpeg: str,
    duration: float,
    threshold: float = 0.3,
    min_scene_length: float = 0.5,
) -> list[SceneBoundary]:
    result = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-vf",
            f"select='gt(scene,{threshold})',showinfo",
            "-f",
            "null",
            "-",
        ]
    )
    return parse_scene_timestamps(result.stderr, duration, min_scene_length)


def parse_audio_energy(stderr: str, threshold_lufs: float = -40.0) -> AudioSignals | None:
    pattern = re.compile(r"t:\s*([\d.]+)\s+.*?M:\s*(-?[\d.]+)")
    per_second: dict[int, list[float]] = {}
    for match in pattern.finditer(stderr):
        second = int(float(match.group(1)))
        loudness = float(match.group(2))
        if loudness > -120:
            per_second.setdefault(second, []).append(loudness)
    if not per_second:
        return None

    averages = {
        second: sum(values) / len(values) for second, values in per_second.items()
    }
    active = [second for second, value in averages.items() if value > threshold_lufs]
    peak_second, peak_loudness = max(averages.items(), key=lambda item: item[1])
    return AudioSignals(
        active_seconds=len(active),
        quiet_intro_seconds=float(min(active)) if active else 0.0,
        peak_loudness_at_seconds=float(peak_second),
        peak_loudness_lufs=round(peak_loudness, 1),
    )


def analyze_audio(video_path: Path, ffmpeg: str) -> AudioSignals | None:
    result = _run(
        [
            ffmpeg,
            "-hide_banner",
            "-i",
            str(video_path),
            "-af",
            "ebur128",
            "-f",
            "null",
            "-",
        ]
    )
    return parse_audio_energy(result.stderr)


def analyze_video_signals(
    video_path: Path,
    ffmpeg: str,
    duration: float,
    has_audio: bool,
) -> VideoSignals:
    scenes = detect_scenes(video_path, ffmpeg, duration)
    shot_count = len(scenes)
    return VideoSignals(
        scenes=scenes,
        average_shot_duration=round(duration / shot_count, 3),
        cut_frequency=round(max(0, shot_count - 1) / duration, 3),
        audio=analyze_audio(video_path, ffmpeg) if has_audio else None,
    )


def format_signals_evidence(signals: VideoSignals) -> str:
    return json.dumps(signals.to_dict(), ensure_ascii=False)
