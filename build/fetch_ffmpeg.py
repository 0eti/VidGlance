"""내장용 ffprobe를 받는다 (spec §4): Gyan.dev essentials 정적 빌드(Windows x64).

    uv run python build/fetch_ffmpeg.py [--force]

zip을 받아 SHA-256을 확인하고 `ffprobe.exe`와 `LICENSE`만 `build/ffmpeg/`에 꺼낸다.
받은 버전은 `build/ffmpeg_version.txt`에 기록한다.
"""

import hashlib
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import date
from pathlib import Path

BASE = "https://www.gyan.dev/ffmpeg/builds"
ZIP_URL = f"{BASE}/ffmpeg-release-essentials.zip"
SHA_URL = f"{ZIP_URL}.sha256"
VERSION_URL = f"{BASE}/release-version"

HERE = Path(__file__).resolve().parent
OUT_DIR = HERE / "ffmpeg"
VERSION_FILE = HERE / "ffmpeg_version.txt"
WANTED = {"bin/ffprobe.exe": "ffprobe.exe", "LICENSE": "LICENSE"}


def _get(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "VidGlance-build"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _download(url: str, dest: Path) -> str:
    """받으면서 SHA-256을 계산한다."""
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "VidGlance-build"})
    with urllib.request.urlopen(request, timeout=60) as response, dest.open("wb") as f:
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        while chunk := response.read(1 << 20):
            f.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {done / total:6.1%}  {done >> 20}/{total >> 20} MB", end="")
    print()
    return digest.hexdigest()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if (OUT_DIR / "ffprobe.exe").is_file() and "--force" not in sys.argv:
        print(f"이미 있음: {OUT_DIR / 'ffprobe.exe'} (다시 받으려면 --force)")
        return 0

    version = _get(VERSION_URL).decode().strip()
    expected = _get(SHA_URL).decode().split()[0].lower()
    print(f"ffmpeg {version} essentials 받는 중: {ZIP_URL}")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "ffmpeg.zip"
        actual = _download(ZIP_URL, archive)
        if actual != expected:
            print(f"SHA-256 불일치: 기대 {expected}, 실제 {actual}")
            return 1

        OUT_DIR.mkdir(exist_ok=True)
        with zipfile.ZipFile(archive) as z:
            for member in z.namelist():
                # zip 안은 "ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe" 형태
                inner = member.split("/", 1)[-1]
                if inner in WANTED:
                    with (
                        z.open(member) as src,
                        (OUT_DIR / WANTED[inner]).open("wb") as dst,
                    ):
                        shutil.copyfileobj(src, dst)
        missing = [name for name in WANTED.values() if not (OUT_DIR / name).is_file()]
        if missing:
            print(f"zip에서 찾지 못함: {missing}")
            return 1

    VERSION_FILE.write_text(
        f"ffmpeg {version} essentials_build (Gyan.dev, GPL)\n"
        f"source: {ZIP_URL}\n"
        f"sha256: {expected}\n"
        f"fetched: {date.today().isoformat()}\n",
        encoding="utf-8",
    )
    print(f"완료: {OUT_DIR / 'ffprobe.exe'}\n버전 기록: {VERSION_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
