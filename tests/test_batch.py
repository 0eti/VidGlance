import shutil
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import pytest
from PIL import Image

from vidglance import ffmpeg, fonts
from vidglance.batch import (
    Context,
    InputItem,
    Status,
    collect_inputs,
    output_path,
    process_video,
)
from vidglance.config import Settings

# --- collect_inputs ---


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "영상 폴더"
    (root / "하위").mkdir(parents=True)
    for name in ["10화.mp4", "2화.mp4", "UPPER.MKV", "2화_sheet.webp", "메모.txt"]:
        (root / name).write_bytes(b"")
    (root / "하위" / "3화.mp4").write_bytes(b"")
    return root


def _names(items: list[InputItem]) -> list[str]:
    return [i.path.name for i in items]


def test_collect_folder_filters_and_sorts(folder: Path) -> None:
    items = collect_inputs([str(folder)], recursive=False, suffix="_sheet")
    assert _names(items) == ["2화.mp4", "10화.mp4", "UPPER.MKV"]  # 자연 정렬
    assert all(i.error is None and i.path.is_absolute() for i in items)


def test_collect_recursive(folder: Path) -> None:
    items = collect_inputs([str(folder)], recursive=True, suffix="_sheet")
    assert "3화.mp4" in _names(items)


def test_collect_mixed_dedup_and_explicit_files(folder: Path) -> None:
    args = [
        str(folder / "2화.mp4"),  # 폴더와 중복
        str(folder),
        str(folder / "메모.txt"),  # 직접 지정한 파일은 확장자와 관계없이 넣는다
        str(folder / "2화_sheet.webp"),  # 직접 지정해도 시트는 뺀다
        str(folder / "없는 파일.mp4"),
    ]
    items = collect_inputs(args, recursive=False, suffix="_sheet")
    assert _names(items) == [
        "2화.mp4",
        "10화.mp4",
        "UPPER.MKV",
        "메모.txt",
        "없는 파일.mp4",
    ]
    assert items[-1].error == "파일 없음"


def test_collect_custom_suffix(folder: Path) -> None:
    (folder / "a_thumb.webp").write_bytes(b"")
    items = collect_inputs(
        [str(folder / "a_thumb.webp")], recursive=False, suffix="_thumb"
    )
    assert items == []


# --- output_path ---


def test_output_path_default() -> None:
    video = Path("D:/영상/예시 영상.mp4")
    assert output_path(video, Settings()) == Path("D:/영상/예시 영상_sheet.webp")


def test_output_path_options() -> None:
    video = Path("D:/영상/a.mkv")
    s = Settings(suffix="_thumb", format="png")
    assert output_path(video, s) == Path("D:/영상/a_thumb.png")
    assert output_path(video, replace(s, output_dir="thumbs")) == Path(
        "D:/영상/thumbs/a_thumb.png"
    )
    assert output_path(video, replace(s, output_dir="E:/시트")) == Path(
        "E:/시트/a_thumb.png"
    )


# --- process_video ---


@pytest.fixture(scope="module")
def ctx(tools: ffmpeg.Tools) -> Context:
    return Context(Settings(), tools.ffprobe, fonts.find_fonts())


@pytest.fixture
def copy(media: Callable[[str], Path], tmp_path: Path) -> Callable[[str, str], Path]:
    def get(name: str, as_name: str = "") -> Path:
        dst = tmp_path / (as_name or name)
        shutil.copy2(media(name), dst)
        return dst

    return get


def test_process_done(copy: Callable[..., Path], ctx: Context) -> None:
    video = copy("무음.mp4", "한글 영상 (1)&.mp4")
    result = process_video(video, ctx)
    assert result.status is Status.DONE, result.message
    assert result.output == video.with_name("한글 영상 (1)&_sheet.webp")
    with Image.open(result.output) as sheet:
        assert sheet.format == "WEBP"
        assert sheet.width == 1024
    assert set(result.timings) == {"probe", "extract", "render", "save"}
    assert result.warnings == []


def test_process_skips_existing_then_overwrites(
    copy: Callable[..., Path], ctx: Context
) -> None:
    video = copy("무음.mp4")
    existing = video.with_name("무음_sheet.webp")
    existing.write_bytes(b"old")
    result = process_video(video, ctx)
    assert (result.status, result.message) == (Status.SKIPPED, "이미 있음")
    assert existing.read_bytes() == b"old"

    result = process_video(video, replace(ctx, settings=Settings(overwrite=True)))
    assert result.status is Status.DONE
    assert existing.read_bytes() != b"old"


def test_process_broken_video_fails(copy: Callable[..., Path], ctx: Context) -> None:
    result = process_video(copy("깨짐.mp4"), ctx)
    assert result.status is Status.FAILED
    assert "영상을 읽을 수 없음" in result.message


def test_process_non_video_is_skipped(tmp_path: Path, ctx: Context) -> None:
    doc = tmp_path / "메모.txt"
    doc.write_text("영상 아님", encoding="utf-8")
    result = process_video(doc, ctx)
    assert result.status is Status.SKIPPED
    assert result.message.startswith("영상 아님")


def test_process_output_dir_created(copy: Callable[..., Path], ctx: Context) -> None:
    video = copy("짧음_1초.mp4")
    s = Settings(output_dir="시트 모음", format="jpg")
    result = process_video(video, replace(ctx, settings=s))
    assert result.status is Status.DONE
    assert result.output == video.parent / "시트 모음" / "짧음_1초_sheet.jpg"
    assert result.output.is_file()
    assert "영상이 짧아 20칸 중 9칸만 채웁니다" in result.warnings


def test_process_layout_error_fails(copy: Callable[..., Path], ctx: Context) -> None:
    s = Settings(width=320, columns=20, gap=100)
    result = process_video(copy("무음.mp4"), replace(ctx, settings=s))
    assert result.status is Status.FAILED
    assert "너무 작습니다" in result.message


def test_process_webp_height_limit(copy: Callable[..., Path], ctx: Context) -> None:
    # 세로 영상 1열 20행 → 높이가 16383을 넘어 너비를 줄인다
    s = Settings(columns=1, rows=20)
    result = process_video(copy("세로_720x1280.mp4"), replace(ctx, settings=s))
    assert result.status is Status.DONE
    assert any("WebP 최대 높이" in w for w in result.warnings)
    with Image.open(result.output) as sheet:  # type: ignore[arg-type]
        assert sheet.height <= 16383
