"""ffmpeg/ffprobe 실행 파일 탐색(spec §4), subprocess 래퍼.

ffmpeg 호출은 반드시 이 모듈의 `run()`을 거친다.
"""

import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vidglance import paths

# 콘솔 창이 새로 뜨지 않게 한다 (Windows 전용 플래그)
_CREATE_NO_WINDOW: int = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FFmpegNotFoundError(Exception):
    """ffmpeg/ffprobe를 어디서도 찾지 못했다."""

    def __init__(self, name: str, searched: list[str]) -> None:
        self.name = name
        self.searched = searched
        lines = "\n".join(f"  - {place}" for place in searched)
        super().__init__(f"{name}를 찾을 수 없습니다. 찾아본 위치:\n{lines}")


@dataclass(frozen=True)
class Tools:
    """사용할 ffmpeg/ffprobe 실행 파일 경로."""

    ffmpeg: Path
    ffprobe: Path


def _exe_name(name: str) -> str:
    return f"{name}.exe" if os.name == "nt" else name


def find_tool(name: str, ffmpeg_dir: str | Path | None = None) -> Path:
    """spec §4 순서(설정 → exe 옆 → PATH → 내장)로 실행 파일을 찾는다."""
    exe = _exe_name(name)
    searched: list[str] = []

    dirs: list[tuple[str, Path]] = []
    if ffmpeg_dir:
        dirs.append(("설정 ffmpeg_dir", Path(ffmpeg_dir)))
    dirs.append(("exe 폴더", paths.app_dir()))
    for label, folder in dirs:
        candidate = folder / exe
        if candidate.is_file():
            return candidate.resolve()
        searched.append(f"{label}: {candidate}")

    on_path = shutil.which(name)
    if on_path:
        return Path(on_path).resolve()
    searched.append("PATH 환경 변수")

    bundled = paths.bundled_ffmpeg_dir()
    if bundled is not None:
        candidate = bundled / exe
        if candidate.is_file():
            return candidate
        searched.append(f"내장본: {candidate}")

    raise FFmpegNotFoundError(exe, searched)


def find_tools(ffmpeg_dir: str | Path | None = None) -> Tools:
    """ffmpeg와 ffprobe를 각각 같은 규칙으로 찾는다."""
    return Tools(
        ffmpeg=find_tool("ffmpeg", ffmpeg_dir),
        ffprobe=find_tool("ffprobe", ffmpeg_dir),
    )


def run(
    args: Sequence[str | os.PathLike[str]], *, timeout: float | None = None
) -> subprocess.CompletedProcess[bytes]:
    """리스트 인자로 실행하고 stdout/stderr를 bytes로 받는다. 종료 코드는 검사하지 않는다."""
    return subprocess.run(
        [os.fspath(a) for a in args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        timeout=timeout,
        creationflags=_CREATE_NO_WINDOW,
        check=False,
    )


def decode(data: bytes) -> str:
    """ffmpeg 출력을 문자열로 바꾼다 (cp949로 디코딩되지 않게 UTF-8 고정)."""
    return data.decode("utf-8", errors="replace")


def version(tool: Path) -> str:
    """`-version` 출력의 첫 줄 (예: `ffmpeg version 9.0.2-full_build-www.gyan.dev ...`)."""
    result = run([tool, "-version"], timeout=10)
    first = decode(result.stdout).splitlines()
    return first[0] if first else ""
