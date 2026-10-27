"""순수 함수: 시트 좌표 계산 (spec §8). I/O를 하지 않는다."""

import math
from dataclasses import dataclass

PADDING = 10  # 바깥 여백 (헤더 아래 여백도 같은 값)
LINE_SPACING = 1.3  # 헤더 줄 높이 = 글자 크기 × 1.3
HEADER_FONT_RATIO = 0.014  # 헤더 글자 = 시트 너비 × 0.014
TIMESTAMP_FONT_RATIO = 0.06  # 타임스탬프 글자 = 칸 너비 × 0.06
TIMESTAMP_MARGIN_RATIO = 0.02  # 타임스탬프 박스와 칸 가장자리 사이 = 칸 너비 × 0.02
TIMESTAMP_BOX_PADDING_RATIO = 0.25  # 박스 안쪽 여백 = 글자 크기 × 0.25
MIN_FONT_SIZE = 11
MIN_TIMESTAMP_MARGIN = 3
MIN_CELL_WIDTH = 16
WEBP_MAX_SIZE = 16383


class LayoutError(ValueError):
    """설정으로는 시트를 배치할 수 없다 (칸이 너무 작음 등)."""


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int


@dataclass(frozen=True)
class Layout:
    width: int
    height: int
    padding: int
    header_font_size: int
    header_line_height: int
    header_top: int  # 첫 헤더 줄의 위쪽 y (헤더가 없으면 의미 없음)
    cell_width: int
    cell_height: int
    cells: list[Rect]  # 왼쪽 위부터 행 순서
    timestamp_font_size: int
    timestamp_margin: int
    timestamp_box_padding: int
    shrunk_from: int | None  # 최대 높이 때문에 너비를 줄였으면 원래 너비


def _layout(
    width: int, columns: int, rows: int, gap: int, aspect: float, header_lines: int
) -> Layout:
    cell_w = (width - 2 * PADDING - (columns - 1) * gap) // columns
    if cell_w < MIN_CELL_WIDTH:
        raise LayoutError(
            f"칸 너비가 {cell_w}px로 너무 작습니다. width를 늘리거나 columns·gap을 줄이세요"
        )
    cell_h = max(1, round(cell_w / aspect))

    header_font = max(MIN_FONT_SIZE, round(width * HEADER_FONT_RATIO))
    line_h = round(header_font * LINE_SPACING)
    header_h = header_lines * line_h + PADDING if header_lines else 0

    grid_w = columns * cell_w + (columns - 1) * gap
    left = (width - grid_w) // 2  # 내림으로 남은 px를 양쪽에 나눈다
    top = PADDING + header_h
    cells = [
        Rect(left + c * (cell_w + gap), top + r * (cell_h + gap), cell_w, cell_h)
        for r in range(rows)
        for c in range(columns)
    ]
    height = top + rows * cell_h + (rows - 1) * gap + PADDING

    ts_font = max(MIN_FONT_SIZE, round(cell_w * TIMESTAMP_FONT_RATIO))
    return Layout(
        width=width,
        height=height,
        padding=PADDING,
        header_font_size=header_font,
        header_line_height=line_h,
        header_top=PADDING,
        cell_width=cell_w,
        cell_height=cell_h,
        cells=cells,
        timestamp_font_size=ts_font,
        timestamp_margin=max(
            MIN_TIMESTAMP_MARGIN, round(cell_w * TIMESTAMP_MARGIN_RATIO)
        ),
        timestamp_box_padding=round(ts_font * TIMESTAMP_BOX_PADDING_RATIO),
        shrunk_from=None,
    )


def compute_layout(
    *,
    width: int,
    columns: int,
    rows: int,
    gap: int,
    aspect: float,
    header_lines: int,
    max_height: int | None = None,
) -> Layout:
    """설정·영상 비율(가로/세로)·헤더 줄 수 → 시트 크기와 칸 좌표.

    max_height(예: WebP 16383)를 넘으면 시트 너비를 비율대로 줄여 다시 계산한다.
    """
    layout = _layout(width, columns, rows, gap, aspect, header_lines)
    if max_height is None or layout.height <= max_height:
        return layout

    reduced = width
    while layout.height > max_height:
        # 여백·간격은 고정이라 한 번에 딱 맞지 않을 수 있어 넘지 않을 때까지 줄인다
        reduced = min(reduced - 1, math.floor(reduced * max_height / layout.height))
        layout = _layout(reduced, columns, rows, gap, aspect, header_lines)
    return Layout(**{**layout.__dict__, "shrunk_from": width})
