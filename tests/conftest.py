"""spec §14 테스트 영상을 ffmpeg lavfi로 만든다.

`tests/_media/`에 한 번 만들어 두고 다음 실행부터는 재사용한다(커밋하지 않음).
만드는 방법을 바꾸면 `tests/_media/`를 지우고 다시 실행한다.
"""

from collections.abc import Callable
from pathlib import Path

import pytest

from vidglance import ffmpeg

MEDIA_DIR = Path(__file__).parent / "_media"

_X264 = ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p"]
_AAC = ["-c:a", "aac", "-b:a", "64k"]


def _video(size: str, rate: int, duration: float) -> list[str]:
    return [
        "-f",
        "lavfi",
        "-i",
        f"testsrc2=size={size}:rate={rate}:duration={duration}",
    ]


def _audio(duration: float) -> list[str]:
    return ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]


# 이름 → ffmpeg 입력·출력 옵션 (출력 경로는 마지막에 붙인다)
_RECIPES: dict[str, list[str]] = {
    "기본_1080p30.mp4": [*_video("1920x1080", 30, 60), *_audio(60), *_X264, *_AAC],
    "무음.mp4": [*_video("320x240", 25, 10), *_X264, "-an"],
    "세로_720x1280.mp4": [*_video("720x1280", 30, 10), *_audio(10), *_X264, *_AAC],
    "짧음_1초.mp4": [*_video("320x240", 30, 1), *_audio(1), *_X264, *_AAC],
    # 3~6초 구간만 프레임을 절반 버려 가변 프레임으로 만든다
    "가변프레임.mkv": [
        *_video("320x240", 30, 10),
        *_audio(10),
        "-vf",
        "select='not(between(t,3,6)*mod(n,2))'",
        "-fps_mode",
        "vfr",
        *_X264,
        *_AAC,
    ],
    # 640x480 저장, SAR 4:3 → 표시 비율 16:9
    "애너모픽.mp4": [
        *_video("640x480", 25, 10),
        *_audio(10),
        "-vf",
        "setsar=4/3",
        *_X264,
        *_AAC,
    ],
    "공백 과 특수문자 (1)&.mp4": [*_video("320x240", 25, 5), *_audio(5), *_X264, *_AAC],
}


def _generate(tools: ffmpeg.Tools, name: str, out: Path) -> None:
    tmp = out.with_name(f".tmp_{out.name}")
    if name == "회전90.mp4":
        # 640x360으로 만든 뒤 회전 메타데이터(90°)만 붙인다
        src = out.with_name(".tmp_회전원본.mp4")
        _ffmpeg(tools, [*_video("640x360", 25, 5), *_audio(5), *_X264, *_AAC], src)
        _ffmpeg(tools, ["-display_rotation", "90", "-i", str(src), "-c", "copy"], tmp)
        src.unlink()
    elif name == "깨짐.mp4":
        # moov가 파일 끝에 있는 mp4의 앞 절반만 남긴다 → ffprobe가 읽지 못함
        src = out.with_name(".tmp_깨짐원본.mp4")
        _ffmpeg(tools, [*_video("320x240", 25, 5), *_audio(5), *_X264, *_AAC], src)
        data = src.read_bytes()
        tmp.write_bytes(data[: len(data) // 2])
        src.unlink()
    else:
        _ffmpeg(tools, _RECIPES[name], tmp)
    tmp.replace(out)


def _ffmpeg(tools: ffmpeg.Tools, args: list[str], out: Path) -> None:
    cmd = [tools.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", *args, out]
    result = ffmpeg.run(cmd, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(
            f"테스트 영상 생성 실패: {out.name}\n{ffmpeg.decode(result.stderr)}"
        )


MEDIA_NAMES: list[str] = [*_RECIPES, "회전90.mp4", "깨짐.mp4"]


@pytest.fixture(scope="session")
def tools() -> ffmpeg.Tools:
    try:
        return ffmpeg.find_tools()
    except ffmpeg.FFmpegNotFoundError as e:
        pytest.skip(f"ffmpeg 없음: {e}")


@pytest.fixture(scope="session")
def media(tools: ffmpeg.Tools) -> Callable[[str], Path]:
    """`media("기본_1080p30.mp4")`처럼 테스트 영상 경로를 돌려준다. 없으면 만든다."""
    MEDIA_DIR.mkdir(exist_ok=True)
    for name in MEDIA_NAMES:
        out = MEDIA_DIR / name
        if not out.exists():
            _generate(tools, name, out)

    def get(name: str) -> Path:
        assert name in MEDIA_NAMES, f"알 수 없는 테스트 영상: {name}"
        return MEDIA_DIR / name

    return get
