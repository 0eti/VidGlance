"""진입점: 인자 파싱, 콘솔 출력, 창 대기, 종료 코드."""

import argparse
import sys

from vidglance import __version__


def build_parser() -> argparse.ArgumentParser:
    """명령줄 파서를 만든다. 옵션은 Phase 4에서 spec §10대로 채운다."""
    parser = argparse.ArgumentParser(prog="vidglance")
    parser.add_argument(
        "--version", action="version", version=f"VidGlance {__version__}"
    )
    parser.add_argument("inputs", nargs="*", help="영상 파일 또는 폴더")
    return parser


def main(argv: list[str] | None = None) -> int:
    """명령줄 진입점. 종료 코드를 반환한다."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    build_parser().parse_args(argv)
    print("아직 구현되지 않았습니다.")
    return 0
