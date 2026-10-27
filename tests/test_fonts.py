from pathlib import Path

import pytest

from vidglance import fonts, paths


@pytest.fixture
def no_malgun(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Windows 폰트 폴더를 빈 임시 폴더로 바꾼다."""
    empty = tmp_path / "Fonts"
    empty.mkdir()
    monkeypatch.setattr(fonts, "WINDOWS_FONTS", empty)
    return empty


def test_custom_font_used_for_both(tmp_path: Path) -> None:
    custom = tmp_path / "내 폰트.ttf"
    custom.write_bytes(b"")
    found = fonts.find_fonts(str(custom))
    assert (found.regular, found.bold) == (custom, custom)
    assert found.warnings == []


def test_missing_custom_falls_back_with_warning(tmp_path: Path) -> None:
    found = fonts.find_fonts(str(tmp_path / "없음.ttf"))
    assert found.source in ("맑은 고딕", "내장 Pretendard")
    assert "없음.ttf" in found.warnings[0]


@pytest.mark.skipif(
    not (fonts.WINDOWS_FONTS / "malgun.ttf").is_file(), reason="맑은 고딕 없음"
)
def test_malgun_default() -> None:
    found = fonts.find_fonts()
    assert found.source == "맑은 고딕"
    assert found.regular.name.lower() == "malgun.ttf"
    assert found.bold.name.lower() == "malgunbd.ttf"


def test_malgun_without_bold_uses_regular(no_malgun: Path) -> None:
    (no_malgun / "malgun.ttf").write_bytes(b"")
    found = fonts.find_fonts()
    assert found.bold == found.regular == no_malgun / "malgun.ttf"


def test_bundled_pretendard_when_no_malgun(no_malgun: Path) -> None:
    found = fonts.find_fonts()
    assert found.source == "내장 Pretendard"
    assert found.regular.name == "Pretendard-Regular.otf"
    assert found.bold.name == "Pretendard-Bold.otf"
    # 한글 글리프가 실제로 그려지는지 (□ 대체 글리프가 아님)
    font = fonts.load(found.regular, 20)
    assert font.getmask("가").getbbox() != font.getmask("\uffff").getbbox()


def test_not_found_lists_places(
    no_malgun: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(paths, "resource_dir", lambda: tmp_path / "없는 리소스")
    with pytest.raises(fonts.FontNotFoundError) as exc:
        fonts.find_fonts("C:/없는/폰트.ttf")
    message = str(exc.value)
    assert "폰트.ttf" in message
    assert "malgun.ttf" in message
    assert "Pretendard-Regular.otf" in message
