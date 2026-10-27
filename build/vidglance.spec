# PyInstaller 설정: VidGlance.exe (onefile, 콘솔 앱)
# 빌드는 `uv run python build/build.py`로 한다 (ffprobe 받기 → 이 spec 빌드).
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 (PyInstaller가 넣어 주는 이름)

a = Analysis(  # noqa: F821
    [str(ROOT / "src" / "vidglance" / "__main__.py")],
    pathex=[str(ROOT / "src")],
    # 실행 시 sys._MEIPASS 아래 경로 = paths.py가 찾는 경로
    binaries=[(str(ROOT / "build" / "ffmpeg" / "ffprobe.exe"), "ffmpeg")],
    datas=[(str(ROOT / "assets" / "fonts"), "assets/fonts")],
    excludes=["tkinter", "unittest", "pydoc", "numpy"],
)
pyz = PYZ(a.pure)  # noqa: F821
exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="VidGlance",
    console=True,
    icon=str(ROOT / "assets" / "icon.ico"),
    upx=False,
)
