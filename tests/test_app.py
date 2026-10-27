"""엔드투엔드: 인자는 드래그앤드롭과 같은 절대 경로 목록이다."""

import json
import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from PIL import Image

from vidglance import __version__, app, batch, ffmpeg
from vidglance.app import EXIT_FAILED, EXIT_OK, EXIT_SETUP, main


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"VidGlance {__version__}"


@pytest.fixture
def workspace(media: Callable[[str], Path], tmp_path: Path) -> dict[str, Path]:
    """영상 2개(각자 다른 폴더) + 영상이 든 폴더 1개 + 설정 파일 경로."""
    a_dir = tmp_path / "영상 A"
    folder = tmp_path / "폴더 & 묶음"
    (folder / "하위").mkdir(parents=True)
    a_dir.mkdir()
    files = {
        "a": a_dir / "첫 번째 영상.mp4",
        "b": tmp_path / "공백 과 특수문자 (1)&.mp4",
        "c1": folder / "1화.mp4",
        "c2": folder / "2화.mkv",
        "deep": folder / "하위" / "3화.mp4",
    }
    shutil.copy2(media("무음.mp4"), files["a"])
    shutil.copy2(media("공백 과 특수문자 (1)&.mp4"), files["b"])
    shutil.copy2(media("짧음_1초.mp4"), files["c1"])
    shutil.copy2(media("가변프레임.mkv"), files["c2"])
    shutil.copy2(media("무음.mp4"), files["deep"])
    return {**files, "folder": folder, "config": tmp_path / "설정" / "config.json"}


def _run(ws: dict[str, Path], *args: str) -> int:
    return main(["--no-pause", "--config", str(ws["config"]), *args])


def _sheet(video: Path, ext: str = "webp") -> Path:
    return video.with_name(f"{video.stem}_sheet.{ext}")


def test_files_and_folder_in_one_run(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    ws = workspace
    code = _run(ws, str(ws["a"]), str(ws["b"]), str(ws["folder"]))
    out = capsys.readouterr().out

    assert code == EXIT_OK, out
    for key in ("a", "b", "c1", "c2"):
        assert _sheet(ws[key]).is_file(), key
    assert not _sheet(ws["deep"]).exists()  # recursive가 꺼져 있다
    assert ws["config"].is_file()  # 설정 파일을 새로 만든다
    assert "(새로 만듦)" in out
    assert "4x5, 1024px, webp" in out
    # 전체 경로 기준 자연 정렬 순서로 처리한다
    order = ["공백 과 특수문자 (1)&.mp4", "첫 번째 영상.mp4", "1화.mp4", "2화.mkv"]
    for i, name in enumerate(order, 1):
        assert f"[{i}/4] {name} … 완료" in out
    assert "→ 첫 번째 영상_sheet.webp" in out
    assert "경고: 영상이 짧아 20칸 중 9칸만 채웁니다" in out
    assert "완료 4, 건너뜀 0, 실패 0" in out

    # 다시 실행하면 전부 건너뛴다
    assert _run(ws, str(ws["a"]), str(ws["b"]), str(ws["folder"])) == EXIT_OK
    out = capsys.readouterr().out
    assert out.count("건너뜀 (이미 있음)") == 4
    assert "완료 0, 건너뜀 4, 실패 0" in out


def test_config_changes_apply_next_run(workspace: dict[str, Path]) -> None:
    ws = workspace
    assert _run(ws, str(ws["a"])) == EXIT_OK
    with Image.open(_sheet(ws["a"])) as first:
        first_size = first.size

    data = json.loads(ws["config"].read_text(encoding="utf-8"))
    data.update({"gap": 0, "columns": 5, "rows": 6, "overwrite": True})
    data["header"] = dict.fromkeys(data["header"], False)
    ws["config"].write_text(json.dumps(data), encoding="utf-8")

    assert _run(ws, str(ws["a"])) == EXIT_OK
    with Image.open(_sheet(ws["a"])) as second:
        # 5열·간격 0 → 칸 (1024 − 20) / 5 = 200, 4:3 → 150. 헤더 없음 → 10 + 6×150 + 10
        assert second.size == (1024, 10 + 6 * 150 + 10)
    assert second.size != first_size


def test_recursive_option(workspace: dict[str, Path]) -> None:
    ws = workspace
    assert _run(ws, "-r", str(ws["folder"])) == EXIT_OK
    assert _sheet(ws["deep"]).is_file()


def test_cli_overrides(workspace: dict[str, Path]) -> None:
    ws = workspace
    code = _run(ws, "-g", "2x2", "--format", "png", "--theme", "dark", str(ws["a"]))
    assert code == EXIT_OK
    with Image.open(_sheet(ws["a"], "png")) as sheet:
        assert sheet.format == "PNG"
        assert sheet.getpixel((1, 1)) == (0x1E, 0x1E, 0x1E)
    # 명령줄 옵션은 설정 파일을 바꾸지 않는다
    assert json.loads(ws["config"].read_text(encoding="utf-8"))["columns"] == 4


def test_failures_continue_and_exit_1(
    workspace: dict[str, Path],
    media: Callable[[str], Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    ws = workspace
    broken = ws["a"].with_name("깨진 영상.mp4")
    shutil.copy2(media("깨짐.mp4"), broken)
    doc = ws["a"].with_name("메모.txt")
    doc.write_text("영상 아님", encoding="utf-8")
    missing = ws["a"].with_name("없는 영상.mp4")

    code = _run(ws, str(broken), str(ws["a"]), str(doc), str(missing))
    out = capsys.readouterr().out

    assert code == EXIT_FAILED
    assert _sheet(ws["a"]).is_file()  # 실패가 있어도 나머지는 처리한다
    assert "깨진 영상.mp4 … 실패: 영상을 읽을 수 없음" in out
    assert "메모.txt … 건너뜀 (영상 아님" in out
    assert "없는 영상.mp4 … 실패: 파일 없음" in out
    assert "완료 1, 건너뜀 1, 실패 2" in out


def test_quiet_prints_summary_only(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    ws = workspace
    assert _run(ws, "-q", str(ws["a"])) == EXIT_OK
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("완료 1, 건너뜀 0, 실패 0")


def test_verbose_prints_tools_and_timings(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    ws = workspace
    assert _run(ws, "-v", str(ws["a"])) == EXIT_OK
    out = capsys.readouterr().out
    assert "ffprobe: " in out and "ffprobe version" in out
    assert "PyAV " in out
    assert "폰트: " in out
    assert "probe " in out and "추출 " in out and "렌더 " in out and "저장 " in out


def test_no_inputs_creates_config_and_shows_usage(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    ws = workspace
    assert _run(ws) == EXIT_OK
    out = capsys.readouterr().out
    assert "끌어다 놓으세요" in out
    assert str(ws["config"]) in out
    assert ws["config"].is_file()


def test_invalid_config_exit_2_untouched(
    workspace: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    ws = workspace
    ws["config"].parent.mkdir(parents=True)
    ws["config"].write_text('{"columns": 0}', encoding="utf-8")
    assert _run(ws, str(ws["a"])) == EXIT_SETUP
    out = capsys.readouterr().out
    assert "설정 오류" in out and "columns: 1~20" in out
    assert ws["config"].read_text(encoding="utf-8") == '{"columns": 0}'
    assert not _sheet(ws["a"]).exists()


def test_invalid_cli_value_exit_2(workspace: dict[str, Path]) -> None:
    ws = workspace
    assert _run(ws, "--quality", "0", str(ws["a"])) == EXIT_SETUP
    with pytest.raises(SystemExit) as exc:
        _run(ws, "-g", "4by5", str(ws["a"]))
    assert exc.value.code == EXIT_SETUP


def test_ffprobe_missing_exit_2(
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def not_found(name: str, ffmpeg_dir: object = None) -> Path:
        raise ffmpeg.FFmpegNotFoundError("ffprobe.exe", ["PATH 환경 변수"])

    monkeypatch.setattr(ffmpeg, "find_tool", not_found)
    ws = workspace
    assert _run(ws, str(ws["a"])) == EXIT_SETUP
    assert "ffprobe.exe를 찾을 수 없습니다" in capsys.readouterr().out


def test_nothing_to_process(
    workspace: dict[str, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty = tmp_path / "빈 폴더"
    empty.mkdir()
    assert _run(workspace, str(empty)) == EXIT_OK
    assert "처리할 영상이 없습니다" in capsys.readouterr().out


# --- 창 대기 (spec §2.4) ---


@pytest.fixture
def waits(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """키 대기·카운트다운 호출을 기록한다 (실제로 기다리지 않는다)."""
    calls: list[str] = []
    monkeypatch.setattr(app, "_wait_key", lambda *a: calls.append("key"))
    monkeypatch.setattr(app, "_countdown", lambda s: calls.append(f"countdown {s}"))
    return calls


@pytest.mark.parametrize(
    ("pause", "ok", "delay", "expected"),
    [
        (False, False, 3, []),  # 터미널 실행 / --no-pause
        (True, True, 3, ["countdown 3"]),  # 모두 성공 → 카운트다운
        (True, True, 0, []),  # 0이면 바로 닫힘
        (True, True, -1, ["key"]),  # 음수면 항상 키 대기
        (True, False, 3, ["key"]),  # 실패가 있으면 키 대기
    ],
)
def test_finish_rules(
    waits: list[str], pause: bool, ok: bool, delay: int, expected: list[str]
) -> None:
    app._finish(pause, ok, delay)
    assert waits == expected


def test_drag_and_drop_window_counts_down(
    workspace: dict[str, Path], waits: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "owns_console", lambda: True)  # 새로 열린 창
    ws = workspace
    assert main(["--config", str(ws["config"]), str(ws["a"])]) == EXIT_OK
    assert waits == ["countdown 3"]


def test_drag_and_drop_config_error_waits_for_key(
    workspace: dict[str, Path], waits: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(app, "owns_console", lambda: True)
    ws = workspace
    ws["config"].parent.mkdir(parents=True)
    ws["config"].write_text("{", encoding="utf-8")
    assert main(["--config", str(ws["config"]), str(ws["a"])]) == EXIT_SETUP
    assert waits == ["key"]


def test_terminal_does_not_wait(workspace: dict[str, Path], waits: list[str]) -> None:
    # pytest는 터미널(다른 프로세스와 같은 콘솔)이나 파이프에서 돈다 → 기다리지 않는다
    assert app.owns_console() is False
    ws = workspace
    assert main(["--config", str(ws["config"]), str(ws["a"])]) == EXIT_OK
    assert waits == []


# --- 중단·예기치 않은 오류 ---


def test_interrupt_stops_batch(
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ws = workspace
    real = batch.process_video
    calls: list[Path] = []

    def interrupt_second(video: Path, ctx: batch.Context) -> batch.Result:
        calls.append(video)
        if len(calls) == 2:
            raise KeyboardInterrupt  # Ctrl+C·창 닫기(SIGBREAK)
        return real(video, ctx)

    monkeypatch.setattr(app, "process_video", interrupt_second)
    code = _run(ws, str(ws["a"]), str(ws["b"]), str(ws["folder"]))
    out = capsys.readouterr().out

    assert code == EXIT_FAILED
    assert len(calls) == 2  # 나머지는 처리하지 않는다
    assert "… 중단" in out
    assert out.strip().endswith("— 중단됨")
    leftovers = [p for p in ws["a"].parent.parent.rglob("*.tmp")]
    assert leftovers == []


def test_unexpected_error_does_not_stop_batch(
    workspace: dict[str, Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    ws = workspace
    real = batch.process_video

    def broken_for_b(video: Path, ctx: batch.Context) -> batch.Result:
        if video == ws["b"]:
            raise RuntimeError("뜻밖의 문제")
        return real(video, ctx)

    monkeypatch.setattr(app, "process_video", broken_for_b)
    code = _run(ws, str(ws["a"]), str(ws["b"]))
    out = capsys.readouterr().out

    assert code == EXIT_FAILED
    assert "실패: 예기치 않은 오류: RuntimeError('뜻밖의 문제')" in out
    assert _sheet(ws["a"]).is_file()
    assert "완료 1, 건너뜀 0, 실패 1" in out


def test_backend_version_in_verbose() -> None:
    from vidglance.extract import backend_version

    assert backend_version().startswith("PyAV ")
    assert "(FFmpeg " in backend_version()
