import json
from pathlib import Path
from typing import Any

import pytest

from vidglance import config, paths
from vidglance.config import (
    ConfigError,
    HeaderSettings,
    Settings,
    apply_overrides,
    load_config,
    resolve_config_path,
)


def _write(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# --- 생성·읽기 ---


def test_creates_default_file(tmp_path: Path) -> None:
    path = tmp_path / "한글 폴더" / "config.json"
    loaded = load_config(path)
    assert loaded.created
    assert loaded.settings == Settings()
    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "config_version": 1,\n  "columns": 4,')
    assert _read(path) == config.defaults_dict()


def test_default_file_matches_spec(tmp_path: Path) -> None:
    data = config.defaults_dict()
    assert list(data) == [
        "config_version", "columns", "rows", "width", "gap", "theme", "language",
        "header", "format", "quality", "suffix", "output_dir", "overwrite",
        "show_timestamp", "recursive", "skip_start_seconds", "skip_end_seconds",
        "font", "ffmpeg_dir", "close_delay_seconds",
    ]  # fmt: skip
    assert data["width"] == 1024 and data["quality"] == 85 and data["gap"] == 8
    assert data["header"] == dict.fromkeys(
        [
            "file_name",
            "size",
            "resolution",
            "fps",
            "video_codec",
            "audio_codec",
            "duration",
        ],
        True,
    )


def test_reads_values(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    data = config.defaults_dict() | {"columns": 5, "rows": 6, "gap": 0, "theme": "dark"}
    _write(path, data)
    loaded = load_config(path)
    assert not loaded.created
    s = loaded.settings
    assert (s.columns, s.rows, s.gap, s.theme) == (5, 6, 0, "dark")
    assert loaded.warnings == []


def test_bom_is_accepted(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"columns": 3}), encoding="utf-8-sig")
    assert load_config(path).settings.columns == 3


def test_missing_keys_filled_and_saved(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write(path, {"columns": 5, "header": {"size": False}, "my_note": "메모"})
    loaded = load_config(path)

    assert loaded.settings.columns == 5
    assert loaded.settings.header == HeaderSettings(size=False)
    saved = _read(path)
    assert saved["columns"] == 5  # 기존 값 유지
    assert saved["rows"] == 5  # 빠진 키 추가
    assert saved["header"]["size"] is False
    assert saved["header"]["duration"] is True
    assert saved["my_note"] == "메모"  # 모르는 키도 지우지 않는다
    assert loaded.warnings == ["모르는 설정 키(무시함): my_note"]


def test_complete_file_is_not_rewritten(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    text = json.dumps(config.defaults_dict())  # 한 줄짜리
    path.write_text(text, encoding="utf-8")
    load_config(path)
    assert path.read_text(encoding="utf-8") == text


def test_unknown_header_key_warns(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write(path, {"header": {"bitrate": True}})
    assert load_config(path).warnings == ["모르는 설정 키(무시함): header.bitrate"]


# --- 오류 ---


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ({"columns": 0}, "columns: 1~20 사이 정수여야 합니다 (현재: 0)"),
        ({"rows": 21}, "rows: 1~20 사이 정수여야 합니다"),
        ({"columns": 4.0}, "columns: 1~20 사이 정수여야 합니다"),
        ({"columns": True}, "columns: 1~20 사이 정수여야 합니다"),
        ({"width": "1024"}, 'width: 320~8000 사이 정수여야 합니다 (현재: "1024")'),
        ({"gap": 101}, "gap: 0~100"),
        ({"theme": "blue"}, 'theme: "light" / "dark" 중 하나여야 합니다'),
        ({"language": "jp"}, "language:"),
        ({"format": "gif"}, "format:"),
        ({"quality": 0}, "quality: 1~100"),
        ({"suffix": ""}, "suffix: 비어 있지 않은 문자열이어야 합니다"),
        ({"suffix": "_a/b?"}, "suffix: 파일명에 쓸 수 없는 문자가 있습니다: / ?"),
        ({"overwrite": 1}, "overwrite: true 또는 false여야 합니다"),
        ({"skip_start_seconds": -1}, "skip_start_seconds: 0 이상의 숫자여야 합니다"),
        ({"close_delay_seconds": 1.5}, "close_delay_seconds: 정수여야 합니다"),
        ({"header": {"fps": "yes"}}, "header.fps: true 또는 false여야 합니다"),
        ({"header": []}, "header: {"),
    ],
)
def test_invalid_values(tmp_path: Path, data: dict[str, Any], expected: str) -> None:
    path = tmp_path / "config.json"
    _write(path, data)
    before = path.read_text(encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert expected in str(exc.value)
    assert path.read_text(encoding="utf-8") == before  # 사용자 파일을 덮어쓰지 않는다


def test_all_errors_reported_together(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    _write(path, {"columns": 0, "theme": "x", "header": {"size": 1}})
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    message = str(exc.value)
    assert "columns:" in message and "theme:" in message and "header.size:" in message


def test_json_syntax_error_points_to_line(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text('{\n  "columns": 4,\n  "rows": 5,\n}', encoding="utf-8")
    with pytest.raises(ConfigError, match="4번째 줄"):
        load_config(path)


def test_backslash_hint(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        '{"font": "C:\\Fonts\\a.ttf"}', encoding="utf-8"
    )  # \F, \a 이스케이프 오류
    with pytest.raises(ConfigError) as exc:
        load_config(path)
    assert "\\\\로 두 번" in str(exc.value)


def test_not_an_object(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(ConfigError, match="형태여야"):
        load_config(path)


# --- 명령줄 덮어쓰기 ---


def test_apply_overrides() -> None:
    s = apply_overrides(Settings(), {"columns": 5, "rows": 6, "format": "png"})
    assert (s.columns, s.rows, s.format) == (5, 6, "png")
    assert s.width == 1024


def test_apply_overrides_validates() -> None:
    with pytest.raises(ConfigError, match="명령줄 옵션 오류"):
        apply_overrides(Settings(), {"columns": 50})


# --- 위치 ---


def test_resolve_explicit(tmp_path: Path) -> None:
    assert (
        resolve_config_path(str(tmp_path / "a.json")) == (tmp_path / "a.json").resolve()
    )


@pytest.fixture
def places(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[Path, Path]:
    app = tmp_path / "app"
    appdata = tmp_path / "appdata"
    app.mkdir()
    monkeypatch.setattr(paths, "app_dir", lambda: app)
    monkeypatch.setenv("APPDATA", str(appdata))
    return app, appdata


def test_resolve_beside_exe(places: tuple[Path, Path]) -> None:
    app, _ = places
    assert resolve_config_path() == app / "config.json"


def test_resolve_appdata_when_not_writable(
    places: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    _, appdata = places
    monkeypatch.setattr(config, "_can_write", lambda folder: False)
    assert resolve_config_path() == appdata / "VidGlance" / "config.json"


def test_resolve_prefers_existing(places: tuple[Path, Path]) -> None:
    app, appdata = places
    existing = appdata / "VidGlance" / "config.json"
    existing.parent.mkdir(parents=True)
    existing.write_text("{}", encoding="utf-8")
    assert resolve_config_path() == existing
    (app / "config.json").write_text("{}", encoding="utf-8")
    assert resolve_config_path() == app / "config.json"
