from pathlib import Path

import pytest
from PIL import Image

from vidglance import fonts
from vidglance.config import OutputFormat, ThemeName
from vidglance.extract import Frame
from vidglance.layout import Layout, compute_layout
from vidglance.render import THEMES, fit_text, render_sheet, save_sheet

WHITE = (255, 255, 255)


@pytest.fixture(scope="module")
def font_files() -> fonts.FontFiles:
    return fonts.find_fonts()


def _layout(header_lines: int = 5, rows: int = 2) -> Layout:
    return compute_layout(
        width=640, columns=2, rows=rows, gap=8, aspect=16 / 9, header_lines=header_lines
    )


def _frames(
    layout: Layout, count: int, color: tuple[int, int, int] = WHITE
) -> list[Frame]:
    size = (layout.cell_width, layout.cell_height)
    return [Frame(60.0 * (i + 1), Image.new("RGB", size, color)) for i in range(count)]


def _is_close(a: tuple[int, ...], b: tuple[int, ...], tol: int = 2) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b, strict=True))


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_sheet_size_and_background(
    theme: ThemeName, font_files: fonts.FontFiles
) -> None:
    lay = _layout()
    sheet = render_sheet(lay, ["File Name: a.mp4"], _frames(lay, 4), font_files, theme)
    assert sheet.size == (lay.width, lay.height)
    assert sheet.mode == "RGB"
    assert sheet.getpixel((1, 1)) == THEMES[theme].background
    assert sheet.getpixel((lay.width - 2, lay.height - 2)) == THEMES[theme].background


def test_frames_pasted_in_cells(font_files: fonts.FontFiles) -> None:
    lay = _layout()
    frames = _frames(lay, 4, (10, 200, 30))
    sheet = render_sheet(lay, [], frames, font_files, show_timestamp=False)
    for rect in lay.cells:
        assert sheet.getpixel((rect.x, rect.y)) == (10, 200, 30)
        assert sheet.getpixel((rect.x + rect.w - 1, rect.y + rect.h - 1)) == (
            10,
            200,
            30,
        )


def test_failed_and_empty_cells(font_files: fonts.FontFiles) -> None:
    lay = _layout()
    frames = _frames(lay, 2)
    frames[1] = Frame(120.0, None)  # 실패 칸
    # 칸 4개 중 프레임 2개 → 3·4번째는 빈 칸(배경색)
    sheet = render_sheet(lay, [], frames, font_files, "dark", show_timestamp=False)
    failed, empty = lay.cells[1], lay.cells[2]
    assert sheet.getpixel((failed.x + 5, failed.y + 5)) == THEMES["dark"].failed_cell
    assert sheet.getpixel((empty.x + 5, empty.y + 5)) == THEMES["dark"].background


def test_timestamp_box_bottom_right_on_bright_frame(
    font_files: fonts.FontFiles,
) -> None:
    lay = _layout()
    sheet = render_sheet(lay, [], _frames(lay, 4), font_files)
    rect = lay.cells[0]
    margin = lay.timestamp_margin
    # 박스 안쪽 오른쪽 아래 구석: 흰 프레임 위 검정 60% → 약 102
    inside = sheet.getpixel(
        (rect.x + rect.w - margin - 1, rect.y + rect.h - margin - 1)
    )
    assert _is_close(inside, (102, 102, 102))
    # 박스 바깥(가장자리 여백)은 프레임 그대로
    outside = sheet.getpixel((rect.x + rect.w - 1, rect.y + rect.h - 1))
    assert outside == WHITE
    # 칸 왼쪽 위에는 아무것도 없다
    assert sheet.getpixel((rect.x + 2, rect.y + 2)) == WHITE
    # 박스 안에 흰 글자 픽셀이 있다
    box = sheet.crop(
        (
            rect.x + rect.w // 2,
            rect.y + rect.h - 40,
            rect.x + rect.w - margin,
            rect.y + rect.h - margin,
        )
    )
    assert WHITE in [c for _, c in box.getcolors(maxcolors=100000) or []]


def test_no_timestamp(font_files: fonts.FontFiles) -> None:
    lay = _layout()
    sheet = render_sheet(lay, [], _frames(lay, 4), font_files, show_timestamp=False)
    rect = lay.cells[0]
    corner = sheet.crop((rect.x, rect.y, rect.x + rect.w, rect.y + rect.h))
    assert corner.getcolors() == [(rect.w * rect.h, WHITE)]


def test_header_text_drawn_only_in_header(font_files: fonts.FontFiles) -> None:
    lay = _layout()
    sheet = render_sheet(lay, ["파일명: 한글.mp4", "크기: 1.00MB"], [], font_files)
    header = sheet.crop((0, 0, lay.width, lay.cells[0].y))
    colors = {c for _, c in header.getcolors(maxcolors=100000) or []}
    assert (0, 0, 0) in colors  # 검정 글자
    # 헤더 없이 그리면 격자가 위로 붙는다
    no_header = _layout(header_lines=0)
    blank = render_sheet(no_header, [], [], font_files)
    assert blank.getcolors() == [(no_header.width * no_header.height, WHITE)]


def test_fit_text_middle_ellipsis(font_files: fonts.FontFiles) -> None:
    font = fonts.load(font_files.regular, 14)
    short = "File Name: a.mp4"
    assert fit_text(short, font, 1000) == short

    long = "File Name: " + "아주긴파일이름" * 20 + "_끝.mp4"
    fitted = fit_text(long, font, 300)
    assert "…" in fitted
    assert font.getlength(fitted) <= 300
    assert fitted.startswith("File Name: ")
    assert fitted.endswith("_끝.mp4")
    # 한 글자만 더 남겨도 넘친다 (최대한 남긴다)
    assert len(fitted) >= 10


@pytest.mark.parametrize(
    ("fmt", "pil_format"), [("webp", "WEBP"), ("jpg", "JPEG"), ("png", "PNG")]
)
def test_save_formats(fmt: OutputFormat, pil_format: str, tmp_path: Path) -> None:
    image = Image.new("RGB", (64, 32), (200, 100, 50))
    out = tmp_path / f"영상 이름_sheet.{fmt}"
    save_sheet(image, out, fmt, 85)
    with Image.open(out) as saved:
        assert saved.format == pil_format
        assert saved.size == (64, 32)
    assert list(tmp_path.iterdir()) == [out]  # 임시 파일이 남지 않는다


def test_save_failure_leaves_no_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = Image.new("RGB", (8, 8))

    def broken_save(*args: object, **kwargs: object) -> None:
        Path(args[0]).write_bytes(b"partial")
        raise OSError("디스크 가득 참")

    monkeypatch.setattr(Image.Image, "save", lambda self, *a, **k: broken_save(*a, **k))
    out = tmp_path / "a_sheet.webp"
    with pytest.raises(OSError):
        save_sheet(image, out, "webp", 85)
    assert list(tmp_path.iterdir()) == []


def test_save_replaces_existing(tmp_path: Path) -> None:
    out = tmp_path / "a_sheet.png"
    out.write_bytes(b"old")
    save_sheet(Image.new("RGB", (4, 4)), out, "png", 85)
    with Image.open(out) as saved:
        assert saved.size == (4, 4)
