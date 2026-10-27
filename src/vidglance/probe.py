"""ffprobe → VideoInfo(dataclass)."""

import json
import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from vidglance import ffmpeg


class ProbeError(Exception):
    """영상 정보를 읽지 못했다. 메시지는 사용자에게 그대로 보여준다."""


@dataclass(frozen=True)
class VideoInfo:
    """헤더와 레이아웃에 쓰는 영상 정보. 해상도·비율은 회전을 적용한 값이다."""

    path: Path
    file_name: str
    size_bytes: int
    width: int
    height: int
    dar: tuple[int, int]
    fps: float | None
    video_codec_name: str
    video_codec_tag: str
    audio_codec_name: str | None
    duration: float

    @property
    def aspect(self) -> float:
        """표시 비율(가로/세로). 애너모픽 보정이 반영된 값."""
        return self.dar[0] / self.dar[1]


def _ratio(text: str | None) -> tuple[int, int] | None:
    """`16:9` 같은 문자열 → (16, 9). 없거나 0이 들어 있으면 None."""
    if not text or ":" not in text:
        return None
    try:
        num, den = (int(x) for x in text.split(":", 1))
    except ValueError:
        return None
    if num <= 0 or den <= 0:
        return None
    return num, den


def _reduce(num: int, den: int) -> tuple[int, int]:
    g = math.gcd(num, den)
    return num // g, den // g


def _rate(text: str | None) -> float | None:
    """`30000/1001` → 29.97. `0/0`이나 잘못된 값이면 None."""
    if not text:
        return None
    try:
        value = Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None
    return float(value) if value > 0 else None


def _float(text: Any) -> float | None:
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def _rotation(stream: dict[str, Any]) -> int:
    """회전 각도(도). 최신 ffprobe는 side_data의 Display Matrix, 예전 파일은 tags.rotate."""
    for side in stream.get("side_data_list", []):
        if "rotation" in side:
            return int(float(side["rotation"]))
    rotate = stream.get("tags", {}).get("rotate")
    return int(float(rotate)) if rotate else 0


def _first_video(streams: list[dict[str, Any]]) -> dict[str, Any] | None:
    # 앨범 아트(attached_pic)도 video 스트림으로 나오므로 제외한다
    for s in streams:
        if s.get("codec_type") == "video" and not s.get("disposition", {}).get(
            "attached_pic"
        ):
            return s
    return None


def parse(path: Path, size_bytes: int, data: dict[str, Any]) -> VideoInfo:
    """ffprobe JSON(`-show_format -show_streams`)을 VideoInfo로 바꾼다."""
    streams: list[dict[str, Any]] = data.get("streams", [])
    video = _first_video(streams)
    if video is None:
        raise ProbeError("비디오 스트림 없음")
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    width, height = int(video.get("width", 0)), int(video.get("height", 0))
    if width <= 0 or height <= 0:
        raise ProbeError("해상도를 알 수 없음")

    dar = _ratio(video.get("display_aspect_ratio"))
    if dar is None:
        sar = _ratio(video.get("sample_aspect_ratio")) or (1, 1)
        dar = _reduce(width * sar[0], height * sar[1])

    if abs(_rotation(video)) % 180 == 90:
        width, height = height, width
        dar = (dar[1], dar[0])

    duration = _float(data.get("format", {}).get("duration")) or _float(
        video.get("duration")
    )
    if duration is None:
        raise ProbeError("길이를 알 수 없음")

    return VideoInfo(
        path=path,
        file_name=path.name,
        size_bytes=size_bytes,
        width=width,
        height=height,
        dar=dar,
        fps=_rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate")),
        video_codec_name=str(video.get("codec_name", "unknown")),
        video_codec_tag=str(video.get("codec_tag_string", "")),
        audio_codec_name=str(audio.get("codec_name", "unknown")) if audio else None,
        duration=duration,
    )


def probe(path: Path, ffprobe: Path) -> VideoInfo:
    """ffprobe를 실행해 영상 정보를 읽는다. 실패하면 ProbeError."""
    cmd = [
        ffprobe,
        "-v", "error",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        path,
    ]  # fmt: skip
    result = ffmpeg.run(cmd, timeout=60)
    if result.returncode != 0:
        lines = ffmpeg.decode(result.stderr).strip().splitlines()
        reason = lines[-1] if lines else f"종료 코드 {result.returncode}"
        # ffprobe는 "{경로}: 이유" 형태로 쓴다. 파일 이름은 진행 표시에 이미 있으므로 뗀다
        reason = reason.removeprefix(f"{path}: ")
        raise ProbeError(f"영상을 읽을 수 없음: {reason}")
    try:
        data = json.loads(ffmpeg.decode(result.stdout))
    except json.JSONDecodeError as e:
        raise ProbeError(f"ffprobe 출력을 해석할 수 없음: {e}") from e
    return parse(path, path.stat().st_size, data)
