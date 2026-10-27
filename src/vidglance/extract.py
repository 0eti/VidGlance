"""시점 계산, ffmpeg 프레임 추출(병렬) (spec §7)."""

import io
import math
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from vidglance import ffmpeg
from vidglance.formatting import format_duration

# 칸 사이 최소 간격(초). 이보다 촘촘하면 "매우 짧은 영상"으로 본다.
MIN_SPACING = 0.1
# 프레임 하나 추출 제한 시간(초)
FRAME_TIMEOUT = 60


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
    seconds: float  # 전체 추출 소요 시간
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


def extract_frame(
    ffmpeg_path: Path, video: Path, t: float, size: tuple[int, int]
) -> Image.Image | None:
    """t초의 프레임 하나를 칸 크기(size)로 뽑는다. 실패하면 None."""
    cell_w, cell_h = size
    cmd = [
        ffmpeg_path,
        "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.3f}",
        "-i", video,
        "-frames:v", "1",
        "-vf", f"scale={cell_w}:{cell_h}:flags=bicubic,setsar=1",
        "-f", "image2pipe", "-vcodec", "png", "-",
    ]  # fmt: skip
    try:
        result = ffmpeg.run(cmd, timeout=FRAME_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0 or not result.stdout:
        return None
    try:
        with Image.open(io.BytesIO(result.stdout)) as img:
            return img.convert("RGB")
    except OSError:
        return None


def _extract_with_retry(
    ffmpeg_path: Path, video: Path, t: float, size: tuple[int, int]
) -> tuple[Image.Image | None, float]:
    """실패하면 1초 앞에서 한 번 더 시도한다. (이미지, 소요 시간)."""
    began = time.perf_counter()
    image = extract_frame(ffmpeg_path, video, t, size)
    if image is None:
        image = extract_frame(ffmpeg_path, video, max(0.0, t - 1), size)
    return image, time.perf_counter() - began


def default_jobs() -> int:
    """jobs = 0일 때 쓰는 병렬 수: min(4, CPU 코어 수)."""
    return min(4, os.cpu_count() or 1)


def extract_frames(
    ffmpeg_path: Path,
    video: Path,
    times: list[float],
    size: tuple[int, int],
    jobs: int = 0,
) -> ExtractResult:
    """여러 시점을 스레드 풀로 병렬 추출한다. 일부가 실패해도 나머지는 돌려준다."""
    began = time.perf_counter()
    with ThreadPoolExecutor(max_workers=jobs or default_jobs()) as pool:
        results = list(
            pool.map(lambda t: _extract_with_retry(ffmpeg_path, video, t, size), times)
        )
    seconds = time.perf_counter() - began

    frames = [Frame(t, image) for t, (image, _) in zip(times, results, strict=True)]
    warnings = [
        f"{format_duration(f.time)} 프레임을 뽑지 못해 회색 칸으로 둡니다"
        for f in frames
        if f.image is None
    ]
    return ExtractResult(frames, warnings, seconds, [s for _, s in results])


if __name__ == "__main__":
    # 임시 디버그 명령 (Phase 2): python -m vidglance.extract <파일> [jobs]
    # 4×5, 칸 너비 244px(시트 1024px 기준)로 뽑고 단계별 시간을 출력한다.
    import sys

    from vidglance.probe import ProbeError, probe

    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    target = Path(sys.argv[1]).resolve()
    jobs = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    tools = ffmpeg.find_tools()
    print(f"ffmpeg: {tools.ffmpeg}\n        {ffmpeg.version(tools.ffmpeg)}")

    began = time.perf_counter()
    try:
        info = probe(target, tools.ffprobe)
    except ProbeError as e:
        print(f"실패: {e}")
        sys.exit(1)
    probe_seconds = time.perf_counter() - began

    plan = plan_times(info.duration, 20)
    size = (244, max(1, round(244 / info.aspect)))
    result = extract_frames(tools.ffmpeg, target, plan.times, size, jobs)
    total = time.perf_counter() - began

    print(
        f"영상: {info.file_name}  {format_duration(info.duration)}  {size[0]}x{size[1]}"
    )
    print(f"probe   {probe_seconds:6.2f}s")
    print(
        f"추출    {result.seconds:6.2f}s  (jobs={jobs or default_jobs()}, "
        f"프레임당 평균 {sum(result.frame_seconds) / len(result.frame_seconds):.2f}s, "
        f"최대 {max(result.frame_seconds):.2f}s)"
    )
    print(f"합계    {total:6.2f}s")
    for warning in plan.warnings + result.warnings:
        print(f"경고: {warning}")
