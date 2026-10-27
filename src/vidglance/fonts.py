"""폰트 탐색 (spec §8): 설정 → 맑은 고딕 → 내장 Pretendard."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from PIL import ImageFont

from vidglance import paths

WINDOWS_FONTS = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
BUNDLED_DIR = Path("assets") / "fonts"  # paths.resource_dir() 기준


class FontNotFoundError(Exception):
    """쓸 수 있는 폰트가 없다."""


@dataclass(frozen=True)
class FontFiles:
    regular: Path
    bold: Path
    source: str  # 어디서 찾았는지 (-v 출력용)
    warnings: list[str] = field(default_factory=list)


def find_fonts(custom: str = "") -> FontFiles:
    """보통·굵게 폰트 파일을 찾는다. 하나도 없으면 FontNotFoundError."""
    warnings: list[str] = []
    searched: list[str] = []

    if custom:
        path = Path(custom)
        if path.is_file():
            return FontFiles(path, path, "설정 font")
        warnings.append(f"설정한 폰트 파일이 없어 기본 폰트를 씁니다: {path}")
        searched.append(f"설정 font: {path}")

    malgun = WINDOWS_FONTS / "malgun.ttf"
    if malgun.is_file():
        bold = WINDOWS_FONTS / "malgunbd.ttf"
        return FontFiles(
            malgun, bold if bold.is_file() else malgun, "맑은 고딕", warnings
        )
    searched.append(f"맑은 고딕: {malgun}")

    bundled = paths.resource_dir() / BUNDLED_DIR
    regular = bundled / "Pretendard-Regular.otf"
    if regular.is_file():
        bold = bundled / "Pretendard-Bold.otf"
        return FontFiles(
            regular, bold if bold.is_file() else regular, "내장 Pretendard", warnings
        )
    searched.append(f"내장 폰트: {regular}")

    places = "\n".join(f"  - {s}" for s in searched)
    raise FontNotFoundError(f"폰트를 찾을 수 없습니다. 찾아본 위치:\n{places}")


def load(path: Path, size: int) -> ImageFont.FreeTypeFont:
    """폰트 파일을 크기(px)로 연다."""
    return ImageFont.truetype(str(path), size)
