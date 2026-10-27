import pytest

from vidglance.layout import WEBP_MAX_SIZE, Layout, LayoutError, Rect, compute_layout


def _lay(
    *,
    width: int = 1024,
    columns: int = 4,
    rows: int = 5,
    gap: int = 8,
    aspect: float = 16 / 9,
    header_lines: int = 5,
    max_height: int | None = None,
) -> Layout:
    return compute_layout(
        width=width,
        columns=columns,
        rows=rows,
        gap=gap,
        aspect=aspect,
        header_lines=header_lines,
        max_height=max_height,
    )


def test_default_sheet() -> None:
    lay = _lay()
    # 칸 너비 (1024 − 20 − 24) / 4 = 245, 높이 245 / (16/9) = 137.8 → 138
    assert (lay.cell_width, lay.cell_height) == (245, 138)
    # 헤더 글자 1024 × 0.014 = 14.3 → 14, 줄 높이 14 × 1.3 = 18.2 → 18
    assert (lay.header_font_size, lay.header_line_height) == (14, 18)
    # 헤더 높이 5 × 18 + 10 = 100 → 격자는 y = 10 + 100
    assert lay.cells[0] == Rect(10, 110, 245, 138)
    assert lay.cells[1] == Rect(10 + 245 + 8, 110, 245, 138)
    assert lay.cells[4] == Rect(10, 110 + 138 + 8, 245, 138)
    assert len(lay.cells) == 20
    assert lay.height == 10 + 100 + 5 * 138 + 4 * 8 + 10
    assert lay.width == 1024
    # 타임스탬프: 245 × 0.06 = 14.7 → 15, 여백 245 × 0.02 = 4.9 → 5, 박스 안쪽 15 × 0.25 → 4
    assert (lay.timestamp_font_size, lay.timestamp_margin) == (15, 5)
    assert lay.timestamp_box_padding == 4
    assert lay.shrunk_from is None


def test_grid_fits_inside_padding() -> None:
    lay = _lay()
    last = lay.cells[-1]
    assert last.x + last.w <= lay.width - lay.padding
    assert last.y + last.h == lay.height - lay.padding


def test_leftover_pixels_are_split() -> None:
    # (1027 − 20 − 24) / 4 = 245.75 → 245, 남는 3px → 왼쪽 1, 오른쪽 2
    lay = _lay(width=1027)
    assert lay.cells[0].x == 11
    assert lay.width - (lay.cells[3].x + lay.cells[3].w) == 12


def test_gap_zero_cells_touch() -> None:
    lay = _lay(gap=0)
    a, b, below = lay.cells[0], lay.cells[1], lay.cells[4]
    assert a.x + a.w == b.x
    assert a.y + a.h == below.y


def test_no_header() -> None:
    lay = _lay(header_lines=0)
    assert lay.cells[0].y == lay.padding
    with_header = _lay()
    assert with_header.height - lay.height == 100


def test_header_lines_change_height() -> None:
    two = _lay(header_lines=2)
    assert two.cells[0].y == 10 + 2 * 18 + 10


def test_vertical_video() -> None:
    lay = _lay(aspect=9 / 16)
    assert lay.cell_width == 245
    assert lay.cell_height == round(245 * 16 / 9)


def test_anamorphic_uses_display_aspect() -> None:
    # 저장 640×480이라도 DAR 16:9를 넘기면 16:9 칸
    lay = _lay(aspect=16 / 9)
    assert lay.cell_width / lay.cell_height == pytest.approx(16 / 9, rel=0.01)


def test_min_font_sizes() -> None:
    lay = _lay(width=320, columns=10, gap=0)
    assert lay.header_font_size == 11  # 320 × 0.014 = 4.5 → 최소 11
    assert lay.timestamp_font_size == 11
    assert lay.timestamp_margin == 3


def test_cell_too_small() -> None:
    with pytest.raises(LayoutError, match="너무 작습니다"):
        _lay(width=320, columns=20, gap=100)


def test_webp_limit_shrinks_width() -> None:
    # 세로 영상 20행: 원래 높이가 16383을 넘는다
    natural = _lay(width=2000, rows=20, aspect=9 / 16)
    assert natural.height > WEBP_MAX_SIZE

    lay = _lay(width=2000, rows=20, aspect=9 / 16, max_height=WEBP_MAX_SIZE)
    assert lay.height <= WEBP_MAX_SIZE
    assert lay.height > WEBP_MAX_SIZE * 0.98  # 필요 이상으로 줄이지 않는다
    assert lay.width < 2000
    assert lay.shrunk_from == 2000
    assert len(lay.cells) == 80


def test_within_limit_is_unchanged() -> None:
    lay = _lay(max_height=WEBP_MAX_SIZE)
    assert lay == _lay()
