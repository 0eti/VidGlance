"""exe 빌드: 내장용 ffprobe 받기(없을 때만) → PyInstaller.

    uv run python build/build.py

결과: dist/VidGlance.exe (작업 폴더는 build/work/)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    subprocess.run([sys.executable, ROOT / "build" / "fetch_ffmpeg.py"], check=True)
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller", ROOT / "build" / "vidglance.spec",
            "--noconfirm", "--clean",
            "--distpath", ROOT / "dist",
            "--workpath", ROOT / "build" / "work",
        ],
        check=True,
    )  # fmt: skip
    exe = ROOT / "dist" / "VidGlance.exe"
    print(f"\n완료: {exe} ({exe.stat().st_size / 2**20:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
