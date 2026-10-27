"""Pillow 합성, 저장 (spec §8, §9)."""

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vidglance import fonts
from vidglance.config import OutputFormat, ThemeName
from vidglance.extract import Frame
from vidglance.formatting import format_duration
from vidglance.layout import Layout, Rect

RGB = tuple[int, int, int]


@dataclass(frozen=True)
class Theme:
    background: RGB
    header_text: RGB
    cell_background: RGB  # 레터박스
    failed_cell: RGB


THEMES: dict[ThemeName, Theme] = {
    "light": Theme(
        background=(0xFF, 0xFF, 0xFF),
        header_text=(0x00, 0x00, 0x00),
        cell_background=(0x00, 0x00, 0x00),
        failed_cell=(0x9E, 0x9E, 0x9E),
    ),
    "dark": Theme(
        background=(0x1E, 0x1E, 0x1E),
        header_text=(0xED, 0xED, 0xED),
        cell_background=(0x00, 0x00, 0x00),
        failed_cell=(0x4A, 0x4A, 0x4A),
    ),
}

# 타임스탬프는 테마와 관계없이 같은 스타일 (밝은 장면에서도 읽히도록)
TIMESTAMP_BOX = (0, 0, 0, round(255 * 0.6))
TIMESTAMP_TEXT = (0xFF, 0xFF, 0xFF, 0xFF)
ELLIPSIS = "…"

_SAVE_FORMATS: dict[OutputFormat, str] = {"webp": "WEBP", "jpg": "JPEG", "png": "PNG"}


def fit_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> str:
    """너비를 넘으면 가운데를 `…`로 줄인다 (앞뒤를 최대한 남긴다)."""
    if font.getlength(text) <= max_width:
        return text

    def shortened(keep: int) -> str:
        head = keep - keep // 2
        return text[:head] + ELLIPSIS + text[len(text) - keep // 2 :]

    # 남길 글자 수를 이분 탐색
    lo, hi = 0, len(text) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if font.getlength(shortened(mid)) <= max_width:
            lo = mid
        else:
            hi = mid - 1
    return shortened(lo)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    layout: Layout,
    lines: list[str],
    font_files: fonts.FontFiles,
    color: RGB,
) -> None:
    bold = fonts.load(font_files.bold, layout.header_font_size)
    regular = fonts.load(font_files.regular, layout.header_font_size)
    max_width = layout.width - 2 * layout.padding
    for i, line in enumerate(lines):
        font = bold if i == 0 else regular  # 첫 줄만 굵게
        # 줄 상자의 세로 가운데에 글자를 맞춘다
        y = layout.header_top + i * layout.header_line_height
        y += layout.header_line_height / 2
        text = fit_text(line, font, max_width)
        draw.text((layout.padding, y), text, font=font, fill=color, anchor="lm")


def _draw_timestamp(
    draw: ImageDraw.ImageDraw,
    rect: Rect,
    text: str,
    font: ImageFont.FreeTypeFont,
    layout: Layout,
) -> None:
    """칸 오른쪽 아래에 반투명 박스 + 흰 글자 (RGBA 오버레이에 그린다)."""
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font, anchor="lt")
    pad = layout.timestamp_box_padding
    box_right = rect.x + rect.w - layout.timestamp_margin
    box_bottom = rect.y + rect.h - layout.timestamp_margin
    box_left = box_right - (right - left) - 2 * pad
    box_top = box_bottom - (bottom - top) - 2 * pad
    draw.rectangle(
        (box_left, box_top, box_right - 1, box_bottom - 1), fill=TIMESTAMP_BOX
    )
    draw.text(
        (box_left + pad - left, box_top + pad - top),
        text,
        font=font,
        fill=TIMESTAMP_TEXT,
        anchor="lt",
    )


def render_sheet(
    layout: Layout,
    header_lines: list[str],
    frames: list[Frame],
    font_files: fonts.FontFiles,
    theme: ThemeName = "light",
    show_timestamp: bool = True,
) -> Image.Image:
    """헤더 + 격자 + 타임스탬프를 합성한다.

    frames가 칸보다 적으면 남는 칸은 비워 둔다(매우 짧은 영상).
    image가 None인 프레임은 실패 칸(회색)으로 그린다.
    """
    colors = THEMES[theme]
    sheet = Image.new("RGB", (layout.width, layout.height), colors.background)
    draw = ImageDraw.Draw(sheet)
    if header_lines:
        _draw_header(draw, layout, header_lines, font_files, colors.header_text)

    overlay = Image.new("RGBA", sheet.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    ts_font = fonts.load(font_files.regular, layout.timestamp_font_size)
    for rect, frame in zip(layout.cells, frames, strict=False):
        box = (rect.x, rect.y, rect.x + rect.w - 1, rect.y + rect.h - 1)
        if frame.image is None:
            draw.rectangle(box, fill=colors.failed_cell)
        else:
            draw.rectangle(box, fill=colors.cell_background)
            image = frame.image
            if image.size != (rect.w, rect.h):
                image = image.resize((rect.w, rect.h), Image.Resampling.BICUBIC)
            sheet.paste(image, (rect.x, rect.y))
        if show_timestamp:
            text = format_duration(frame.time)
            _draw_timestamp(overlay_draw, rect, text, ts_font, layout)

    return Image.alpha_composite(sheet.convert("RGBA"), overlay).convert("RGB")


def save_sheet(image: Image.Image, path: Path, fmt: OutputFormat, quality: int) -> None:
    """임시 이름(`.{이름}.tmp`)으로 쓴 뒤 바꾼다. 중간에 끊겨도 깨진 파일이 남지 않는다."""
    tmp = path.with_name(f".{path.name}.tmp")
    options: dict[str, object] = {}
    if fmt != "png":
        options["quality"] = quality
    try:
        image.save(tmp, _SAVE_FORMATS[fmt], **options)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
