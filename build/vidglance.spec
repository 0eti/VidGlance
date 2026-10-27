# PyInstaller 설정: VidGlance.exe (콘솔 앱)
# 빌드는 `uv run python build/build.py`로 한다 (ffprobe 받기 → onefile, onedir 두 번 빌드).
# 환경 변수 VIDGLANCE_ONEDIR=1이면 onedir(dist/VidGlance/), 아니면 onefile(dist/VidGlance.exe).
import os
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 (PyInstaller가 넣어 주는 이름)
ONEDIR = os.environ.get("VIDGLANCE_ONEDIR") == "1"

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "vidglance" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    # 실행 시 sys._MEIPASS 아래 경로 = paths.py가 찾는 경로
    binaries=[(str(ROOT / "build" / "ffmpeg" / "ffprobe.exe"), "ffmpeg")],
    datas=[
        (str(ROOT / "assets" / "fonts"), "assets/fonts"),
        (str(ROOT / "build" / "ffmpeg" / "LICENSE"), "ffmpeg"),  # ffprobe GPL 원문
    ],
    excludes=["tkinter", "unittest", "pydoc", "numpy"],
)
pyz = PYZ(a.pure)  # noqa: F821
options = {
    "name": "VidGlance",
    "console": True,
    "icon": str(ROOT / "assets" / "icon.ico"),
    "upx": False,
}

if ONEDIR:
    # 폴더 배포: VidGlance.exe + _internal/ (실행마다 압축을 풀지 않아 시작이 빠르다)
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **options)  # noqa: F821
    coll = COLLECT(exe, a.binaries, a.datas, name="VidGlance", upx=False)  # noqa: F821
else:
    # 파일 하나 배포: 실행마다 임시 폴더에 내장 파일을 푼다
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], **options)  # noqa: F821
