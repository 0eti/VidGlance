"""config.json 위치·생성·검증·병합 → Settings(dataclass).

파일 읽기·쓰기는 Phase 4에서 구현한다. 지금은 다른 모듈이 받을 설정 타입만 둔다.
"""

from dataclasses import dataclass
from typing import Literal

Language = Literal["en", "ko"]
ThemeName = Literal["light", "dark"]
OutputFormat = Literal["webp", "jpg", "png"]


@dataclass(frozen=True)
class HeaderSettings:
    """헤더 항목별 표시 여부 (spec §6)."""

    file_name: bool = True
    size: bool = True
    resolution: bool = True
    fps: bool = True
    video_codec: bool = True
    audio_codec: bool = True
    duration: bool = True
