"""진입점: 인자 파싱, 콘솔 출력, 창 대기, 종료 코드 (spec §2, §10, §11).

print·입력 대기·종료 코드는 이 모듈에서만 다룬다.
"""

import argparse
import ctypes
import os
import signal
import sys
import time
from typing import Any

from vidglance import __version__, ffmpeg, fonts
from vidglance.batch import Context, Result, Status, collect_inputs, process_video
from vidglance.config import (
    ConfigError,
    LoadedConfig,
    Settings,
    apply_overrides,
    load_config,
    resolve_config_path,
)
from vidglance.extract import backend_version

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_SETUP = 2  # 설정 오류·ffprobe 없음·잘못된 인자

RULE = "─" * 10


def _grid(text: str) -> tuple[int, int]:
    try:
        columns, rows = (int(x) for x in text.lower().split("x"))
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"격자는 4x5 형식이어야 합니다: {text}"
        ) from None
    return columns, rows


def build_parser() -> argparse.ArgumentParser:
    """spec §10. 지정한 옵션은 config.json 값을 덮어쓴다."""
    p = argparse.ArgumentParser(
        prog="VidGlance",
        description="영상 파일·폴더마다 정보 헤더 + 프레임 격자 시트를 만듭니다.",
    )
    p.add_argument("inputs", nargs="*", help="영상 파일 또는 폴더")
    p.add_argument("-g", "--grid", type=_grid, metavar="CxR", help="격자 (예: 4x5)")
    p.add_argument("-w", "--width", type=int, metavar="PX")
    p.add_argument("--gap", type=int, metavar="PX")
    p.add_argument("--theme", choices=["light", "dark"])
    p.add_argument("--lang", choices=["en", "ko"])
    p.add_argument("-o", "--output-dir", metavar="DIR")
    p.add_argument("-r", "--recursive", action="store_true", default=None)
    p.add_argument("--format", choices=["webp", "jpg", "png"])
    p.add_argument("--quality", type=int, metavar="N")
    p.add_argument("--overwrite", action="store_true", default=None)
    p.add_argument("--no-timestamp", action="store_true")
    p.add_argument("--font", metavar="PATH")
    p.add_argument("--seek", choices=["fast", "accurate"], help="프레임 고르는 방식")
    p.add_argument("--ffmpeg-dir", metavar="DIR")
    p.add_argument("--config", metavar="PATH", help="설정 파일 직접 지정")
    p.add_argument("--no-pause", action="store_true", help="끝나고 기다리지 않음")
    p.add_argument("-q", "--quiet", action="store_true", help="요약만 출력")
    p.add_argument(
        "-v", "--verbose", action="store_true", help="ffprobe 경로·단계별 시간 출력"
    )
    p.add_argument("--version", action="version", version=f"VidGlance {__version__}")
    return p


def _overrides(args: argparse.Namespace) -> dict[str, Any]:
    """명령줄에서 지정한 값만 설정 키 이름으로."""
    values: dict[str, Any] = {
        "width": args.width,
        "gap": args.gap,
        "theme": args.theme,
        "language": args.lang,
        "output_dir": args.output_dir,
        "recursive": args.recursive,
        "format": args.format,
        "quality": args.quality,
        "overwrite": args.overwrite,
        "font": args.font,
        "seek_mode": args.seek,
        "ffmpeg_dir": args.ffmpeg_dir,
    }
    if args.grid:
        values["columns"], values["rows"] = args.grid
    if args.no_timestamp:
        values["show_timestamp"] = False
    return {k: v for k, v in values.items() if v is not None}


# --- 콘솔 창 ---------------------------------------------------------------


def _process_image(pid: int) -> str | None:
    """프로세스의 실행 파일 경로 (Windows)."""
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return None
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = ctypes.c_uint32(len(buf))
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return buf.value
        return None
    finally:
        kernel32.CloseHandle(handle)


def owns_console() -> bool:
    """이 프로그램을 위해 새로 열린 콘솔 창인지 (드래그·더블클릭). spec §2.4."""
    if os.name != "nt":
        return False
    try:
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        buf = (ctypes.c_uint32 * 16)()
        count = kernel32.GetConsoleProcessList(buf, len(buf))
    except (AttributeError, OSError):
        return False
    if count == 0 or count > len(buf):
        return False
    others = set(buf[:count]) - {os.getpid()}
    # 같은 실행 파일인 부모(onefile exe의 부트로더, venv의 python.exe 런처)는
    # 이 프로그램의 일부이므로 빼고 센다
    parent = os.getppid()
    if parent in others:
        image = _process_image(parent)
        if image and os.path.normcase(image) == os.path.normcase(sys.executable):
            others.discard(parent)
    return not others


def _wait_key(message: str = "아무 키나 누르면 닫힙니다…") -> None:
    import msvcrt

    print(message, flush=True)
    msvcrt.getwch()


def _countdown(seconds: int) -> None:
    import msvcrt

    for left in range(seconds, 0, -1):
        print(
            f"\r{left}초 뒤 닫힙니다… (아무 키나 누르면 바로 닫힘)", end="", flush=True
        )
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if msvcrt.kbhit():
                msvcrt.getwch()
                print()
                return
            time.sleep(0.05)
    print()


def _finish(pause: bool, ok: bool, delay: int) -> None:
    """spec §2.4: 실패가 있거나 delay < 0이면 키 대기, 아니면 카운트다운."""
    if not pause:
        return
    if not ok or delay < 0:
        _wait_key()
    elif delay > 0:
        _countdown(delay)


def _raise_interrupt(signum: int, frame: Any) -> None:
    raise KeyboardInterrupt


# --- 출력 -------------------------------------------------------------------


def _describe(result: Result) -> str:
    seconds = f"{result.seconds:.1f}s"
    if result.status is Status.DONE and result.output is not None:
        return f"완료 ({seconds}) → {result.output.name}"
    if result.status is Status.SKIPPED:
        return f"건너뜀 ({result.message})"
    return f"실패: {result.message}"


def _timings(result: Result) -> str:
    names = {"probe": "probe", "extract": "추출", "render": "렌더", "save": "저장"}
    return ", ".join(f"{names[k]} {v:.2f}s" for k, v in result.timings.items())


def _print_setup(
    loaded: LoadedConfig, s: Settings, verbose: bool, ctx: Context
) -> None:
    created = " (새로 만듦)" if loaded.created else ""
    print(
        f"VidGlance {__version__}  |  설정: {loaded.path}{created}  |  "
        f"{s.columns}x{s.rows}, {s.width}px, {s.format}"
    )
    for warning in loaded.warnings + ctx.fonts.warnings:
        print(f"경고: {warning}")
    if verbose:
        print(f"ffprobe: {ctx.ffprobe}\n         {ffmpeg.version(ctx.ffprobe)}")
        print(backend_version())
        print(f"폰트: {ctx.fonts.source} ({ctx.fonts.regular}, {ctx.fonts.bold})")


# --- 진입점 -----------------------------------------------------------------


def run(args: argparse.Namespace, pause: bool) -> int:
    began = time.perf_counter()
    try:
        loaded = load_config(resolve_config_path(args.config))
        settings = apply_overrides(loaded.settings, _overrides(args))
    except ConfigError as e:
        print(f"설정 오류: {e}\n\n설정 파일을 고친 뒤 다시 실행하세요.")
        _finish(pause, ok=False, delay=0)
        return EXIT_SETUP

    if not args.inputs:
        created = " (새로 만들었습니다)" if loaded.created else ""
        print(f"VidGlance {__version__}")
        print("영상 파일이나 폴더를 VidGlance.exe 위로 끌어다 놓으세요.")
        print("여러 개를 한꺼번에 놓을 수 있습니다.")
        print(f"설정 파일: {loaded.path}{created}")
        _finish(pause, ok=False, delay=0)  # 안내를 읽을 수 있게 키 대기
        return EXIT_OK

    try:
        ctx = Context(
            settings,
            ffmpeg.find_tool("ffprobe", settings.ffmpeg_dir),
            fonts.find_fonts(settings.font),
        )
    except (ffmpeg.FFmpegNotFoundError, fonts.FontNotFoundError) as e:
        print(f"오류: {e}")
        _finish(pause, ok=False, delay=0)
        return EXIT_SETUP

    if not args.quiet:
        _print_setup(loaded, settings, args.verbose, ctx)

    items = collect_inputs(args.inputs, settings.recursive, settings.suffix)
    counts = dict.fromkeys(Status, 0)
    width = len(str(len(items)))
    interrupted = False
    for index, item in enumerate(items, 1):
        if not args.quiet:
            print(
                f"[{index:>{width}}/{len(items)}] {item.path.name} … ",
                end="",
                flush=True,
            )
        try:
            if item.error:
                result = Result(item.path, Status.FAILED, item.error)
            else:
                result = process_video(item.path, ctx)
        except KeyboardInterrupt:
            interrupted = True
            print("중단")
            break
        # 한 파일의 예기치 않은 오류로 전체를 멈추지 않는다
        except Exception as e:  # noqa: BLE001
            result = Result(item.path, Status.FAILED, f"예기치 않은 오류: {e!r}")
        counts[result.status] += 1
        if not args.quiet:
            print(_describe(result))
            for warning in result.warnings:
                print(f"    경고: {warning}")
            if args.verbose and result.timings:
                print(f"    {_timings(result)}")

    total = time.perf_counter() - began
    if not args.quiet:
        print(RULE)
    if not items:
        print("처리할 영상이 없습니다.")
    summary = (
        f"완료 {counts[Status.DONE]}, 건너뜀 {counts[Status.SKIPPED]}, "
        f"실패 {counts[Status.FAILED]} (총 {total:.1f}s)"
    )
    print(summary + (" — 중단됨" if interrupted else ""))

    ok = counts[Status.FAILED] == 0 and not interrupted
    _finish(pause, ok, settings.close_delay_seconds)
    return EXIT_OK if ok else EXIT_FAILED


def main(argv: list[str] | None = None) -> int:
    """명령줄 진입점. 종료 코드를 반환한다."""
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    if hasattr(signal, "SIGBREAK"):
        # 콘솔 창 닫기·Ctrl+Break도 Ctrl+C처럼 정리하고 끝낸다 (임시 파일 삭제 등)
        signal.signal(signal.SIGBREAK, _raise_interrupt)

    args = build_parser().parse_args(argv)
    pause = not args.no_pause and owns_console()
    try:
        return run(args, pause)
    except KeyboardInterrupt:
        print("\n중단했습니다.")
        return EXIT_FAILED
