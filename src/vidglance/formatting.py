"""크기·시간·비율·코덱 문자열과 헤더 줄 구성 (spec §6).

헤더 레이블 문자열은 이 모듈의 `LABELS` 한곳에만 둔다.
"""

import math
from typing import TYPE_CHECKING

from vidglance.config import HeaderSettings, Language

if TYPE_CHECKING:
    from vidglance.probe import VideoInfo

LABELS: dict[Language, dict[str, str]] = {
    "en": {
        "file_name": "File Name",
        "size": "Size",
        "bytes": "bytes",
        "resolution": "Resolution",
        "fps": "fps",
        "video_codec": "Video Codec",
        "audio_codec": "Audio Codec",
        "no_audio": "None",
        "duration": "Duration",
    },
    "ko": {
        "file_name": "파일명",
        "size": "크기",
        "bytes": "바이트",
        "resolution": "해상도",
        "fps": "fps",
        "video_codec": "비디오 코덱",
        "audio_codec": "오디오 코덱",
        "no_audio": "없음",
        "duration": "재생 시간",
    },
}

_SIZE_UNITS = ("KB", "MB", "GB")


def format_size(size_bytes: int) -> str:
    """1024 기준, 소수 둘째 자리. 예: 7438762215 → `6.93GB`."""
    value = size_bytes / 1024
    unit = 0
    # 반올림한 값이 1024가 되면 다음 단위로 올린다 (1024.00KB 대신 1.00MB)
    while round(value, 2) >= 1024 and unit < len(_SIZE_UNITS) - 1:
        value /= 1024
        unit += 1
    return f"{value:.2f}{_SIZE_UNITS[unit]}"


def format_duration(seconds: float) -> str:
    """초 → `HH:MM:SS` (초 아래 내림, 100시간 이상이면 시 자리가 늘어남)."""
    total = max(0, math.floor(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def format_fps(fps: float | None) -> str:
    """소수 둘째 자리, 끝자리 0 제거. 예: 59.7700 → `59.77`, 30.0 → `30`."""
    if fps is None:
        return "N/A"
    return f"{fps:.2f}".rstrip("0").rstrip(".")


def format_resolution(width: int, height: int, dar: tuple[int, int]) -> str:
    """예: `1920×1080(16:9)`."""
    return f"{width}×{height}({dar[0]}:{dar[1]})"


def video_codec_label(codec_name: str, codec_tag: str) -> str:
    """codec_tag_string이 의미 있으면 그것을, 아니면 codec_name을 대문자로."""
    if codec_tag and "[" not in codec_tag and codec_tag.isprintable():
        return codec_tag.upper()
    return codec_name.upper()


def audio_codec_label(codec_name: str | None, language: Language) -> str:
    """오디오는 항상 codec_name 대문자. 오디오가 없으면 None/없음."""
    if codec_name is None:
        return LABELS[language]["no_audio"]
    return codec_name.upper()


def header_lines(
    info: "VideoInfo", header: HeaderSettings, language: Language
) -> list[str]:
    """켜진 항목만 모아 표시할 헤더 줄 목록을 만든다. 모두 꺼지면 빈 목록."""
    label = LABELS[language]
    size = format_size(info.size_bytes)
    resolution = format_resolution(info.width, info.height, info.dar)
    video = video_codec_label(info.video_codec_name, info.video_codec_tag)
    audio = audio_codec_label(info.audio_codec_name, language)
    duration = format_duration(info.duration)

    # 줄마다 (켜짐 여부, 문자열) 목록. 같은 줄의 켜진 항목은 ", "로 잇는다.
    rows: list[list[tuple[bool, str]]] = [
        [(header.file_name, f"{label['file_name']}: {info.file_name}")],
        [
            (
                header.size,
                f"{label['size']}: {size} ({info.size_bytes:,} {label['bytes']})",
            )
        ],
        [
            (header.resolution, f"{label['resolution']}: {resolution}"),
            (header.fps, f"{label['fps']}: {format_fps(info.fps)}"),
        ],
        [
            (header.video_codec, f"{label['video_codec']}: {video}"),
            (header.audio_codec, f"{label['audio_codec']}: {audio}"),
        ],
        [(header.duration, f"{label['duration']}: {duration}")],
    ]
    lines = []
    for row in rows:
        parts = [text for enabled, text in row if enabled]
        if parts:
            lines.append(", ".join(parts))
    return lines
