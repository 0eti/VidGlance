"""exe 빌드: 내장용 ffprobe 받기(없을 때만) → PyInstaller로 onefile, onedir 두 가지.

    uv run python build/build.py

결과:
    dist/VidGlance.exe           onefile (파일 하나, 시작마다 압축 해제 약 5초)
    dist/VidGlance/VidGlance.exe onedir  (폴더 배포, 시작 빠름)
작업 폴더는 build/work/onefile, build/work/onedir
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"


def _pyinstaller(mode: str) -> None:
    env = {**os.environ, "VIDGLANCE_ONEDIR": "1" if mode == "onedir" else "0"}
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", ROOT / "build" / "vidglance.spec",
            "--noconfirm", "--clean",
            "--distpath", DIST,
            "--workpath", ROOT / "build" / "work" / mode,
        ],
        check=True,
        env=env,
    )  # fmt: skip


def _size_mb(path: Path) -> float:
    files = [path] if path.is_file() else [p for p in path.rglob("*") if p.is_file()]
    return sum(p.stat().st_size for p in files) / 2**20


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    subprocess.run([sys.executable, ROOT / "build" / "fetch_ffmpeg.py"], check=True)
    for mode in ("onefile", "onedir"):
        _pyinstaller(mode)

    onefile, onedir = DIST / "VidGlance.exe", DIST / "VidGlance"
    print(f"\n완료:\n  onefile  {onefile} ({_size_mb(onefile):.1f} MB)")
    print(f"  onedir   {onedir / 'VidGlance.exe'} (폴더 {_size_mb(onedir):.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
