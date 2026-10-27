from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from vidglance import ffmpeg
from vidglance.config import HeaderSettings
from vidglance.formatting import header_lines
from vidglance.probe import ProbeError, VideoInfo, parse, probe

# 테스트 영상별 기대값 (ffprobe JSON에서 확인한 값)
# 이름: (가로, 세로, DAR, fps, 비디오 코덱 표기, 오디오 코덱, 재생 시간)
EXPECTED: dict[str, tuple[int, int, tuple[int, int], str, str, str, str]] = {
    "기본_1080p30.mp4": (1920, 1080, (16, 9), "30", "AVC1", "AAC", "00:01:00"),
    "무음.mp4": (320, 240, (4, 3), "25", "AVC1", "None", "00:00:10"),
    "세로_720x1280.mp4": (720, 1280, (9, 16), "30", "AVC1", "AAC", "00:00:10"),
    "회전90.mp4": (360, 640, (9, 16), "25", "AVC1", "AAC", "00:00:05"),
    "짧음_1초.mp4": (320, 240, (4, 3), "30", "AVC1", "AAC", "00:00:01"),
    # mkv는 avg_frame_rate가 명목값이고 tag가 없어 codec_name을 쓴다 (spec §6)
    "가변프레임.mkv": (320, 240, (4, 3), "30", "H264", "AAC", "00:00:10"),
    "애너모픽.mp4": (640, 480, (16, 9), "25", "AVC1", "AAC", "00:00:10"),
    "공백 과 특수문자 (1)&.mp4": (320, 240, (4, 3), "25", "AVC1", "AAC", "00:00:05"),
}


@pytest.fixture(scope="module")
def ffprobe(tools: ffmpeg.Tools) -> Path:
    return tools.ffprobe


@pytest.mark.parametrize("name", list(EXPECTED))
def test_probe_media(name: str, media: Callable[[str], Path], ffprobe: Path) -> None:
    width, height, dar, fps, vcodec, acodec, duration = EXPECTED[name]
    path = media(name)
    info = probe(path, ffprobe)

    assert info.file_name == name
    assert info.size_bytes == path.stat().st_size
    assert (info.width, info.height, info.dar) == (width, height, dar)

    lines = header_lines(info, HeaderSettings(), "en")
    assert lines[0] == f"File Name: {name}"
    assert lines[1].endswith(f"({info.size_bytes:,} bytes)")
    assert lines[2] == f"Resolution: {width}×{height}({dar[0]}:{dar[1]}), fps: {fps}"
    assert lines[3] == f"Video Codec: {vcodec}, Audio Codec: {acodec}"
    assert lines[4] == f"Duration: {duration}"


def test_probe_anamorphic_aspect(media: Callable[[str], Path], ffprobe: Path) -> None:
    info = probe(media("애너모픽.mp4"), ffprobe)
    assert info.aspect == pytest.approx(16 / 9)


def test_probe_broken_file(media: Callable[[str], Path], ffprobe: Path) -> None:
    with pytest.raises(ProbeError, match="영상을 읽을 수 없음"):
        probe(media("깨짐.mp4"), ffprobe)


def test_probe_not_a_video(tmp_path: Path, ffprobe: Path) -> None:
    text = tmp_path / "메모.txt"
    text.write_text("영상 아님", encoding="utf-8")
    with pytest.raises(ProbeError):
        probe(text, ffprobe)


# --- parse(): ffprobe JSON 경계 케이스 ---


def _video(**overrides: Any) -> dict[str, Any]:
    stream: dict[str, Any] = {
        "codec_type": "video",
        "codec_name": "h264",
        "codec_tag_string": "avc1",
        "width": 1920,
        "height": 1080,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "avg_frame_rate": "60000/1001",
        "r_frame_rate": "60000/1001",
    }
    stream.update(overrides)
    return stream


def _parse(*streams: dict[str, Any], duration: str | None = "100.5") -> VideoInfo:
    fmt = {"duration": duration} if duration else {}
    return parse(Path("a.mp4"), 1, {"streams": list(streams), "format": fmt})


def test_parse_basic() -> None:
    info = _parse(_video(), {"codec_type": "audio", "codec_name": "aac"})
    assert info.fps == pytest.approx(59.94, abs=0.01)
    assert info.audio_codec_name == "aac"
    assert info.duration == 100.5


def test_parse_skips_attached_pic() -> None:
    cover = _video(
        codec_name="mjpeg", width=500, height=500, disposition={"attached_pic": 1}
    )
    info = _parse(cover, _video())
    assert info.video_codec_name == "h264"
    assert (info.width, info.height) == (1920, 1080)


def test_parse_only_attached_pic_is_not_video() -> None:
    cover = _video(codec_name="mjpeg", disposition={"attached_pic": 1})
    with pytest.raises(ProbeError, match="비디오 스트림 없음"):
        _parse(cover, {"codec_type": "audio", "codec_name": "mp3"})


@pytest.mark.parametrize("rotation", [90, -90, 270])
def test_parse_rotation_side_data(rotation: int) -> None:
    info = _parse(_video(side_data_list=[{"rotation": rotation}]))
    assert (info.width, info.height, info.dar) == (1080, 1920, (9, 16))


def test_parse_rotation_180_keeps_size() -> None:
    info = _parse(_video(side_data_list=[{"rotation": 180}]))
    assert (info.width, info.height) == (1920, 1080)


def test_parse_rotation_legacy_tag() -> None:
    info = _parse(_video(tags={"rotate": "90"}))
    assert (info.width, info.height) == (1080, 1920)


@pytest.mark.parametrize("dar", [None, "0:1", "N/A"])
def test_parse_dar_fallback_gcd(dar: str | None) -> None:
    info = _parse(_video(display_aspect_ratio=dar, width=1366, height=768))
    assert info.dar == (683, 384)


def test_parse_dar_fallback_uses_sar() -> None:
    info = _parse(
        _video(
            display_aspect_ratio=None, sample_aspect_ratio="4:3", width=640, height=480
        )
    )
    assert info.dar == (16, 9)


def test_parse_fps_fallback() -> None:
    assert _parse(_video(avg_frame_rate="0/0", r_frame_rate="25/1")).fps == 25
    assert _parse(_video(avg_frame_rate="0/0", r_frame_rate="0/0")).fps is None


def test_parse_duration_fallback_to_stream() -> None:
    info = _parse(_video(duration="42.0"), duration=None)
    assert info.duration == 42.0


def test_parse_no_duration() -> None:
    with pytest.raises(ProbeError, match="길이를 알 수 없음"):
        _parse(_video(), duration=None)


def test_parse_no_video() -> None:
    with pytest.raises(ProbeError, match="비디오 스트림 없음"):
        _parse({"codec_type": "audio", "codec_name": "aac"})
