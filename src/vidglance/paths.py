"""exe 폴더·내장 리소스 경로(frozen 여부 처리).

`sys.frozen`, `sys._MEIPASS`는 이 모듈에서만 다룬다.
"""

import sys
from pathlib import Path

# 개발 중 프로젝트 루트 (src/vidglance/paths.py 기준 두 단계 위)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def is_frozen() -> bool:
    """PyInstaller로 빌드된 exe에서 실행 중인지."""
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """exe가 있는 폴더. 개발 중에는 프로젝트 루트."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return _PROJECT_ROOT


def resource_dir() -> Path:
    """내장 리소스(폰트 등)의 기준 폴더. exe에서는 압축이 풀린 임시 폴더."""
    if is_frozen():
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return _PROJECT_ROOT


def bundled_ffmpeg_dir() -> Path | None:
    """exe에 내장된 ffmpeg 폴더. 개발 중에는 내장본이 없으므로 None."""
    if is_frozen():
        return resource_dir() / "ffmpeg"
    return None
