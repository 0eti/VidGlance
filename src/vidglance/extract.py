"""시점 계산, PyAV 프레임 추출 (spec §7).

PyAV(`import av`)는 이 모듈에서만 쓴다.
"""

import math
import time
from dataclasses import dataclass
from pathlib import Path

import av
from av.container import InputContainer
from av.stream import Disposition
from av.video.frame import VideoFrame
from av.video.stream import VideoStream
from PIL import Image

from vidglance.formatting import format_duration

# 칸 사이 최소 간격(초). 이보다 촘촘하면 "매우 짧은 영상"으로 본다.
MIN_SPACING = 0.1
# 프레임 시각 비교 허용 오차(초, 부동소수 오차용)
_EPSILON = 1e-3

_ROTATE = {
    90: Image.Transpose.ROTATE_90,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_270,
}


@dataclass(frozen=True)
class FramePlan:
    """뽑을 시점 목록. 영상이 매우 짧으면 칸 수보다 적다."""

    times: list[float]
    warnings: list[str]


@dataclass(frozen=True)
class Frame:
    """칸 하나의 결과. image가 None이면 추출 실패(회색 칸)."""

    time: float
    image: Image.Image | None


@dataclass(frozen=True)
class ExtractResult:
    frames: list[Frame]
    warnings: list[str]
    seconds: float  # 전체 소요 시간 (파일 열기 포함)
    open_seconds: float  # 파일 열기
    frame_seconds: list[float]  # 프레임별 소요 시간 (재시도 포함)


def plan_times(
    duration: float, count: int, skip_start: float = 0, skip_end: float = 0
) -> FramePlan:
    """`t_i = S + L·i/(N+1)` (i = 1..N). 처음과 끝은 제외한 균등 간격."""
    warnings: list[str] = []
    min_length = count * MIN_SPACING

    start, end = skip_start, duration - skip_end
    if (skip_start or skip_end) and end - start < min_length:
        warnings.append(
            f"앞뒤 제외 구간을 빼면 {max(0.0, end - start):.1f}초만 남아 제외 구간을 무시합니다"
        )
        start, end = 0.0, duration
    length = end - start

    n = count
    if length < min_length:
        # 간격이 0.1초 이상이 되는 최대 개수 (부동소수 오차 보정 후 내림)
        n = max(1, math.floor(length / MIN_SPACING + 1e-9) - 1)
        warnings.append(f"영상이 짧아 {count}칸 중 {n}칸만 채웁니다")

    times = [start + length * i / (n + 1) for i in range(1, n + 1)]
    return FramePlan(times, warnings)


def backend_version() -> str:
    """-v 출력용: `PyAV 19.0.2 (FFmpeg 9.0.2)`."""
    return f"PyAV {av.__version__} (FFmpeg {av.ffmpeg_version_info})"


def _first_video(container: InputContainer) -> VideoStream | None:
    # 앨범 아트(attached_pic)는 건너뛴다 (probe와 같은 규칙)
    for stream in container.streams.video:
        if not stream.disposition & Disposition.attached_pic:
            return stream
    return None


def _to_image(frame: VideoFrame, size: tuple[int, int]) -> Image.Image:
    """칸 크기로 줄이고(애너모픽 보정 포함) display matrix대로 돌린다."""
    cell_w, cell_h = size
    rotation = round(frame.rotation / 90) * 90 % 360
    if rotation in (90, 270):
        cell_w, cell_h = cell_h, cell_w
    small = frame.reformat(
        width=cell_w, height=cell_h, format="rgb24", interpolation="BICUBIC"
    )
    image = small.to_image()
    if rotation in _ROTATE:
        image = image.transpose(_ROTATE[rotation])
    return image


def _grab(
    container: InputContainer,
    stream: VideoStream,
    target: float,
    size: tuple[int, int],
) -> Image.Image | None:
    """target초(절대 시각) 이전 키프레임으로 seek한 뒤 target 이상인 첫 프레임을 돌려준다."""
    try:
        container.seek(int(target / stream.time_base), stream=stream, backward=True)
        for frame in container.decode(stream):
            if frame.time is not None and frame.time >= target - _EPSILON:
                return _to_image(frame, size)
    except av.FFmpegError:
        return None
    return None  # target 이후 프레임이 없음 (끝을 넘음)


def extract_frames(
    video: Path, times: list[float], size: tuple[int, int]
) -> ExtractResult:
    """파일을 한 번 열고 시점마다 seek해 칸 크기 프레임을 뽑는다.

    실패한 시점은 1초 앞에서 한 번 더 시도하고, 그래도 실패하면 image=None.
    """
    began = time.perf_counter()
    try:
        container = av.open(str(video))
    except (av.FFmpegError, OSError) as e:
        seconds = time.perf_counter() - began
        frames = [Frame(t, None) for t in times]
        warning = f"영상을 열 수 없어 모든 칸을 회색으로 둡니다: {e}"
        return ExtractResult(frames, [warning], seconds, seconds, [0.0] * len(times))

    with container:
        open_seconds = time.perf_counter() - began
        stream = _first_video(container)
        frames: list[Frame] = []
        frame_seconds: list[float] = []
        if stream is not None:
            stream.thread_type = "AUTO"
        # ffmpeg의 입력 seek처럼 파일 시작 시각 기준으로 맞춘다
        start = container.start_time / av.time_base if container.start_time else 0.0
        for t in times:
            frame_began = time.perf_counter()
            image = None
            if stream is not None:
                image = _grab(container, stream, start + t, size)
                if image is None:
                    image = _grab(container, stream, start + max(0.0, t - 1), size)
            frames.append(Frame(t, image))
            frame_seconds.append(time.perf_counter() - frame_began)

    warnings = [
        f"{format_duration(f.time)} 프레임을 뽑지 못해 회색 칸으로 둡니다"
        for f in frames
        if f.image is None
    ]
    seconds = time.perf_counter() - began
    return ExtractResult(frames, warnings, seconds, open_seconds, frame_seconds)
