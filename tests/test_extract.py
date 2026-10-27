from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image, ImageChops, ImageStat

from vidglance import ffmpeg
from vidglance.extract import extract_frame, extract_frames, plan_times
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


def test_extract_20_frames(media: Callable[[str], Path], ffmpeg_path: Path) -> None:
    times = plan_times(60, 20).times
    result = extract_frames(ffmpeg_path, media("기본_1080p30.mp4"), times, (240, 135))

    assert [f.time for f in result.frames] == times
    assert all(
        f.image is not None and f.image.size == (240, 135) for f in result.frames
    )
    assert result.warnings == []
    assert result.seconds > 0
    assert len(result.frame_seconds) == 20


def test_extract_matches_accurate_decode(
    media: Callable[[str], Path], ffmpeg_path: Path, tmp_path: Path
) -> None:
    """입력 seek 결과가 처음부터 디코딩해 얻은 같은 시점 프레임과 같다."""
    video = media("무음.mp4")
    image = extract_frame(ffmpeg_path, video, 4.0, (320, 240))
    assert image is not None

    ref_png = tmp_path / "ref.png"
    cmd = [
        ffmpeg_path,
        "-v",
        "error",
        "-i",
        video,
        "-ss",
        "4.0",
        "-frames:v",
        "1",
        ref_png,
    ]
    assert ffmpeg.run(cmd).returncode == 0
    with Image.open(ref_png) as ref:
        diff = ImageChops.difference(image, ref.convert("RGB"))
    assert max(ImageStat.Stat(diff).mean) < 2


def test_extract_anamorphic_uses_display_aspect(
    media: Callable[[str], Path], ffmpeg_path: Path
) -> None:
    image = extract_frame(ffmpeg_path, media("애너모픽.mp4"), 5, (320, 180))
    assert image is not None and image.size == (320, 180)


def test_extract_rotated_is_portrait_content(
    media: Callable[[str], Path], ffmpeg_path: Path
) -> None:
    """autorotate가 적용되면 testsrc2의 세로 색 막대가 가로 줄무늬가 된다."""
    image = extract_frame(ffmpeg_path, media("회전90.mp4"), 2, (180, 320))
    assert image is not None and image.size == (180, 320)
    # 한 행(가로줄) 안의 색은 거의 같고, 한 열(세로줄)을 따라서는 색이 바뀐다
    row = image.crop((20, 160, 160, 161))
    column = image.crop((90, 20, 91, 300))
    assert max(ImageStat.Stat(row).stddev) < max(ImageStat.Stat(column).stddev)


def test_extract_failure_becomes_none_with_warning(
    media: Callable[[str], Path], ffmpeg_path: Path
) -> None:
    # 10초 영상의 1000초 지점 → 재시도(999초)도 실패 → 회색 칸
    result = extract_frames(ffmpeg_path, media("무음.mp4"), [5, 1000], (160, 120))
    assert result.frames[0].image is not None
    assert result.frames[1].image is None
    assert result.warnings == ["00:16:40 프레임을 뽑지 못해 회색 칸으로 둡니다"]


def test_extract_retry_one_second_earlier(
    media: Callable[[str], Path], ffmpeg_path: Path
) -> None:
    # 10초 영상의 10.5초 → 실패, 9.5초 재시도는 성공
    assert extract_frame(ffmpeg_path, media("무음.mp4"), 10.5, (160, 120)) is None
    result = extract_frames(ffmpeg_path, media("무음.mp4"), [10.5], (160, 120))
    assert result.frames[0].image is not None
    assert result.warnings == []


def test_extract_broken_file(media: Callable[[str], Path], ffmpeg_path: Path) -> None:
    result = extract_frames(ffmpeg_path, media("깨짐.mp4"), [1, 2], (160, 120))
    assert [f.image for f in result.frames] == [None, None]
    assert len(result.warnings) == 2


def test_extract_special_path(media: Callable[[str], Path], ffmpeg_path: Path) -> None:
    image = extract_frame(
        ffmpeg_path, media("공백 과 특수문자 (1)&.mp4"), 2, (160, 120)
    )
    assert image is not None
