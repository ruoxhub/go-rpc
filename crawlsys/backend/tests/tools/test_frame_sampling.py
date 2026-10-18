"""视频抽帧时间戳规划测试。"""

import pytest

from models.results import SceneBoundary
from tools.frame_sampling import (
    FrameSamplingOptions,
    FrameSamplingStrategy,
    plan_frame_timestamps,
)


def plan(
    strategy: FrameSamplingStrategy,
    *,
    duration: float = 10.0,
    max_frames: int = 32,
    interval: float = 5.0,
    timestamps: tuple[float, ...] = (),
    scenes: tuple[SceneBoundary, ...] = (),
) -> tuple[float, ...]:
    return plan_frame_timestamps(
        duration=duration,
        scenes=scenes,
        options=FrameSamplingOptions(
            strategy=strategy,
            max_frames=max_frames,
            interval_seconds=interval,
            timestamps=timestamps,
        ),
    )


def test_interval_samples_from_start_and_includes_terminal_frame():
    assert plan(FrameSamplingStrategy.INTERVAL, interval=3.0) == (
        0.0,
        3.0,
        6.0,
        9.0,
        9.999,
    )


def test_count_distributes_requested_maximum_across_video():
    assert plan(FrameSamplingStrategy.COUNT, max_frames=4) == (
        0.0,
        3.333,
        6.666,
        9.999,
    )


def test_timestamps_sort_deduplicate_and_clamp_without_adding_endpoints():
    assert plan(
        FrameSamplingStrategy.TIMESTAMPS,
        max_frames=4,
        timestamps=(8.0, 2.0, 2.0, 20.0),
    ) == (2.0, 8.0, 9.999)


def test_scene_guided_preserves_current_boundary_and_midpoint_behavior():
    scenes = (SceneBoundary(0.0, 2.0), SceneBoundary(2.0, 8.0))

    assert plan(FrameSamplingStrategy.SCENE_GUIDED, scenes=scenes) == (
        0.0,
        0.1,
        2.1,
        5.0,
        9.999,
    )


@pytest.mark.parametrize("strategy", list(FrameSamplingStrategy))
def test_every_strategy_honors_global_frame_limit(strategy):
    timestamps = tuple(float(value) for value in range(20))
    scenes = tuple(
        SceneBoundary(float(value), float(value + 1)) for value in range(10)
    )

    result = plan(
        strategy,
        duration=20.0,
        max_frames=4,
        interval=1.0,
        timestamps=timestamps,
        scenes=scenes,
    )

    assert len(result) <= 4
    assert result == tuple(sorted(set(result)))


@pytest.mark.parametrize(
    "overrides",
    [
        {"duration": 0.0},
        {"duration": float("inf")},
        {"duration": "10"},
        {"max_frames": 1},
        {"max_frames": True},
        {"max_frames": 513},
        {"interval": 0.0},
        {"interval": True},
        {"interval": 0.0009},
        {"interval": "1"},
        {"timestamps": (float("nan"),)},
        {"timestamps": (-1.0,)},
        {"timestamps": (True,)},
        {"timestamps": ("1",)},
    ],
)
def test_invalid_sampling_inputs_are_rejected(overrides):
    values = {
        "duration": 10.0,
        "max_frames": 4,
        "interval": 1.0,
        "timestamps": (1.0,),
    }
    values.update(overrides)

    with pytest.raises(ValueError):
        plan(FrameSamplingStrategy.TIMESTAMPS, **values)


def test_interval_handles_largest_finite_duration_without_overflow():
    result = plan(
        FrameSamplingStrategy.INTERVAL,
        duration=float.fromhex("0x1.fffffffffffffp+1023"),
        max_frames=4,
        interval=0.001,
    )

    assert len(result) == 4
    assert result[0] == 0.0
    assert result[-1] == float.fromhex("0x1.fffffffffffffp+1023")


def test_timestamps_strategy_requires_at_least_one_timestamp():
    with pytest.raises(ValueError, match="timestamps"):
        plan(FrameSamplingStrategy.TIMESTAMPS)


def test_strategy_must_be_frame_sampling_enum():
    with pytest.raises(ValueError, match="strategy"):
        plan_frame_timestamps(
            duration=10.0,
            scenes=(),
            options=FrameSamplingOptions(strategy="interval"),  # type: ignore[arg-type]
        )
