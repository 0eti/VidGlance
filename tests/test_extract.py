from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from PIL import Image, ImageChops, ImageStat

from vidglance import extract, ffmpeg
from vidglance.extract import extract_frames, plan_times
from vidglance.formatting import format_duration

# --- plan_times ---


def test_plan_times_reference() -> None:
    # 레퍼런스 시트: 2:41:57, 4×5 → 00:07:42 … 02:34:15.
    # 두 끝이 모두 맞으려면 D ∈ [9717.75, 9718.8) — 초 아래 값이 .9 근처인 영상이다.
    plan = plan_times(9717.9, 20)
    stamps = [format_duration(t) for t in plan.times]
    assert len(stamps) == 20
    assert stamps[0] == "00:07:42"
    assert stamps[1] == "00:15:25"
    assert stamps[-1] == "02:34:15"
    assert plan.warnings == []


def test_plan_times_even_spacing_excludes_ends() -> None:
    assert plan_times(100, 4).times == pytest.approx([20, 40, 60, 80])


def test_plan_times_with_skip() -> None:
    plan = plan_times(100, 4, skip_start=10, skip_end=10)
    assert plan.times == pytest.approx([26, 42, 58, 74])
    assert plan.warnings == []


def test_plan_times_skip_too_long_is_ignored() -> None:
    # 4칸이면 최소 0.4초 필요: 1초 남으면 스킵 유지, 0.3초 남으면 무시

    assert plan_times(10, 4, skip_start=4, skip_end=5).warnings == []
    plan = plan_times(10, 4, skip_start=5, skip_end=4.7)
    assert plan.times == pytest.approx([2, 4, 6, 8])
    assert "무시" in plan.warnings[0]


def test_plan_times_skip_beyond_duration_is_ignored() -> None:
    plan = plan_times(10, 4, skip_start=30)
    assert plan.times == pytest.approx([2, 4, 6, 8])
    assert len(plan.warnings) == 1


def test_plan_times_very_short() -> None:
    plan = plan_times(1.0, 20)
    assert plan.times == pytest.approx([0.1 * i for i in range(1, 10)])
    assert plan.warnings == ["영상이 짧아 20칸 중 9칸만 채웁니다"]


def test_plan_times_exactly_min_length_is_full() -> None:
    plan = plan_times(2.0, 20)
    assert len(plan.times) == 20
    assert plan.warnings == []


def test_plan_times_tiny_video_gets_one_frame() -> None:
    plan = plan_times(0.15, 20)
    assert plan.times == pytest.approx([0.075])


# --- 실제 추출 ---


@pytest.fixture(scope="module")
def ffmpeg_path(tools: ffmpeg.Tools) -> Path:
    return tools.ffmpeg


def _reference(
    ffmpeg_path: Path, video: Path, t: float, size: tuple[int, int], out: Path
) -> Image.Image:
    """ffmpeg CLI로 처음부터 디코딩해 얻은 t초 프레임 (autorotate·칸 크기 축소 포함)."""
    w, h = size
    cmd = [
        ffmpeg_path, "-v", "error", "-y", "-i", video, "-ss", f"{t:.3f}",
        "-frames:v", "1", "-vf", f"scale={w}:{h}:flags=bicubic,setsar=1", out,
    ]  # fmt: skip
    assert ffmpeg.run(cmd).returncode == 0
    with Image.open(out) as img:
        return img.convert("RGB")


# 같은 프레임이면 0~4.4(회전은 축소·회전 순서 차이로 경계가 약간 다름),
# 1프레임만 어긋나도 7.4 이상이다 (testsrc2 측정값)
SAME_FRAME = 6


def _mean_diff(a: Image.Image, b: Image.Image) -> float:
    assert a.size == b.size
    return max(ImageStat.Stat(ImageChops.difference(a, b)).mean)


def test_extract_20_frames(media: Callable[[str], Path]) -> None:
    times = plan_times(60, 20).times
    result = extract_frames(media("기본_1080p30.mp4"), times, (240, 135))

    assert [f.time for f in result.frames] == times
    assert all(
        f.image is not None and f.image.size == (240, 135) for f in result.frames
    )
    assert result.warnings == []
    assert 0 < result.open_seconds <= result.seconds
    assert len(result.frame_seconds) == 20


@pytest.mark.parametrize(
    ("name", "t", "size"),
    [
        ("무음.mp4", 4.0, (320, 240)),
        ("무음.mp4", 7.3, (160, 120)),
        ("조각난.mp4", 2.5, (320, 180)),
        ("조각난.mp4", 17.7, (320, 180)),
        ("조각난.mp4", 29.0, (320, 180)),
        ("애너모픽.mp4", 5.0, (320, 180)),  # SAR 4:3 → 16:9로 보정
        ("회전90.mp4", 2.0, (180, 320)),  # display matrix 90° → 세로
    ],
)
def test_extract_matches_ffmpeg_decode(
    name: str,
    t: float,
    size: tuple[int, int],
    media: Callable[[str], Path],
    ffmpeg_path: Path,
    tmp_path: Path,
) -> None:
    """seek 후 디코딩한 프레임이 ffmpeg가 처음부터 디코딩한 같은 시점 프레임과 같다."""
    video = media(name)
    image = extract_frames(video, [t], size).frames[0].image
    assert image is not None and image.size == size
    reference = _reference(ffmpeg_path, video, t, size, tmp_path / "ref.png")
    assert _mean_diff(image, reference) < SAME_FRAME


def test_extract_opens_file_once(
    media: Callable[[str], Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """회귀: fragmented MP4는 열 때마다 조각 전체를 해석하므로 영상당 한 번만 연다."""
    opened: list[str] = []
    real_open = extract.av.open

    def counting_open(*args: Any, **kwargs: Any) -> Any:
        opened.append(str(args[0]))
        return real_open(*args, **kwargs)

    monkeypatch.setattr(extract.av, "open", counting_open)
    times = plan_times(30, 20).times
    result = extract_frames(media("조각난.mp4"), times, (160, 90))

    assert len(opened) == 1
    assert all(f.image is not None for f in result.frames)


def test_extract_failure_becomes_none_with_warning(
    media: Callable[[str], Path],
) -> None:
    # 10초 영상의 1000초 지점 → 재시도(999초)도 실패 → 회색 칸
    result = extract_frames(media("무음.mp4"), [5, 1000], (160, 120))
    assert result.frames[0].image is not None
    assert result.frames[1].image is None
    assert result.warnings == ["00:16:40 프레임을 뽑지 못해 회색 칸으로 둡니다"]


def test_extract_retry_one_second_earlier(
    media: Callable[[str], Path], ffmpeg_path: Path, tmp_path: Path
) -> None:
    # 10초 영상의 10.5초 → 실패, 1초 앞(9.5초) 재시도 결과가 들어간다
    video = media("무음.mp4")
    result = extract_frames(video, [10.5], (160, 120))
    image = result.frames[0].image
    assert image is not None
    assert result.warnings == []
    reference = _reference(ffmpeg_path, video, 9.5, (160, 120), tmp_path / "ref.png")
    assert _mean_diff(image, reference) < SAME_FRAME


def test_extract_broken_file(media: Callable[[str], Path]) -> None:
    result = extract_frames(media("깨짐.mp4"), [1, 2], (160, 120))
    assert [f.image for f in result.frames] == [None, None]
    assert len(result.warnings) == 1
    assert "열 수 없어" in result.warnings[0]


def test_extract_special_path(media: Callable[[str], Path]) -> None:
    result = extract_frames(media("공백 과 특수문자 (1)&.mp4"), [2], (160, 120))
    assert result.frames[0].image is not None
