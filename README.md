# VidGlance

영상 파일을 `VidGlance.exe` 위로 끌어다 놓으면, 같은 폴더에 **한 장짜리 썸네일 시트**(`영상이름_sheet.webp`)를 만드는 Windows 도구입니다.

- 위쪽에 영상 정보: 파일명, 크기, 해상도(비율), fps, 비디오·오디오 코덱, 재생 시간
- 아래에 4×5 격자 프레임: 영상 전체를 처음·끝을 빼고 균등한 간격으로 나눈 지점, 각 칸 오른쪽 아래에 `HH:MM:SS` 타임스탬프
- 여러 영상과 폴더를 한꺼번에 처리하고, 한글 파일명·경로를 지원합니다
- 설치가 필요 없습니다. Python이나 ffmpeg가 없는 PC에서도 동작합니다

## 받기: 두 가지 형태

| 형태 | 파일 | 특징 |
|---|---|---|
| **파일 하나** (onefile) | `VidGlance.exe` (약 82MB) | 들고 다니기 쉽습니다. 실행할 때마다 내장 파일을 임시 폴더에 풀어서 **시작에 약 5초**가 걸립니다 |
| **폴더** (onedir) | `VidGlance\` 폴더 (약 210MB) 안의 `VidGlance.exe` | 시작이 **0.4초**로 빠릅니다. 폴더 전체(`_internal` 포함)를 함께 옮겨야 합니다 |

기능은 똑같습니다. 직접 빌드하는 방법은 [개발](#개발)에 있습니다.

> 서명되지 않은 exe라서 처음 실행할 때 Windows SmartScreen이 "Windows의 PC 보호" 창을 띄울 수 있습니다. **추가 정보 → 실행**을 누르면 됩니다.

## 사용법

1. `VidGlance.exe`를 원하는 폴더에 둡니다.
2. 탐색기에서 영상 파일(여러 개 가능)이나 폴더를 골라 **`VidGlance.exe` 아이콘 위로 끌어다 놓습니다.**
3. 콘솔 창에 진행 상황이 나오고, 각 영상과 **같은 폴더**에 `영상이름_sheet.webp`가 생깁니다.

```
VidGlance 0.1.0  |  설정: D:\Tools\VidGlance\config.json  |  4x5, 1024px, webp
[1/3] 예시영상.mp4 … 완료 (4.2s) → 예시영상_sheet.webp
[2/3] 깨진파일.mkv … 실패: 영상을 읽을 수 없음: Invalid data found when processing input
[3/3] 이미있음.mp4 … 건너뜀 (이미 있음)
──────────
완료 1, 건너뜀 1, 실패 1 (총 6.0s)
아무 키나 누르면 닫힙니다…
```

- **모두 성공하면** 3초 뒤 창이 저절로 닫힙니다(키를 누르면 바로 닫힘). **실패가 있으면** 키를 누를 때까지 기다립니다.
- 이미 시트가 있는 영상은 **건너뜁니다**. 다시 만들려면 시트를 지우거나 설정의 `overwrite`를 `true`로 바꿉니다.
- 폴더를 놓으면 그 안의 영상(`mp4 mkv avi mov wmv flv webm m4v ts m2ts mpg mpeg 3gp`)만 처리합니다. 하위 폴더까지 처리하려면 `recursive`를 `true`로 바꿉니다.
- 파일 수백 개를 한 번에 끌면 Windows 명령줄 길이 제한(약 32,000자)에 걸릴 수 있습니다. 그럴 때는 **폴더를 끌어다 놓으세요.**
- 아주 짧은 영상은 칸 사이가 0.1초 이상이 되는 만큼만 채우고, 나머지 칸은 비워 둡니다. 프레임을 뽑지 못한 칸은 회색으로 남깁니다.

## 설정 (`config.json`)

`VidGlance.exe`를 **더블클릭**(아무것도 끌어다 놓지 않고 실행)하면 exe 옆에 `config.json`이 기본값으로 만들어지고, 그 위치를 알려 줍니다. 메모장으로 고친 뒤 저장하면 **다음 실행부터** 반영됩니다.

- exe 폴더에 쓸 수 없으면(예: `Program Files`) `%APPDATA%\VidGlance\config.json`을 씁니다.
- 새 버전에서 설정이 늘어나면 빠진 키를 기본값으로 파일에 채워 넣습니다. 고친 값은 그대로 둡니다.
- 값이 잘못되면 **어느 키가 왜 잘못됐는지** 보여 주고 아무것도 처리하지 않습니다. 파일은 덮어쓰지 않습니다.

```json
{
  "config_version": 1,
  "columns": 4,
  "rows": 5,
  "width": 1024,
  "gap": 8,
  "theme": "light",
  "language": "en",
  "header": {
    "file_name": true,
    "size": true,
    "resolution": true,
    "fps": true,
    "video_codec": true,
    "audio_codec": true,
    "duration": true
  },
  "format": "webp",
  "quality": 85,
  "suffix": "_sheet",
  "output_dir": "",
  "overwrite": false,
  "show_timestamp": true,
  "recursive": false,
  "skip_start_seconds": 0,
  "skip_end_seconds": 0,
  "seek_mode": "fast",
  "font": "",
  "ffmpeg_dir": "",
  "close_delay_seconds": 3
}
```

| 키 | 뜻 | 허용 값 |
|---|---|---|
| `columns`, `rows` | 격자 열·행 수 | 1–20 |
| `width` | 시트 가로 크기(px) | 320–8000 |
| `gap` | 칸 사이 간격(px). 0이면 칸이 붙습니다 | 0–100 |
| `theme` | 시트 색: 밝은 배경 / 어두운 배경 | `"light"` / `"dark"` |
| `language` | 헤더 레이블 언어 (`File Name:` / `파일명:`) | `"en"` / `"ko"` |
| `header.*` | 헤더 항목별 표시 여부. 모두 `false`면 헤더 없이 격자만 그립니다 | `true` / `false` |
| `format` | 저장 형식 | `"webp"` / `"jpg"` / `"png"` |
| `quality` | 압축 품질 (png는 무시) | 1–100 |
| `suffix` | 출력 파일명 꼬리 (`영상이름{suffix}.webp`) | 비어 있지 않은 문자열. `< > : " / \ \| ? *` 금지 |
| `output_dir` | 저장 폴더. 비우면 영상과 같은 폴더, 상대 경로면 각 영상 폴더 기준 (예: `"thumbs"`) | 경로 |
| `overwrite` | 이미 있는 시트를 덮어쓸지 | `true` / `false` |
| `show_timestamp` | 칸마다 타임스탬프를 그릴지 | `true` / `false` |
| `recursive` | 폴더를 놓았을 때 하위 폴더까지 처리할지 | `true` / `false` |
| `skip_start_seconds`, `skip_end_seconds` | 앞·뒤에서 뺄 구간(초). 인트로·엔딩 건너뛰기 | 0 이상 |
| `seek_mode` | 프레임 고르는 방식. `fast`는 균등 시점에서 가장 가까운 키프레임을 써서 빠르고(시점 오차 보통 1~3초), `accurate`는 정확한 시점까지 디코딩해서 느립니다. 타임스탬프는 항상 실제 장면의 시각입니다 | `"fast"` / `"accurate"` |
| `font` | 글꼴 파일 경로. 비우면 맑은 고딕 → 내장 Pretendard | 경로 |
| `ffmpeg_dir` | `ffprobe.exe`가 있는 폴더. 비우면 자동으로 찾음([ffprobe 교체](#ffprobe-교체)) | 경로 |
| `close_delay_seconds` | 모두 성공했을 때 창이 닫히기까지 기다릴 초. 0이면 바로, 음수면 항상 키 대기 | 정수 |

### Windows 경로를 쓸 때 주의

JSON에서는 `\`를 **두 번** 써야 합니다. 또는 `/`를 써도 됩니다.

```json
"font": "C:\\Fonts\\MyFont.ttf",
"output_dir": "D:/썸네일"
```

`"C:\Fonts\MyFont.ttf"`처럼 한 번만 쓰면 "JSON 문법 오류"가 납니다. 오류 메시지가 몇 번째 줄인지 알려 줍니다.

## 명령줄 옵션

끌어다 놓기 대신 명령 프롬프트에서 실행할 수도 있습니다. 지정한 옵션은 `config.json` 값을 **이번 실행에서만** 덮어씁니다. 명령줄에서 실행하면 끝나고 창이 기다리지 않습니다.

```
VidGlance.exe [옵션] <파일 또는 폴더...>

  -g, --grid CxR         격자 (예: 5x6)
  -w, --width PX
      --gap PX
      --theme THEME      light | dark
      --lang LANG        en | ko
  -o, --output-dir DIR
  -r, --recursive
      --format FMT       webp | jpg | png
      --quality N
      --overwrite
      --no-timestamp
      --font PATH
      --seek MODE        fast | accurate
      --ffmpeg-dir DIR
      --config PATH      설정 파일 직접 지정
      --no-pause         끝나고 기다리지 않음
  -q, --quiet            요약만 출력
  -v, --verbose          ffprobe 경로·버전, 폰트, 단계별 시간 출력
      --version
```

종료 코드: `0` 모두 성공 또는 건너뜀, `1` 하나 이상 실패, `2` 설정 오류·ffprobe 없음·잘못된 옵션.

## ffprobe 교체

영상 정보(헤더)는 **ffprobe**로 읽습니다. exe에 ffprobe가 들어 있지만, 바깥에 있는 것을 먼저 씁니다. 그래서 VidGlance를 다시 빌드하지 않아도 ffprobe만 바꿀 수 있습니다.

찾는 순서:

1. `config.json`의 `ffmpeg_dir` (또는 `--ffmpeg-dir`) 폴더의 `ffprobe.exe`
2. **`VidGlance.exe`와 같은 폴더**의 `ffprobe.exe` ← 가장 간단한 방법
3. `PATH` (예: `winget install Gyan.FFmpeg`로 설치한 것)
4. exe 내장본

어떤 ffprobe를 썼는지는 `VidGlance.exe -v 영상.mp4`로 확인합니다.

```
ffprobe: D:\Tools\VidGlance\ffprobe.exe
         ffprobe version 9.0.2-essentials_build-www.gyan.dev ...
PyAV 19.0.2 (FFmpeg 9.0.2)
```

프레임 추출은 exe에 들어 있는 PyAV(FFmpeg 라이브러리)로 하므로 바꿀 수 없습니다.

## 문제 해결

| 증상 | 확인할 것 |
|---|---|
| 4K·AV1 영상이 느리다 | `seek_mode`가 `"accurate"`인지 확인합니다. 기본값 `"fast"`는 4K AV1 영상 1개를 약 2초에 처리합니다(`accurate`는 약 11초) |
| 시작이 5초쯤 걸린다 | 파일 하나(onefile) 형태라서 그렇습니다. 폴더(onedir) 형태를 쓰면 0.4초입니다 |
| "건너뜀 (이미 있음)" | 시트가 이미 있습니다. 지우거나 `overwrite`를 `true`로 |
| "건너뜀 (영상 아님)" | 영상이 아닌 파일(문서, 사진 등)을 직접 끌어다 놓았습니다 |
| "설정 오류" | 메시지에 나온 키와 줄을 고칩니다. 경로의 `\`는 `\\`로 |
| 칸 일부가 회색 | 그 시점의 프레임을 읽지 못했습니다(손상된 구간 등). 나머지 칸은 정상입니다 |
| 시트 너비가 설정보다 작다 | WebP 최대 크기(16383px)를 넘어서 비율대로 줄였습니다(세로 영상 + 많은 행). 경고가 함께 나옵니다 |

## 개발

[uv](https://docs.astral.sh/uv/)와 ffmpeg(테스트 영상 생성용)가 필요합니다.

```
uv sync                                  # 의존성 설치
uv run vidglance <파일|폴더...>           # 끌어다 놓기와 같은 방식으로 실행
uv run vidglance -v --no-pause <파일>     # ffprobe 경로·단계별 시간 출력
uv run pytest                            # 처음 실행 때 tests/_media/에 테스트 영상을 만든다 (ffmpeg 필요)
uv run ruff check . && uv run ruff format .
uv run python build/build.py            # exe 빌드 → dist/VidGlance.exe(onefile), dist/VidGlance/(onedir)
```

빌드는 처음 한 번 Gyan.dev에서 ffmpeg essentials 빌드(약 115MB)를 받아 SHA-256을 확인하고, 그 안의 `ffprobe.exe`만 꺼내 넣습니다. 받은 버전은 `build/ffmpeg_version.txt`에 기록됩니다.

## 라이선스와 고지

VidGlance의 소스 코드는 [MIT 라이선스](LICENSE)입니다.

배포하는 exe에는 아래 프로그램과 라이브러리가 함께 들어 있고, 각각 자기 라이선스를 따릅니다.

| 구성 요소 | 버전 | 라이선스 | 출처 |
|---|---|---|---|
| FFmpeg `ffprobe.exe` (Gyan.dev essentials 빌드) | 9.0.2 | **GPL v3** — 별도 실행 파일로 함께 배포. 라이선스 원문은 onedir 배포물의 `_internal\ffmpeg\LICENSE`(onefile은 exe 안에 포함) | 빌드: <https://www.gyan.dev/ffmpeg/builds/> · 소스: <https://ffmpeg.org/download.html> |
| PyAV | 19.0.2 | BSD-3-Clause | <https://github.com/PyAV-Org/PyAV> |
| PyAV에 포함된 FFmpeg 라이브러리 (libavcodec 등) | 9.0.2 | LGPL v3 이상 | <https://ffmpeg.org> |
| Pillow | 13.0.0 | MIT-CMU | <https://github.com/python-pillow/Pillow> |
| Python | 3.12 | PSF License | <https://www.python.org> |
| Pretendard 글꼴 | 1.3.9 | SIL Open Font License 1.1 (`assets/fonts/Pretendard-LICENSE.txt`) | <https://github.com/orioncactus/pretendard> |
| PyInstaller 부트로더 | 6.22 | GPL v2+ (빌드된 프로그램에는 적용되지 않는 예외 조항) | <https://pyinstaller.org> |

FFmpeg는 FFmpeg 프로젝트를 시작한 Fabrice Bellard의 상표입니다. VidGlance는 FFmpeg 프로젝트와 관계가 없습니다.
