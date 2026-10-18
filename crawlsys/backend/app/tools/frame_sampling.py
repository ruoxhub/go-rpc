"""Deterministic timestamp planning for representative video frames."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from math import isfinite

from common.constants import MAX_ANALYSIS_FRAMES, MIN_FRAME_INTERVAL_SECONDS
from models.results import SceneBoundary


class FrameSamplingStrategy(StrEnum):
    """Supported timestamp planning strategies."""

    INTERVAL = "interval"
    COUNT = "count"
    TIMESTAMPS = "timestamps"
    SCENE_GUIDED = "scene_guided"


@dataclass(frozen=True)
class FrameSamplingOptions:
    """Immutable options shared by all frame-sampling strategies."""

    strategy: FrameSamplingStrategy = FrameSamplingStrategy.SCENE_GUIDED
    max_frames: int = 32
    interval_seconds: float = 5.0
    timestamps: tuple[float, ...] = ()


def _validate(duration: float, options: FrameSamplingOptions) -> None:
    if (
        isinstance(duration, bool)
        or not isinstance(duration, (int, float))
        or not isfinite(duration)
        or duration <= 0
    ):
        raise ValueError("duration must be finite and greater than zero")
    if not isinstance(options.strategy, FrameSamplingStrategy):
        raise ValueError("unsupported frame sampling strategy")
    if (
        isinstance(options.max_frames, bool)
        or not isinstance(options.max_frames, int)
        or not 2 <= options.max_frames <= MAX_ANALYSIS_FRAMES
    ):
        raise ValueError(
            f"max_frames must be an integer between 2 and {MAX_ANALYSIS_FRAMES}"
        )
    if (
        isinstance(options.interval_seconds, bool)
        or not isinstance(options.interval_seconds, (int, float))
        or not isfinite(options.interval_seconds)
        or options.interval_seconds < MIN_FRAME_INTERVAL_SECONDS
    ):
        raise ValueError(
            "interval_seconds must be finite and greater than or equal to "
            f"{MIN_FRAME_INTERVAL_SECONDS}"
        )
    if not isinstance(options.timestamps, (list, tuple)):
        raise ValueError("timestamps must be a list or tuple")
    for timestamp in options.timestamps:
        if (
            isinstance(timestamp, bool)
            or not isinstance(timestamp, (int, float))
            or not isfinite(timestamp)
            or timestamp < 0
        ):
            raise ValueError("timestamps must contain finite non-negative numbers")
    if options.strategy is FrameSamplingStrategy.TIMESTAMPS and not options.timestamps:
        raise ValueError("timestamps strategy requires at least one timestamp")


def _selected_indexes(length: int, maximum: int) -> tuple[int, ...]:
    if length <= maximum:
        return tuple(range(length))
    denominator = maximum - 1
    last_index = length - 1
    indexes = []
    for index in range(maximum):
        quotient, remainder = divmod(index * last_index, denominator)
        if remainder * 2 > denominator or (
            remainder * 2 == denominator and quotient % 2
        ):
            quotient += 1
        indexes.append(quotient)
    return tuple(indexes)


def _normalize(
    candidates: Sequence[float],
    *,
    terminal: float,
    max_frames: int,
) -> tuple[float, ...]:
    values = tuple(
        sorted({round(min(terminal, max(0.0, value)), 3) for value in candidates})
    )
    return tuple(values[index] for index in _selected_indexes(len(values), max_frames))


def _interval_timestamps(
    terminal: float,
    interval: float,
    max_frames: int,
) -> tuple[float, ...]:
    terminal_numerator, terminal_denominator = terminal.as_integer_ratio()
    interval_numerator, interval_denominator = interval.as_integer_ratio()
    regular_count = (
        terminal_numerator * interval_denominator
        // (terminal_denominator * interval_numerator)
        + 1
    )
    regular_last = float(
        Fraction((regular_count - 1) * interval_numerator, interval_denominator)
    )
    includes_terminal = round(regular_last, 3) == round(terminal, 3)
    candidate_count = regular_count if includes_terminal else regular_count + 1
    indexes = _selected_indexes(candidate_count, max_frames)
    candidates = tuple(
        terminal
        if index == candidate_count - 1 and not includes_terminal
        else float(Fraction(index * interval_numerator, interval_denominator))
        for index in indexes
    )
    return _normalize(candidates, terminal=terminal, max_frames=max_frames)


def _count_timestamps(terminal: float, count: int) -> tuple[float, ...]:
    step = terminal / (count - 1)
    return _normalize(
        tuple(index * step for index in range(count)),
        terminal=terminal,
        max_frames=count,
    )


def _scene_guided_candidates(
    scenes: Sequence[SceneBoundary], terminal: float
) -> tuple[float, ...]:
    candidates: list[float] = [0.0, terminal]
    for scene in scenes:
        candidates.append(min(scene.end_seconds, scene.start_seconds + 0.1))
        if scene.duration_seconds > 3:
            candidates.append(scene.start_seconds + scene.duration_seconds / 2)
    return tuple(candidates)


def plan_frame_timestamps(
    *,
    duration: float,
    scenes: Sequence[SceneBoundary],
    options: FrameSamplingOptions,
) -> tuple[float, ...]:
    """Plan bounded, normalized frame timestamps without reading media."""

    _validate(duration, options)
    terminal = max(0.0, duration - 0.001)

    if options.strategy is FrameSamplingStrategy.INTERVAL:
        return _interval_timestamps(
            terminal, options.interval_seconds, options.max_frames
        )
    if options.strategy is FrameSamplingStrategy.COUNT:
        return _count_timestamps(terminal, options.max_frames)
    if options.strategy is FrameSamplingStrategy.TIMESTAMPS:
        candidates = options.timestamps
    elif options.strategy is FrameSamplingStrategy.SCENE_GUIDED:
        candidates = _scene_guided_candidates(scenes, terminal)
    else:
        raise ValueError(f"unsupported frame sampling strategy: {options.strategy}")

    return _normalize(
        candidates,
        terminal=terminal,
        max_frames=options.max_frames,
    )


def scene_guided_timestamps(
    scenes: list[SceneBoundary],
    duration: float,
    max_frames: int,
) -> list[float]:
    """Return scene-guided timestamps through the compatibility interface."""

    return list(
        plan_frame_timestamps(
            duration=duration,
            scenes=scenes,
            options=FrameSamplingOptions(max_frames=max_frames),
        )
    )
