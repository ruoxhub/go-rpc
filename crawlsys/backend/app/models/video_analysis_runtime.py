"""Runtime-only DTOs used by the video-analysis workflow."""

import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from .video_analysis import InputMode


@dataclass(frozen=True)
class AnalysisRequest:
    source: str | Path
    model: str = "gpt-4o"
    api_key: str | None = None
    base_url: str | None = None
    request_path: Literal["chat", "responses"] = "chat"
    prompt_file: Path | None = None
    output_path: Path | None = None
    cleanup: bool = True
    review_route: Literal["R", "G"] | None = None

    def __post_init__(self) -> None:
        if self.review_route not in ("R", "G", None):
            raise ValueError("review_route must be 'R', 'G', or None")


@dataclass(frozen=True)
class VideoMetadata:
    duration: float
    width: int
    height: int
    fps: float | None
    has_audio_stream: bool

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}"

    @property
    def aspect_ratio(self) -> str:
        divisor = math.gcd(self.width, self.height)
        return f"{self.width // divisor}:{self.height // divisor}"


@dataclass(frozen=True)
class DownloadedVideo:
    video_path: Path
    platform: str
    title: str
    duration_seconds: float | None
    source_url: str
    audio_path: Path | None = None
    cover_path: Path | None = None


@dataclass(frozen=True)
class MediaProbe:
    duration_seconds: float
    format_name: str | None
    size_bytes: int
    bit_rate: int | None
    stream_count: int
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None


@dataclass(frozen=True)
class SceneBoundary:
    start_seconds: float
    end_seconds: float

    @property
    def duration_seconds(self) -> float:
        return self.end_seconds - self.start_seconds

    def to_dict(self) -> dict[str, float]:
        return {
            "start_seconds": self.start_seconds,
            "end_seconds": self.end_seconds,
            "duration_seconds": self.duration_seconds,
        }


@dataclass(frozen=True)
class AudioSignals:
    active_seconds: int
    quiet_intro_seconds: float
    peak_loudness_at_seconds: float
    peak_loudness_lufs: float

    def to_dict(self) -> dict[str, int | float]:
        return {
            "active_seconds": self.active_seconds,
            "quiet_intro_seconds": self.quiet_intro_seconds,
            "peak_loudness_at_seconds": self.peak_loudness_at_seconds,
            "peak_loudness_lufs": self.peak_loudness_lufs,
        }


@dataclass(frozen=True)
class VideoSignals:
    scenes: list[SceneBoundary]
    average_shot_duration: float
    cut_frequency: float
    audio: AudioSignals | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenes": [scene.to_dict() for scene in self.scenes],
            "average_shot_duration": self.average_shot_duration,
            "cut_frequency": self.cut_frequency,
            "audio": self.audio.to_dict() if self.audio else None,
        }


@dataclass(frozen=True)
class MediaTimeRange:
    start_seconds: float
    end_seconds: float
    start_inclusive: bool = True
    end_inclusive: bool = True


@dataclass(frozen=True)
class MediaCoverage:
    input_mode: InputMode
    sampled_timestamps: tuple[float, ...]
    observed_ranges: tuple[MediaTimeRange, ...]
    unobserved_ranges: tuple[MediaTimeRange, ...]
    limitations: tuple[str, ...]


@dataclass
class AnalysisArtifacts:
    local_video_path: Path
    downloaded: bool
    mime_type: str
    metadata: VideoMetadata | None = None
    media_probe: MediaProbe | None = None
    signals: VideoSignals | None = None
    timestamps: list[float] = field(default_factory=list)
    frames: list[bytes] = field(default_factory=list)
    transcript: str | None = None
    detected_voice: bool | None = None
    evidence_text: str = ""
    content_blocks: list[dict] = field(default_factory=list)
    source_sha256: str = ""
    source_id: str = ""
    coverage: MediaCoverage | None = None


class AnalysisStage(str, Enum):
    RESOLVING_INPUT = "resolving_input"
    PROBING_MEDIA = "probing_media"
    ANALYZING_SIGNALS = "analyzing_signals"
    EXTRACTING_FRAMES = "extracting_frames"
    TRANSCRIBING_AUDIO = "transcribing_audio"
    CALLING_MODEL = "calling_model"
    VALIDATING_RESULT = "validating_result"
    SAVING_RESULT = "saving_result"
    COMPLETED = "completed"


@dataclass(frozen=True)
class ProgressEvent:
    stage: AnalysisStage
    message: str
    attempt: int | None = None


ProgressCallback = Callable[[ProgressEvent], None]


__all__ = [
    "AnalysisArtifacts",
    "AnalysisRequest",
    "AnalysisStage",
    "AudioSignals",
    "DownloadedVideo",
    "MediaCoverage",
    "MediaProbe",
    "MediaTimeRange",
    "ProgressCallback",
    "ProgressEvent",
    "SceneBoundary",
    "VideoMetadata",
    "VideoSignals",
]
