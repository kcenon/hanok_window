# 한옥 창호 생성기

창의 외경(완성 외곽) 또는 내경(고정틀 안목) 가로·세로, 창짝당 창살 수, 단문(왼쪽·오른쪽 경첩)·양문을 입력하면 CNC용 한옥 창호 패키지를 만듭니다. 패키지에는 DXF, PNG 5장, CSV 4종과 저장한 DXF를 다시 읽어 확인한 검증 기록이 들어 있습니다.
배포 버전은 0.4.1이고 생성 엔진은 0.2.0입니다. 입력·프리셋, 형식 일반화, 고정 검사 ID, 작업별 패키지 생성 CLI에 더해 0.2에서 외경/내경 기준 입력을, 0.3에서 이 컴퓨터의 브라우저로 쓰는 [웹 화면](#웹-화면)을, 0.3.1에서 그 서버를 켜고 끄는 `web.sh`를, 0.4에서 LLM이 도구 호출로 생성기를 쓰는 [LLM 연동](#llm-연동)을, 0.4.1에서 규칙을 통과하는 값을 알려 주는 고침 제안과 LLM 도구 보강을 추가했습니다.
생성 엔진이 그대로이므로 같은 입력의 revision과 패키지 ID는 바뀌지 않습니다.

함께 볼 문서: [생성 예제 5종](examples/README.md) · [버전별 구현·검증 기록](docs/CHANGELOG.md) · [저장소 안내](../README.md) · [R3 원본 안내](../r3_reference/00_START_HERE.txt)

> 검증 PASS는 명목 CAD 기하의 합격입니다. 실제 제작 전에 확인할 항목은 [범위와 한계](#범위와-한계)에 있습니다.

## 목차

- [설치](#설치)
- [웹 화면](#웹-화면)
- [명령줄](#명령줄)
- [LLM 연동](#llm-연동)
- [입력](#입력)
- [산출물](#산출물)
- [검증](#검증)
- [범위와 한계](#범위와-한계)
- [폴더 구성](#폴더-구성)

## 설치

Python 3.11 이상이 필요합니다. 이 작업 공간에는 `.venv/`를 구성해 두었습니다. 다른 컴퓨터에서는 이 폴더(`generator/`)에서 다음과 같이 설치합니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock    # 검증한 의존 버전으로 맞출 때
.venv/bin/python -m pip install -e .
.venv/bin/hanok-window --help
.venv/bin/hanok-window-web --help
.venv/bin/hanok-window-llm --help
.venv/bin/hanok-window-mcp --help
```

`requirements.lock`은 CPython 3.11.15, macOS arm64에서 검증한 실행 의존 버전 전체입니다. `pyproject.toml`은 직접 쓰는 ezdxf·shapely·Pillow만 고정합니다.
이 문서의 명령은 모두 이 폴더에서 실행합니다.

## 웹 화면

명령어 대신 브라우저에서 입력하고, 입력하는 동안 정면도·원판 배치·핵심 치수를 확인한 뒤 CLI와 똑같이 검증한 패키지를 받습니다.

### 켜고 끄기

Finder에서는 `web-start.command`를 두 번 누르면 켜지고 `web-stop.command`를 두 번 누르면 꺼집니다. 터미널에서는 `web.sh`를 씁니다.

```bash
./web.sh start      # 켜고 기본 브라우저로 엽니다 → http://127.0.0.1:8765
./web.sh stop       # 끕니다. 진행 중인 생성은 끝까지 기다립니다
./web.sh status     # 켜짐 0, 응답 없음 1, 꺼짐 3으로 끝납니다
./web.sh restart    # 껐다가 같은 포트로 다시 켭니다
./web.sh log        # 서버 기록의 마지막 40줄
```

`start`에는 `--port 8800`, `--no-open`, `--output 폴더`(상대 경로는 generator 기준)를 붙일 수 있습니다. 다른 `--output`으로 켠 서버는 끌 때도 같은 `--output`을 붙입니다.
서버는 터미널과 떨어진 세션에서 돌기 때문에 창을 닫아도 꺼지지 않습니다. 기록은 `output/.web/`에 둡니다(`server.json`에 pid와 포트, `server.log`에 서버 출력).
서버는 살아 있는 동안 `server.json`을 잠가 두고, `web.sh`는 그 잠금이 걸려 있을 때만 기록의 pid를 믿습니다. 그래서 비정상 종료나 재부팅 뒤에 남은 pid로 엉뚱한 프로세스를 멈추지 않습니다.

터미널 앞에서 실행하고 Ctrl+C로 끝내려면 서버를 직접 실행합니다.

```bash
.venv/bin/hanok-window-web --output output --open        # http://127.0.0.1:8765
.venv/bin/python -m hanok_generator.web --port 8800      # 같은 서버, 모듈로 실행
```

### 화면

| 화면 | 하는 일 |
|---|---|
| 설계 `#/design` | 형식·외경/내경·창살·프리셋·그림·원판을 입력합니다. 입력이 멈추고 150 ms 뒤 서버가 해석해 정면도와 원판 배치를 그리고, 규칙 위반은 해당 칸 옆에 원인과 고치는 방법을 적고, 크기·창살·그림·원판 규칙은 엔진이 받아들이는 값까지 적습니다(예: “외경 가로를 473 mm 이하로 줄이거나 외경 세로를 751 mm 이상으로 늘리세요.”). 외경↔내경을 바꾸면 같은 창이 되도록 숫자를 바꿔 넣습니다. JSON 불러오기·저장 |
| 기록 `#/packages` | `output/packages/`의 패키지를 형식·크기·창살로 보여 주고, 열기와 불러오기(그 패키지의 입력을 설계 화면에 채움)를 제공합니다 |
| 패키지 `#/packages/<id>` | 검사 결과, 읽기 전용 무결성 확인, 제작 전 확인 항목(PENDING) 6개, 도면 5장과 확대·이동 뷰어, 파일별·ZIP 내려받기 |

### 동작과 보안

- 사전 확인 통과는 “도면 검사 전”입니다. 홈끼리 붙는지 같은 판정은 DXF를 저장해 다시 읽어야 알 수 있으므로, 생성 단계에서 실패하면 실패한 검사와 이유를 결과 카드에 따로 보여 줍니다.
- 생성은 CLI와 같은 `jobs.run_job`으로 합니다. 동시 2개(`--workers`로 변경), 대기 8개까지 받습니다.
- 폼은 예제 JSON과 같은 모양의 요청을 만들므로 같은 입력이면 웹과 `--input` CLI의 패키지 ID가 같습니다. CLI `--size 463x586`은 크기를 실수 `463.0`으로 기록하므로 revision은 같아도 패키지 ID가 다릅니다.
- 서버는 `127.0.0.1`에만 열리고 로그인이 없습니다. 다른 Host(421), 다른 출처(403), JSON이 아닌 본문(415), 64 KiB 초과(413)를 거절합니다. 패키지 파일은 매니페스트에 적힌 것만 해시를 대조한 뒤 보내며, 서버는 출력 폴더에 쓰지 않습니다(쓰기는 `run_job`만 합니다).
- 웹 코드는 `hanok_generator/web/`에 있습니다. 패키지 `source/`에 들어가는 파일(최상위 모듈·엔진·프리셋·스키마)을 건드리지 않아 기존 패키지 ID가 그대로입니다. 같은 이유로 `hanok-window` CLI에 명령을 붙이지 않고 별도 명령 `hanok-window-web`을 둡니다.
- 진행 중인 생성 상태는 서버 메모리에만 있습니다. 서버를 다시 켜면 진행 기록은 사라지고 완료 패키지와 `failures/` 기록은 남습니다. Ctrl+C와 `./web.sh stop`은 진행 중인 생성을 끝까지 기다리고 대기 중인 생성은 취소합니다. `stop`은 150초 안에 끝나지 않으면 강제로 끕니다.

## 명령줄

`.venv/bin/python -m hanok_generator`와 `.venv/bin/hanok-window`는 같은 명령입니다.

| 명령 | 하는 일 |
|---|---|
| `build` | 입력을 검증한 패키지로 만듭니다 |
| `resolve` | 입력·프리셋을 해석하고 기하를 미리 검사합니다. 패키지는 만들지 않습니다 |
| `verify <패키지 폴더>` | 패키지 파일의 누락과 해시를 읽기 전용으로 대조합니다 |
| `schema` | JSON 입력 스키마를 출력합니다 |
| `presets` | 지원 프리셋 목록을 출력합니다 |

```bash
.venv/bin/python -m hanok_generator build --type double --size 600x800 --lattice 2x4 --output output
.venv/bin/python -m hanok_generator build --type double --size 383x506 --size-basis inner --lattice 2x4 --output output
.venv/bin/python -m hanok_generator build --type single --hinge-side right --size 420x900 --lattice 2x6 --output output
.venv/bin/python -m hanok_generator build --input examples/single_empty.json --output output
.venv/bin/python -m hanok_generator build --input examples/double_r3.json --output output
.venv/bin/python -m hanok_generator resolve --type double --size 600x800 --lattice 2x4
.venv/bin/python -m hanok_generator verify output/packages/<패키지 ID>
```

`build`와 `resolve`는 입력을 `--input` JSON 파일로 받거나 `--type`, `--hinge-side`, `--size`, `--size-basis`, `--lattice`, `--preset`, `--picture`, `--picture-margin` 옵션으로 받습니다. 각 옵션의 형식은 `--help`에 있습니다.
명령은 생성한 패키지 경로와 수량을 JSON으로 출력합니다. 입력 오류·기하 검증 실패는 종료 코드가 0이 아니며, 고정 `rule_id`와 원인 수치가 포함된 JSON을 표준 오류로 출력합니다.
`build`의 작업 오류 기록은 `output/failures/`에 남습니다. 명령 구문 오류와 입력 파일을 읽지 못하는 오류는 작업 생성 전에 반환합니다.
`resolve`는 규격과 네스팅을 유도하는 사전 확인입니다. 실제 절삭 영역의 겹침 등 저장 DXF 검사를 통과했다는 뜻은 아닙니다.

## LLM 연동

Claude, GPT, Gemini, 로컬 모델(Ollama 등) 같은 LLM이 도구 호출로 이 생성기를 다룰 수 있도록 도구 8개를 제공합니다.
도구는 웹 화면·명령줄과 같은 코드를 쓰므로 같은 설계면 어느 통로로 만들어도 패키지 ID가 같고, 외부 네트워크는 쓰지 않습니다.
모델이 읽는 도구 설명과 오류 안내(`hint`)는 어떤 모델이든 잘 따르도록 영어로 씁니다.

| 도구 | 하는 일 | 파일 쓰기 |
|---|---|---|
| `describe_generator` | 창 형식, 외경/내경, 프리셋 규칙, 입력 범위, 기본값, 예제 요청, 상태의 뜻을 알려 줍니다 | 없음 |
| `check_design` | 사전 확인입니다. 치수·창짝·창살 칸·원판 사용량을 돌려주거나, 어긴 규칙의 `rule_id`와 수치, 고치는 방법(`hint`), 그 규칙을 통과하는 값(`suggestion`)을 돌려줍니다 | 없음 |
| `build_package` | 사전 확인 뒤 작업 프로세스에서 패키지를 만들고 저장 DXF 검사 67개를 돌립니다. 실패하면 실패한 검사를 돌려줍니다 | `output/` |
| `list_packages` | 만든 패키지 목록(최신순) | 없음 |
| `get_package` | 패키지 하나의 요청·치수·검사·PENDING 항목·파일 | 없음 |
| `verify_package` | 패키지 파일 해시 대조(읽기 전용) | 없음 |
| `get_drawing` | 도면 5장 중 하나를 PNG 이미지(가로 480 px 이하)로 돌려줍니다. 이미지를 읽는 모델은 결과를 직접 봅니다 | 없음 |
| `read_package_file` | 패키지의 글 파일(README.txt, CSV 4종, 검증 기록, 입력·규격 JSON, `source/`의 소스)을 해시 대조 뒤 돌려줍니다. 4만 자가 넘으면 `next_offset`부터 이어 읽습니다. DXF와 PNG는 받지 않습니다 | 없음 |

`package_id`는 앞 8자 이상만 줘도 됩니다. 모델이 보낸 요청은 웹 폼처럼 기본값을 빼고 정수를 정수로 맞춘 뒤 처리하므로, `463.0`처럼 보내도 예제와 같은 패키지가 나옵니다. 잘못된 값은 고치지 않고 규칙 오류로 돌려줍니다.

`suggestion`은 규칙이 가리키는 입력 하나만 바꿔 엔진에 다시 물어 찾은 값입니다. 창살이 너무 많으면 들어가는 최대 개수와 그 창살이 들어가는 최소 크기를, 창짝 비율이 어긋나면 통과하는 최대 가로와 최소 세로를, 개구부나 경첩 간격이 모자라면 최소 크기를, 그림·원판이 모자라면 들어가는 그림 크기·여백이나 원판 크기를 줍니다. 내경으로 입력한 요청에는 크기도 내경(`inner_mm`)으로 줍니다. 값 하나는 그 규칙만 통과시키므로 다음 규칙이 나올 수 있고, 모델은 값을 바꿀 때마다 `check_design`을 다시 부릅니다.

### MCP 클라이언트에 등록

MCP를 지원하는 클라이언트(Claude Code, Claude Desktop, Cursor, VS Code, Gemini CLI 등)에는 이 폴더의 `mcp.sh` 절대 경로를 서버 명령으로 등록합니다. 패키지는 `mcp.sh` 옆의 `output/`에 생깁니다.

```bash
claude mcp add hanok-window -- /절대/경로/generator/mcp.sh        # Claude Code
```

```json
{"mcpServers": {"hanok-window": {"command": "/절대/경로/generator/mcp.sh"}}}
```

위 JSON은 Claude Desktop(`claude_desktop_config.json`), Cursor(`.cursor/mcp.json`), Gemini CLI(`settings.json`)의 형식입니다. VS Code(`.vscode/mcp.json`)는 `{"servers": {"hanok-window": {"type": "stdio", "command": "/절대/경로/generator/mcp.sh"}}}`로 씁니다.
다른 출력 폴더를 쓰려면 `mcp.sh --output /절대/경로`처럼 인자를 붙입니다. 서버는 표준 라이브러리로 만든 stdio JSON-RPC 서버이고, 프로토콜 버전 2025-11-25·2025-06-18·2025-03-26·2024-11-05를 협상합니다.
도구 호출은 작업 스레드 4개에서 처리하므로 생성 중에도 `ping`과 `tools/list`에 바로 답합니다. 요청에 `_meta.progressToken`을 붙인 클라이언트는 생성 단계마다 `notifications/progress`를 받고, `notifications/cancelled`로 취소한 호출에는 답을 보내지 않습니다. 이미 시작한 생성은 작업 프로세스에서 끝까지 진행되어 패키지가 남습니다. 도구마다 결과 스키마(`outputSchema`)를 선언하고, 2025-06-18 이후 버전에서는 결과를 `structuredContent`로도 보냅니다.

### 함수 호출 API에서 쓰기

MCP 없이 모델 API를 직접 부르는 프로그램은 도구 정의를 내보내 모델에 넘기고, 모델이 요청한 도구를 `call`로 실행합니다.

```bash
.venv/bin/hanok-window-llm tools --format openai          # Chat Completions, Ollama·vLLM·LM Studio 등 OpenAI 호환
.venv/bin/hanok-window-llm tools --format openai-responses
.venv/bin/hanok-window-llm tools --format anthropic       # Messages API
.venv/bin/hanok-window-llm tools --format mcp
.venv/bin/hanok-window-llm call check_design '{"type": "double", "outer_mm": [600, 800], "lattice_per_leaf": [2, 4]}'
.venv/bin/hanok-window-llm call get_drawing '{"package_id": "3d8e6187", "drawing": "assembly"}'
```

`call`은 결과를 JSON으로 출력합니다. 도구가 실패하면 종료 코드 1, 도구 이름이나 JSON이 틀리면 2로 끝납니다. 도면 이미지는 `--image-dir`(기본: 임시 폴더)에 PNG로 저장하고 경로를 적습니다.
파이썬 프로그램에서는 같은 기능을 바로 씁니다.

```python
from hanok_generator.llm import Toolbox

box = Toolbox("output")
tools = box.definitions("anthropic")         # 모델에 넘길 도구 정의 (mcp, openai, openai-responses, anthropic)
result = box.call("check_design", {"type": "double", "outer_mm": [600, 800], "lattice_per_leaf": [2, 4]})
result.data, result.is_error, result.images  # JSON 결과, 실패 여부, [(MIME 형식, PNG 바이트)]
```

- 도구가 파일을 쓰는 곳은 `build_package`의 `output/`뿐이며, 기존 패키지를 덮어쓰거나 지우지 않습니다. `read_package_file`도 매니페스트에 적힌 파일만 해시를 대조한 뒤 읽으므로, 모델이 넘긴 값으로 임의의 파일 경로를 열지 않습니다.
- MCP 서버는 도구 호출을 동시에 4개까지 처리합니다. 생성은 작업 프로세스에서 하므로 서버 프로세스에는 builder를 올리지 않습니다.
- 검사 PASS는 명목 CAD 기하의 합격입니다. 모델에게 주는 안내(`instructions`, `describe_generator`)에도 이 점과 시험 가공이 필요하다는 것을 적었습니다.

## 입력

```json
{
  "type": "single",
  "hinge_side": "left",
  "outer_mm": [463.4, 585.4],
  "lattice_per_leaf": [0, 4]
}
```

| 항목 | 의미 |
|---|---|
| `type` | `single` 또는 `double` |
| `hinge_side` | 단문의 `left`/`right`. 양문은 양쪽 바깥 경첩 |
| `outer_mm` | 외경: 완성 외곽 `[가로, 세로]`, mm. 소수를 반올림해 설계를 바꾸지 않음 |
| `inner_mm` | 내경: 고정틀 안목 `[가로, 세로]`, mm. `outer_mm`과 둘 중 하나만 지정 |
| `lattice_per_leaf` | 창짝당 `[세로, 가로]` 부재 개수. 각 방향 0개 지원 |
| `preset` | 기본 `standard_v1`. R3 재현용 `hanok_A3_portrait_R3` |
| `picture` | 선택. `{"size_mm":[297,420],"margin_mm":10}` 또는 `null` |
| `stock_mm` | 선택. 기본 `[1220,900,20]` |

전체 스키마는 `.venv/bin/python -m hanok_generator schema`로, 프리셋 목록은 `presets`로 볼 수 있습니다.

### 외경과 내경

크기는 `outer_mm`(외경)과 `inner_mm`(내경) 중 하나로 지정합니다. CLI에서는 `--size`에 `--size-basis outer|inner`를 더하며 기본은 `outer`입니다.
내경은 창짝이 들어가는 고정틀 안쪽 치수입니다. 엔진은 외곽 = 내경 + 2 × 고정틀 폭(현재 프리셋 40 mm)으로 유도하므로, 내경 383 × 506은 R3 외경 463 × 586과 같은 설계입니다.
입력한 기준의 치수는 저장 DXF의 고정틀에서 다시 재어 `requested_size_matches_measured_frame` 검사로 기록합니다. 조립도에는 외경과 내경을 모두 표기하고 입력 기준에 `(INPUT)`을 붙입니다.
외경 입력의 정규화 요청은 0.1과 같아서 기존 설계의 `revision`이 바뀌지 않습니다.

### 프리셋

`standard_v1`은 R3의 부재 폭·공구·간극 기본값을 사용하고 그림과 세장비 제한은 두지 않습니다.
`hanok_A3_portrait_R3`은 양문 전용이며 창짝 세장비 2.6 하한과 A3 그림을 기본으로 둡니다.
그림을 지정하면 외곽에서 계산한 후면 기준영역에 중앙 배치하고 네 변의 최소 여유를 검사합니다.
그림을 외곽 치수의 등식 제약으로 사용하지 않습니다. 홈 깊이는 원판 두께의 절반으로 유도합니다.
부재 폭·공구·경첩 모양은 공개 입력으로 열지 않고 버전 프리셋에서 공급합니다.

### 입력 범위

현재 API 상한은 외곽(내경 입력이면 유도한 외곽)·원판 길이 각 3000 mm, 창살 각 32개, 두께 5~60 mm입니다.
이는 계산 범위 제한이며 제작 가능 범위를 뜻하지 않습니다. 기하·원판 배치 검사가 별도로 거부할 수 있습니다.
기본 참고 경첩 2개가 겹치지 않도록 창짝 높이가 160 mm보다 커야 합니다.

## 산출물

```text
output/
├── latest.json                         마지막 완료 패키지의 상대 경로
├── packages/<내용 SHA-256>/
│   ├── window.dxf
│   ├── 01_*.png ... 05_*.png
│   ├── *_manifest.csv                  4종; 도그본 0개도 헤더 포함
│   ├── design_request.json             재생성 입력
│   ├── design_parameters.json          엔진에 적용한 전체 값
│   ├── resolved_parameters.json        입력·프리셋·유도 근거
│   ├── design_spec.json
│   ├── validation_report.json
│   ├── environment.json
│   ├── package_manifest.json
│   ├── README.txt
│   └── source/                         실행 소스와 의존 버전
├── failures/<작업 ID>.json
├── .staging/                           생성 중인 작업 폴더 (완료 전에는 공개하지 않음)
└── .web/                               web.sh 서버 기록 (server.json, server.log)
```

### 공개 방식

매 작업은 별도 프로세스와 `.staging/` 아래 새 폴더를 사용합니다.
DXF 저장·재읽기, CSV·PNG·README·소스 생성, 누락·PNG 디코딩·해시 검사를 모두 마친 패키지만
`packages/`로 옮깁니다. 기존 완료 폴더를 수정하지 않고, `latest.json` 파일 하나를 교체해 공개 참조를 전환합니다.
동시 요청은 각자의 완료 경로를 받으며 마지막으로 완료된 요청이 `latest.json`을 갱신합니다.

공개 참조 교체 직전 I/O 오류가 나면 이전 `latest.json`은 유지됩니다.
이 경우 참조되지 않는 새 완료 폴더가 남을 수 있으나 불완전한 폴더를 공개하지 않습니다.
강제 종료로 남은 `.staging/` 폴더도 완료 패키지로 취급하지 않습니다.
전원 장애 후 저장 영속성까지 보장하는 시스템으로 구현한 것은 아닙니다.

### 무결성과 재생성

```bash
.venv/bin/python -m hanok_generator verify output/packages/<패키지 ID>
```

`verify`는 읽기 전용 해시·누락 대조입니다. 매니페스트를 재작성하지 않습니다.
DXF 기하 검증은 빌드 안에서 저장 전과 저장 후 모두 수행합니다.
패키지의 `source/`를 `PYTHONPATH`로 지정하면 원래 저장소 없이 재생성할 수 있습니다.
DXF와 PNG의 재현 조건은 `environment.json`에 기록하며 폰트 파일 자체는 배포하지 않습니다.

### 형식과 상세도

단문은 지정한 쪽의 세로재에 경첩 2개, 반대 세로재에 손잡이와 캐치 참고 위치를 둡니다.
양문은 양쪽 바깥 경첩을 쓰고 R3의 중앙 손잡이·상단 캐치 배치를 사용합니다.
하드웨어의 모양과 위치는 실제 제품을 선정하기 전의 참고 정보입니다.

- J1·J2: 고정틀·창짝 모서리.
- J3: 두 방향 창살이 모두 있을 때만 생성.
- J4V: 세로 창살과 가로 테두리의 결합이 있을 때만 생성.
- J4H: 가로 창살과 세로 테두리의 결합이 있을 때만 생성.

검사 결과는 `rule_id`, `expected`, `actual`, `tolerance`, `targets`, `status`를 구분합니다.
창살 수나 치수를 바꿔도 검사 ID는 변하지 않습니다. 결합 상세에 실제 존재하는 부재 계열이 쓰였는지도 확인합니다.

## 검증

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_generator.py'   # 약 100초
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_web.py'         # 약 15초
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_llm.py'         # 약 10초
```

세 명령은 기록 파일을 바꾸지 않습니다. 시험은 생성기 밖의 임시 폴더에서 완성 패키지를 만듭니다.
실행 소스의 SHA-256과 결과를 `tests/results.json`에 새로 기록할 때만 스크립트로 실행합니다.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/test_generator.py      # tests/results.json을 다시 씁니다
```

- **생성기 시험:** 단문 좌우·양문, 외경/내경 입력 동등성과 재측정, 창살 0개 조합, 조건부 상세도, 하드웨어 부재와 열림 방향, R3 형상 회귀, 소수 외곽 200건씩 일반/최적화 실행, 과밀·원판 초과·그림 초과 거부, 동시 성공/실패 작업, 단계별 오류·작업 프로세스 종료, 소스 번들 재생성, 무결성 검사를 확인합니다.
- **R3 보존:** R3 규격·부품·결합·네스팅 및 생산 윤곽 176개를 고정한 기준은 `tests/fixtures/r3_reference.json`입니다. 저장소의 `r3_reference/` 폴더에서 파일 28개도 SHA-256으로 대조합니다.
- **웹 시험:** 임시 출력 폴더에서 예제 5종을 웹과 `run_job`으로 각각 만들어 패키지 ID를 대조하고, 사전 확인·오류 표시 위치·보안 거절·파일과 ZIP·생성 대기열·서버 프로세스 격리·소스 해시를 확인합니다. `web.sh` 시험은 임시 폴더에서 서버를 켜고 다시 켜고 끄며, 죽은 서버가 남긴 pid를 건드리지 않는지와 포트 충돌·시작 실패 안내를 확인합니다. 규칙 8종마다 고침 제안의 값을 하나씩 적용해 그 규칙이 풀리는지 확인합니다. 화면의 요청 구성(`app.js`)이 예제 JSON을 그대로 만드는지와 오류 문구(`messages.js`)가 제안 값을 적는지는 `node`가 있을 때만 확인합니다.
- **LLM 시험:** 네 형식의 도구 정의(영어·스키마 호환), 요청 정규화, 모델이 실수로 섞은 실수·기본값으로도 CLI와 같은 패키지 ID가 나오는지, 규칙 오류의 `hint`와 제안(제안 값으로 고치면 통과하는지), 모든 도구의 결과가 선언한 결과 스키마를 따르는지, 패키지 파일 읽기와 이어 읽기, 생성 실패 보고, 패키지 도구와 도면 이미지, MCP 서버의 초기화·버전 협상·도구 호출·오류 코드·일괄 요청·생성 중 응답·진행 알림·취소, `hanok-window-llm` 종료 코드, 도구를 부르는 프로세스에 builder가 올라가지 않는지를 확인합니다.

공식 MCP 파이썬 SDK(`mcp`) 클라이언트와 맞물리는지는 따로 확인합니다. SDK는 생성기의 의존성이 아니므로 별도 가상환경에 설치해 실행합니다. SDK가 `mcp.sh`를 켜서 연결하고, 도구 목록과 결과 스키마를 받고, 도구를 불러 결과를 그 스키마로 검증합니다.

```bash
python3.11 -m venv /tmp/mcp-sdk && /tmp/mcp-sdk/bin/python -m pip install mcp
/tmp/mcp-sdk/bin/python tests/interop_mcp_sdk.py        # 모든 단계를 통과하면 끝에 PASS
```

새 시스템은 R3 코드를 별도 모듈로 확장했으며 기존 패키지를 덮어쓰지 않습니다. 이전 리비전(R1·R2)과 조사 기록은 작업 트리에서 정리했고 git 태그로 보관합니다([저장소 안내의 이력](../README.md#이력)).

## 범위와 한계

- 실제 제작용 최소 잔존 폭·끼움 공차·경첩/나사·후판/벽 고정·개폐 간섭·CAM·고정 지그는 PENDING입니다. 시험편으로 확인하기 전에는 기계로 보내지 마십시오.
- 다중 원판은 후속 범위입니다. 개별 부재 초과(`nesting.part_fits_stock`)와 한 장 전체 배치 부족(`nesting.board_width`)은 각각 이유를 밝혀 거부합니다.
- 입력 상한은 계산 범위 제한이며 제작 가능 범위가 아닙니다([입력 범위](#입력-범위)).
- 하드웨어의 모양과 위치는 실제 제품을 선정하기 전의 참고 정보입니다.
- `web.sh`는 파일 잠금과 세션 기능을 쓰므로 macOS와 Linux에서만 동작합니다.
- LLM 연동은 LLM이 생성기를 부르는 방향만 있습니다. 생성기가 LLM API를 불러 자연어로 설계하는 기능은 없습니다.

## 폴더 구성

```text
generator/
├── README.md                이 문서
├── pyproject.toml           배포 정보와 명령 hanok-window·hanok-window-web·hanok-window-llm·hanok-window-mcp
├── requirements.lock        검증한 의존 버전
├── web.sh                   웹 서버 켜고 끄기
├── web-start.command        Finder에서 켜기
├── web-stop.command         Finder에서 끄기
├── mcp.sh                   LLM 클라이언트에 등록하는 MCP 서버
├── hanok_generator/
│   ├── cli.py               명령줄: 패키지 생성·입력 해석·무결성 대조
│   ├── model.py             공개 입력 검사와 버전별 프리셋 해석
│   ├── formats.py           창짝 구성, 참고 하드웨어 위치, 열림 방향
│   ├── jobs.py              작업별 격리 생성, 완료 패키지 보존, latest.json 전환
│   ├── worker.py            작업 프로세스 진입점
│   ├── package.py           패키지 매니페스트와 읽기 전용 무결성 검사
│   ├── engine/              R3 엔진에서 확장한 기하·DXF·렌더·가공 검사
│   ├── presets/             프리셋 값 (r3_parameters.json)
│   ├── request.schema.json  입력 스키마
│   ├── web/                 웹 서버와 화면, 고침 제안, web.sh의 제어 코드
│   └── llm/                 LLM 도구, 함수 호출 정의, MCP 서버
├── examples/                입력 예제 5종과 생성 결과
├── tests/                   test_generator.py, test_web.py, test_llm.py, interop_mcp_sdk.py, fixtures/, results.json
├── docs/CHANGELOG.md        버전별 구현·검증 기록
└── output/                  생성한 패키지 (git에 넣지 않음)
```

`hanok_generator/`의 최상위 모듈, `engine/`, `presets/`, `request.schema.json`은 모든 패키지의 `source/`에 복사되고 그 해시가 패키지 ID에 들어갑니다. 이 파일을 고치면 같은 입력이라도 패키지 ID가 바뀝니다.
`package.source_files()`는 이것들만 모으고 `web/`, `llm/` 같은 다른 하위 폴더는 모으지 않으므로, 화면이나 도구처럼 생성 결과와 무관한 코드는 하위 폴더에 둡니다.
