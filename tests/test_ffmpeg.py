from pathlib import Path

import pytest

from vidglance import ffmpeg, paths


def _make_exe(folder: Path, name: str = "ffmpeg") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    exe = folder / f"{name}.exe"
    exe.write_bytes(b"")
    return exe


@pytest.fixture
def dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    """설정/exe 옆/PATH/내장 네 위치를 임시 폴더로 바꾼다 (처음엔 모두 비어 있음)."""
    d = {
        "config": tmp_path / "설정 폴더",
        "app": tmp_path / "app",
        "path": tmp_path / "on path",
        "bundled": tmp_path / "_MEI" / "ffmpeg",
    }
    for folder in d.values():
        folder.mkdir(parents=True)
    monkeypatch.setattr(paths, "app_dir", lambda: d["app"])
    monkeypatch.setattr(paths, "bundled_ffmpeg_dir", lambda: d["bundled"])
    monkeypatch.setenv("PATH", str(d["path"]))
    return d


def test_search_order(dirs: dict[str, Path]) -> None:
    bundled = _make_exe(dirs["bundled"])
    assert ffmpeg.find_tool("ffmpeg", dirs["config"]) == bundled

    on_path = _make_exe(dirs["path"])
    assert ffmpeg.find_tool("ffmpeg", dirs["config"]) == on_path.resolve()

    beside = _make_exe(dirs["app"])
    assert ffmpeg.find_tool("ffmpeg", dirs["config"]) == beside.resolve()

    configured = _make_exe(dirs["config"])
    assert ffmpeg.find_tool("ffmpeg", dirs["config"]) == configured.resolve()


def test_empty_ffmpeg_dir_is_skipped(dirs: dict[str, Path]) -> None:
    beside = _make_exe(dirs["app"])
    assert ffmpeg.find_tool("ffmpeg", "") == beside.resolve()


def test_ffmpeg_and_ffprobe_found_separately(dirs: dict[str, Path]) -> None:
    mpeg = _make_exe(dirs["app"], "ffmpeg")
    probe = _make_exe(dirs["bundled"], "ffprobe")
    tools = ffmpeg.find_tools()
    assert tools.ffmpeg == mpeg.resolve()
    assert tools.ffprobe == probe


def test_not_found_lists_searched_places(dirs: dict[str, Path]) -> None:
    with pytest.raises(ffmpeg.FFmpegNotFoundError) as exc:
        ffmpeg.find_tool("ffprobe", dirs["config"])
    message = str(exc.value)
    assert "ffprobe.exe" in message
    assert str(dirs["config"]) in message
    assert str(dirs["app"]) in message
    assert "PATH" in message
    assert str(dirs["bundled"]) in message


def test_run_real_ffmpeg_with_list_args() -> None:
    tool = ffmpeg.find_tool("ffmpeg")
    result = ffmpeg.run([tool, "-hide_banner", "-version"])
    assert result.returncode == 0
    assert ffmpeg.version(tool).startswith("ffmpeg version")
