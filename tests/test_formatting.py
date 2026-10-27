from dataclasses import replace
from pathlib import Path

import pytest

from vidglance import formatting as fmt
from vidglance.config import HeaderSettings
from vidglance.probe import VideoInfo

# 레퍼런스 시트의 영상 (Intent.md)
REFERENCE = VideoInfo(
    path=Path("예시영상.mp4"),
    file_name="예시영상.mp4",
    size_bytes=7_438_762_215,
    width=1920,
    height=1080,
    dar=(16, 9),
    fps=59.77,
    video_codec_name="h264",
    video_codec_tag="avc1",
    audio_codec_name="aac",
    duration=9717.4,
)


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0.00KB"),
        (512, "0.50KB"),
        (1024, "1.00KB"),
        (1024 * 1023, "1023.00KB"),
        (1024**2 - 1, "1.00MB"),  # 1023.999KB → 반올림하면 1024 → MB로 올림
        (1024**2, "1.00MB"),
        (1024**3 - 1, "1.00GB"),
        (7_438_762_215, "6.93GB"),
        (1500 * 1024**3, "1500.00GB"),
    ],
)
def test_format_size(size: int, expected: str) -> None:
    assert fmt.format_size(size) == expected


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "00:00:00"),
        (-1, "00:00:00"),
        (59.999, "00:00:59"),
        (60, "00:01:00"),
        (3599.9, "00:59:59"),
        (9717.9, "02:41:57"),
        (360_000, "100:00:00"),
    ],
)
def test_format_duration(seconds: float, expected: str) -> None:
    assert fmt.format_duration(seconds) == expected


@pytest.mark.parametrize(
    ("fps", "expected"),
    [
        (59.77, "59.77"),
        (30.0, "30"),
        (30000 / 1001, "29.97"),
        (24000 / 1001, "23.98"),
        (25.5, "25.5"),
        (25.001, "25"),
        (None, "N/A"),
    ],
)
def test_format_fps(fps: float | None, expected: str) -> None:
    assert fmt.format_fps(fps) == expected


def test_format_resolution() -> None:
    assert fmt.format_resolution(1920, 1080, (16, 9)) == "1920×1080(16:9)"


@pytest.mark.parametrize(
    ("name", "tag", "expected"),
    [
        ("h264", "avc1", "AVC1"),
        ("hevc", "hvc1", "HVC1"),
        ("h264", "[0][0][0][0]", "H264"),  # mkv
        ("h264", "[27][0][0][0]", "H264"),  # mpeg-ts
        ("vp9", "", "VP9"),
    ],
)
def test_video_codec_label(name: str, tag: str, expected: str) -> None:
    assert fmt.video_codec_label(name, tag) == expected


def test_audio_codec_label() -> None:
    assert fmt.audio_codec_label("aac", "en") == "AAC"
    assert fmt.audio_codec_label(None, "en") == "None"
    assert fmt.audio_codec_label(None, "ko") == "없음"


def test_header_lines_reference_en() -> None:
    assert fmt.header_lines(REFERENCE, HeaderSettings(), "en") == [
        "File Name: 예시영상.mp4",
        "Size: 6.93GB (7,438,762,215 bytes)",
        "Resolution: 1920×1080(16:9), fps: 59.77",
        "Video Codec: AVC1, Audio Codec: AAC",
        "Duration: 02:41:57",
    ]


def test_header_lines_reference_ko() -> None:
    assert fmt.header_lines(REFERENCE, HeaderSettings(), "ko") == [
        "파일명: 예시영상.mp4",
        "크기: 6.93GB (7,438,762,215 바이트)",
        "해상도: 1920×1080(16:9), fps: 59.77",
        "비디오 코덱: AVC1, 오디오 코덱: AAC",
        "재생 시간: 02:41:57",
    ]


def test_header_lines_no_audio() -> None:
    silent = replace(REFERENCE, audio_codec_name=None)
    assert fmt.header_lines(silent, HeaderSettings(), "en")[3] == (
        "Video Codec: AVC1, Audio Codec: None"
    )
    assert fmt.header_lines(silent, HeaderSettings(), "ko")[3] == (
        "비디오 코덱: AVC1, 오디오 코덱: 없음"
    )


ALL_OFF = HeaderSettings(
    file_name=False,
    size=False,
    resolution=False,
    fps=False,
    video_codec=False,
    audio_codec=False,
    duration=False,
)


@pytest.mark.parametrize(
    ("enabled", "expected"),
    [
        # 같은 줄에서 하나만 켜면 그 항목만
        ({"fps": True}, ["fps: 59.77"]),
        ({"resolution": True}, ["Resolution: 1920×1080(16:9)"]),
        ({"video_codec": True}, ["Video Codec: AVC1"]),
        ({"audio_codec": True}, ["Audio Codec: AAC"]),
        # 꺼진 줄은 빠지고 아래 줄이 당겨진다
        (
            {"file_name": True, "duration": True},
            ["File Name: 예시영상.mp4", "Duration: 02:41:57"],
        ),
        (
            {"size": True, "fps": True, "audio_codec": True},
            ["Size: 6.93GB (7,438,762,215 bytes)", "fps: 59.77", "Audio Codec: AAC"],
        ),
        # 전부 꺼지면 빈 목록 (헤더 영역 없음)
        ({}, []),
    ],
)
def test_header_lines_combinations(
    enabled: dict[str, bool], expected: list[str]
) -> None:
    header = replace(ALL_OFF, **enabled)
    assert fmt.header_lines(REFERENCE, header, "en") == expected


def test_header_lines_one_line_off_keeps_others() -> None:
    header = HeaderSettings(resolution=False, fps=False)
    lines = fmt.header_lines(REFERENCE, header, "en")
    assert lines == [
        "File Name: 예시영상.mp4",
        "Size: 6.93GB (7,438,762,215 bytes)",
        "Video Codec: AVC1, Audio Codec: AAC",
        "Duration: 02:41:57",
    ]
