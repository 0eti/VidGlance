import sys
from pathlib import Path

import pytest

from vidglance import paths


def test_dev_paths_point_to_project_root() -> None:
    root = paths.app_dir()
    assert (root / "pyproject.toml").is_file()
    assert paths.resource_dir() == root
    assert paths.bundled_ffmpeg_dir() is None


def test_frozen_paths(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "한글 폴더"
    meipass = tmp_path / "_MEI123"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "VidGlance.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)

    assert paths.is_frozen()
    assert paths.app_dir() == exe_dir.resolve()
    assert paths.resource_dir() == meipass
    assert paths.bundled_ffmpeg_dir() == meipass / "ffmpeg"
