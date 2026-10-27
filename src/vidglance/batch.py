"""입력 수집(파일/폴더), 영상 한 개 처리, 결과 (spec §5, §9).

화면 출력은 하지 않는다. 진행 표시·요약은 app.py가 결과 값을 보고 한다.
"""

import os
import re
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from vidglance import fonts
from vidglance.config import Settings
from vidglance.extract import extract_frames, plan_times
from vidglance.formatting import header_lines
from vidglance.layout import WEBP_MAX_SIZE, LayoutError, compute_layout
from vidglance.probe import ProbeError, probe
from vidglance.render import render_sheet, save_sheet

VIDEO_EXTENSIONS = frozenset({
    "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm",
    "m4v", "ts", "m2ts", "mpg", "mpeg", "3gp",
})  # fmt: skip
SHEET_FORMATS = ("webp", "jpg", "png")


class Status(StrEnum):
    DONE = "완료"
    SKIPPED = "건너뜀"
    FAILED = "실패"


@dataclass(frozen=True)
class InputItem:
    path: Path
    error: str | None = None  # "파일 없음" 등 처리 전에 이미 실패


@dataclass(frozen=True)
class Context:
    """영상마다 공통으로 쓰는 것."""

    settings: Settings
    ffprobe: Path
    fonts: fonts.FontFiles


@dataclass(frozen=True)
class Result:
    video: Path
    status: Status
    message: str = ""  # 실패·건너뜀 이유
    output: Path | None = None
    warnings: list[str] = field(default_factory=list)
    seconds: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)  # 단계별 소요 시간


def _natural_key(path: Path) -> list[int | str]:
    """자연 정렬: `2.mp4`가 `10.mp4`보다 앞."""
    parts = re.split(r"(\d+)", str(path).casefold())
    return [int(p) if p.isdigit() else p for p in parts]


def _is_sheet(path: Path, suffix: str) -> bool:
    name = path.name.casefold()
    return any(name.endswith(f"{suffix}.{fmt}".casefold()) for fmt in SHEET_FORMATS)


def _is_video_ext(path: Path) -> bool:
    return path.suffix.lower().lstrip(".") in VIDEO_EXTENSIONS


def collect_inputs(
    args: Sequence[str], recursive: bool, suffix: str
) -> list[InputItem]:
    """파일·폴더가 섞인 인자 → 처리할 영상 목록 (중복 제거, 자연 정렬).

    폴더는 영상 확장자만 모은다. 직접 지정한 파일은 확장자와 관계없이 넣는다.
    이미 만든 시트(`*{suffix}.webp` 등)는 뺀다.
    """
    found: list[InputItem] = []
    for arg in args:
        path = Path(arg).absolute()
        if path.is_dir():
            pattern = path.rglob("*") if recursive else path.iterdir()
            found += [
                InputItem(p)
                for p in pattern
                if p.is_file() and _is_video_ext(p) and not _is_sheet(p, suffix)
            ]
        elif path.is_file():
            if not _is_sheet(path, suffix):
                found.append(InputItem(path))
        else:
            found.append(InputItem(path, "파일 없음"))

    unique: dict[str, InputItem] = {}
    for item in found:
        unique.setdefault(os.path.normcase(str(item.path.resolve())), item)
    return sorted(unique.values(), key=lambda item: _natural_key(item.path))


def output_path(video: Path, settings: Settings) -> Path:
    """`{이름}{suffix}.{format}`. output_dir이 비면 영상 폴더, 상대 경로면 영상 폴더 기준."""
    folder = video.parent
    if settings.output_dir:
        folder = video.parent / Path(settings.output_dir)  # 절대 경로면 그대로
    return folder / f"{video.stem}{settings.suffix}.{settings.format}"


def process_video(video: Path, ctx: Context) -> Result:
    """영상 한 개의 시트를 만든다. 예외 대신 Result로 결과를 돌려준다."""
    began = time.perf_counter()
    s = ctx.settings
    out = output_path(video, s)
    timings: dict[str, float] = {}
    warnings: list[str] = []

    def result(status: Status, message: str = "", output: Path | None = None) -> Result:
        seconds = time.perf_counter() - began
        return Result(video, status, message, output, warnings, seconds, timings)

    if out.exists() and not s.overwrite:
        return result(Status.SKIPPED, "이미 있음", out)

    step = time.perf_counter()
    try:
        info = probe(video, ctx.ffprobe)
    except ProbeError as e:
        if not _is_video_ext(video):
            return result(Status.SKIPPED, f"영상 아님 ({e})")
        return result(Status.FAILED, str(e))
    timings["probe"] = time.perf_counter() - step

    lines = header_lines(info, s.header, s.language)
    try:
        layout = compute_layout(
            width=s.width,
            columns=s.columns,
            rows=s.rows,
            gap=s.gap,
            aspect=info.aspect,
            header_lines=len(lines),
            max_height=WEBP_MAX_SIZE if s.format == "webp" else None,
        )
    except LayoutError as e:
        return result(Status.FAILED, str(e))
    if layout.shrunk_from:
        warnings.append(
            f"WebP 최대 높이({WEBP_MAX_SIZE}px)를 넘어 너비를 "
            f"{layout.shrunk_from}px → {layout.width}px로 줄였습니다"
        )

    step = time.perf_counter()
    plan = plan_times(
        info.duration, len(layout.cells), s.skip_start_seconds, s.skip_end_seconds
    )
    extracted = extract_frames(
        video, plan.times, (layout.cell_width, layout.cell_height)
    )
    timings["extract"] = time.perf_counter() - step
    warnings += plan.warnings + extracted.warnings
    if all(f.image is None for f in extracted.frames):
        return result(Status.FAILED, "프레임을 하나도 뽑지 못했습니다")

    step = time.perf_counter()
    sheet = render_sheet(
        layout, lines, extracted.frames, ctx.fonts, s.theme, s.show_timestamp
    )
    timings["render"] = time.perf_counter() - step

    step = time.perf_counter()
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        save_sheet(sheet, out, s.format, s.quality)
    except OSError as e:
        return result(Status.FAILED, f"저장할 수 없음: {e}")
    timings["save"] = time.perf_counter() - step

    return result(Status.DONE, output=out)
