"""config.json 위치·생성·검증·병합 → Settings(dataclass) (spec §3).

설정 파일은 이 모듈에서만 읽고 쓴다. 다른 모듈은 Settings만 받는다.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Literal

from vidglance import paths

Language = Literal["en", "ko"]
ThemeName = Literal["light", "dark"]
OutputFormat = Literal["webp", "jpg", "png"]

CONFIG_NAME = "config.json"
CONFIG_VERSION = 1
FORBIDDEN_FILENAME_CHARS = '<>:"/\\|?*'


class ConfigError(Exception):
    """설정 파일을 쓸 수 없다. 메시지는 사용자에게 그대로 보여준다."""


@dataclass(frozen=True)
class HeaderSettings:
    """헤더 항목별 표시 여부 (spec §6)."""

    file_name: bool = True
    size: bool = True
    resolution: bool = True
    fps: bool = True
    video_codec: bool = True
    audio_codec: bool = True
    duration: bool = True


@dataclass(frozen=True)
class Settings:
    """config.json 값 (spec §3.2). 필드 순서가 파일에 쓰는 키 순서다."""

    config_version: int = CONFIG_VERSION
    columns: int = 4
    rows: int = 5
    width: int = 1024
    gap: int = 8
    theme: ThemeName = "light"
    language: Language = "en"
    header: HeaderSettings = field(default_factory=HeaderSettings)
    format: OutputFormat = "webp"
    quality: int = 85
    suffix: str = "_sheet"
    output_dir: str = ""
    overwrite: bool = False
    show_timestamp: bool = True
    recursive: bool = False
    skip_start_seconds: float = 0
    skip_end_seconds: float = 0
    font: str = ""
    ffmpeg_dir: str = ""
    close_delay_seconds: int = 3


@dataclass(frozen=True)
class LoadedConfig:
    settings: Settings
    path: Path
    created: bool  # 이번에 새로 만들었는지
    warnings: list[str]


# --- 값 검증 -------------------------------------------------------------

Validator = Callable[[Any], str | None]  # 문제가 있으면 이유, 없으면 None


def _int_range(lo: int, hi: int) -> Validator:
    def check(v: Any) -> str | None:
        if isinstance(v, bool) or not isinstance(v, int) or not lo <= v <= hi:
            return f"{lo}~{hi} 사이 정수여야 합니다"
        return None

    return check


def _choice(*options: str) -> Validator:
    def check(v: Any) -> str | None:
        if v not in options:
            return " / ".join(f'"{o}"' for o in options) + " 중 하나여야 합니다"
        return None

    return check


def _bool(v: Any) -> str | None:
    return None if isinstance(v, bool) else "true 또는 false여야 합니다"


def _str(v: Any) -> str | None:
    return None if isinstance(v, str) else '문자열("...")이어야 합니다'


def _int(v: Any) -> str | None:
    if isinstance(v, bool) or not isinstance(v, int):
        return "정수여야 합니다"
    return None


def _non_negative(v: Any) -> str | None:
    if isinstance(v, bool) or not isinstance(v, int | float) or v < 0:
        return "0 이상의 숫자여야 합니다"
    return None


def _suffix(v: Any) -> str | None:
    if not isinstance(v, str) or not v:
        return "비어 있지 않은 문자열이어야 합니다"
    bad = sorted({c for c in v if c in FORBIDDEN_FILENAME_CHARS})
    if bad:
        return f"파일명에 쓸 수 없는 문자가 있습니다: {' '.join(bad)}"
    return None


_VALIDATORS: dict[str, Validator] = {
    "config_version": _int,
    "columns": _int_range(1, 20),
    "rows": _int_range(1, 20),
    "width": _int_range(320, 8000),
    "gap": _int_range(0, 100),
    "theme": _choice("light", "dark"),
    "language": _choice("en", "ko"),
    "format": _choice("webp", "jpg", "png"),
    "quality": _int_range(1, 100),
    "suffix": _suffix,
    "output_dir": _str,
    "overwrite": _bool,
    "show_timestamp": _bool,
    "recursive": _bool,
    "skip_start_seconds": _non_negative,
    "skip_end_seconds": _non_negative,
    "font": _str,
    "ffmpeg_dir": _str,
    "close_delay_seconds": _int,
}
_HEADER_KEYS = [f.name for f in fields(HeaderSettings)]


def defaults_dict() -> dict[str, Any]:
    """기본 설정을 파일에 쓸 모양(dict)으로."""
    return _to_dict(Settings())


def _to_dict(settings: Settings) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for f in fields(Settings):
        value = getattr(settings, f.name)
        if isinstance(value, HeaderSettings):
            value = {k: getattr(value, k) for k in _HEADER_KEYS}
        data[f.name] = value
    return data


def _show(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _validate(data: dict[str, Any]) -> list[str]:
    """dict의 키별 오류 목록 ("키: 이유 (현재: 값)")."""
    errors = []
    for key, check in _VALIDATORS.items():
        if key in data and (reason := check(data[key])):
            errors.append(f"{key}: {reason} (현재: {_show(data[key])})")
    header = data.get("header")
    if "header" in data and not isinstance(header, dict):
        errors.append('header: {"file_name": true, ...} 형태여야 합니다')
    elif isinstance(header, dict):
        for key in _HEADER_KEYS:
            if key in header and (reason := _bool(header[key])):
                errors.append(f"header.{key}: {reason} (현재: {_show(header[key])})")
    return errors


def _from_dict(data: dict[str, Any]) -> Settings:
    """검증을 통과한 dict(빠진 키는 기본값)로 Settings를 만든다."""
    values = {k: v for k, v in data.items() if k in _VALIDATORS}
    header = HeaderSettings(
        **{k: v for k, v in data.get("header", {}).items() if k in _HEADER_KEYS}
    )
    return Settings(**values, header=header)


# --- 파일 위치 -------------------------------------------------------------


def _appdata_config() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "VidGlance" / CONFIG_NAME


def _can_write(folder: Path) -> bool:
    """폴더에 실제로 파일을 만들 수 있는지 (Program Files 등은 os.access가 믿을 수 없다)."""
    probe = folder / f".vidglance_write_test_{os.getpid()}"
    try:
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_config_path(explicit: str | None = None) -> Path:
    """spec §3.1: --config → exe 옆 → (exe 폴더에 쓸 수 없으면) %APPDATA%."""
    if explicit:
        return Path(explicit).resolve()
    beside = paths.app_dir() / CONFIG_NAME
    appdata = _appdata_config()
    if beside.is_file():
        return beside
    if appdata.is_file():
        return appdata
    return beside if _can_write(beside.parent) else appdata


# --- 읽기·쓰기 -------------------------------------------------------------


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")


def _json_error(path: Path, e: json.JSONDecodeError) -> ConfigError:
    message = (
        f"{path}\n  {e.lineno}번째 줄 {e.colno}번째 글자: JSON 문법 오류 ({e.msg})"
    )
    if "escape" in e.msg:
        message += (
            "\n  Windows 경로의 \\는 \\\\로 두 번 쓰거나 /를 쓰세요."
            ' 예: "D:\\\\영상" 또는 "D:/영상"'
        )
    return ConfigError(message)


def load_config(path: Path) -> LoadedConfig:
    """설정 파일을 읽는다. 없으면 기본값으로 만들고, 빠진 키는 채워 다시 저장한다.

    문법·값 오류면 ConfigError (파일은 건드리지 않는다).
    """
    if not path.is_file():
        try:
            _write(path, defaults_dict())
        except OSError as e:
            raise ConfigError(f"설정 파일을 만들 수 없습니다: {path}\n  {e}") from e
        return LoadedConfig(Settings(), path, True, [])

    try:
        # 메모장이 붙이는 BOM도 허용한다
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise _json_error(path, e) from e
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"설정 파일을 읽을 수 없습니다: {path}\n  {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path}\n  설정 파일은 {{ ... }} 형태여야 합니다")

    errors = _validate(data)
    if errors:
        lines = "\n".join(f"  - {e}" for e in errors)
        raise ConfigError(f"{path}\n{lines}")

    warnings = [
        f"모르는 설정 키(무시함): {k}"
        for k in data
        if k not in _VALIDATORS and k != "header"
    ]
    header = data.get("header", {})
    warnings += [
        f"모르는 설정 키(무시함): header.{k}" for k in header if k not in _HEADER_KEYS
    ]

    # 빠진 키를 기본값으로 채워 저장한다. 기존 값·모르는 키는 그대로 둔다.
    defaults = defaults_dict()
    missing = [k for k in defaults if k not in data]
    missing += [f"header.{k}" for k in _HEADER_KEYS if k not in header]
    if missing:
        merged = {k: data.get(k, v) for k, v in defaults.items()}
        merged["header"] = {**defaults["header"], **header}
        merged.update({k: v for k, v in data.items() if k not in merged})
        try:
            _write(path, merged)
        except OSError as e:
            warnings.append(
                f"빠진 설정({', '.join(missing)})을 파일에 추가하지 못했습니다: {e}"
            )

    return LoadedConfig(_from_dict(data), path, False, warnings)


def apply_overrides(settings: Settings, overrides: dict[str, Any]) -> Settings:
    """명령줄 옵션 값으로 덮어쓴다. 값은 설정 파일과 같은 규칙으로 검증한다."""
    errors = _validate(overrides)
    if errors:
        raise ConfigError("명령줄 옵션 오류:\n" + "\n".join(f"  - {e}" for e in errors))
    return replace(settings, **overrides)
