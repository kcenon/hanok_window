# 한옥 창호 CNC 설계와 생성기

창 크기(외경 또는 내경), 창짝당 창살 수, 단문(왼쪽·오른쪽 경첩)·양문을 넣으면 CNC로 깎을 한옥 창호의 CAD 패키지를 만드는 생성기와, 그 출발점인 확정 설계 R3를 함께 담은 저장소입니다.
패키지 하나에는 DXF 도면, PNG 5장, 부품·홈·도그본·하드웨어 참고 좌표표(CSV 4종), 저장한 DXF를 다시 읽어 확인한 검증 기록이 들어 있습니다.

> **제작 전 확인:** 모든 검증은 명목 CAD 기하에 대한 것입니다. 끼움 공차, 경첩·나사 같은 하드웨어, CAM 경로, 고정 지그는 아직 확인 전(PENDING)입니다. 시험편으로 확인하기 전에는 기계로 보내지 마십시오.

## 바로 시작

처음 한 번 `generator/` 폴더에서 설치합니다. Python 3.11 이상이 필요합니다.

```bash
cd generator
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
```

브라우저 화면으로 설계하려면 Finder에서 `generator/web-start.command`를 두 번 누릅니다. 서버가 켜지고 기본 브라우저에 `http://127.0.0.1:8765/`가 열립니다. 끌 때는 `generator/web-stop.command`를 두 번 누릅니다.
터미널에서는 다음과 같이 합니다.

```bash
cd generator
./web.sh start     # 켜고 브라우저로 엽니다
./web.sh stop      # 끕니다. 진행 중인 생성은 끝까지 기다립니다
```

명령줄로 바로 만들 수도 있습니다. 결과는 `generator/output/packages/<패키지 ID>/`에 생깁니다.

```bash
cd generator
.venv/bin/python -m hanok_generator build --input examples/double_r3.json --output output
```

LLM 에이전트(Claude, Cursor, VS Code 등 MCP 클라이언트)로 설계하려면 `generator/mcp.sh`의 절대 경로를 MCP 서버로 등록합니다. OpenAI·Anthropic 형식의 함수 호출 정의도 내보낼 수 있습니다.
자세한 사용법은 [generator/README.md](generator/README.md)에 있습니다.

## 폴더 구성

```text
hanok_window/
├── README.md                  이 문서
├── generator/                 한옥 창호 생성기 0.4.0 (생성 엔진 0.2.0). 새 설계는 여기서
│   ├── README.md              사용 설명서: 설치·웹 화면·명령줄·LLM 연동·입력·산출물·검증
│   ├── web.sh                 웹 서버 켜고 끄기 (start·stop·status·restart·log)
│   ├── web-start.command      Finder에서 두 번 누르면 켜기
│   ├── web-stop.command       Finder에서 두 번 누르면 끄기
│   ├── mcp.sh                 LLM 클라이언트에 등록하는 MCP 서버
│   ├── hanok_generator/       파이썬 패키지: 엔진, 명령줄, 웹 화면, LLM 도구
│   ├── examples/              입력 예제 5종과 생성 결과
│   ├── tests/                 회귀 시험, 웹 시험, LLM 시험, R3 기준값
│   ├── docs/CHANGELOG.md      버전별 구현·검증 기록
│   └── output/                생성한 패키지 (git에 넣지 않음)
└── r3_reference/              확정 설계 R3 원본 (수정 금지)
    ├── 00_START_HERE.txt      R3 안내: 규격, 먼저 열 파일, 재생성·검증 방법
    ├── 01_plan/               계획 문서와 통합 경위
    ├── 02_cnc/                R3 DXF·PNG·CSV와 그것을 만든 소스
    ├── 03_tests/              R3 회귀 시험과 실행 기록
    └── package_manifest.json  R3 파일 목록과 SHA-256
```

## 무엇을 어디서 하나

| 하려는 일 | 갈 곳 |
|---|---|
| 새 크기·창살·형식으로 설계하고 패키지 받기 | `generator/`의 웹 화면 또는 명령줄 |
| LLM(Claude·GPT·Gemini·로컬 모델)에게 설계를 맡기기 | [generator/README.md의 LLM 연동](generator/README.md#llm-연동) (`mcp.sh`, `hanok-window-llm`) |
| R3 설계를 생성기로 다시 만들기 | `generator/examples/double_r3.json` (내경 입력은 `double_inner_r3.json`) |
| R3 원본 도면과 계획 문서 보기 | `r3_reference/00_START_HERE.txt`부터 |
| 생성기가 버전마다 바꾼 것 | [generator/docs/CHANGELOG.md](generator/docs/CHANGELOG.md) |
| 지난 리비전(R1·R2) 보기 | 아래 [이력](#이력)의 git 태그 |

## 지킬 규칙

- **`r3_reference/`는 고치지 않습니다.** 생성기 회귀 시험이 이 폴더의 파일 28개를 SHA-256으로 대조하므로 한 바이트만 바뀌어도 실패합니다. 2026-09-13에 `unified/`에서 이름만 바꿨고 내용은 그대로입니다. 그 안의 문서가 가리키는 `from_codex/`·`from_claude/`는 작업 트리에서 정리해 git 기록에만 있습니다([이력](#이력)).
- **패키지를 섞어 쓰지 않습니다.** 각 패키지의 DXF는 그 패키지 안의 부품표·홈 좌표·가공 지침과 함께 씁니다. 태그에서 꺼낸 옛 DXF, 특히 `from_claude/`의 DXF(채택하지 않은 창살 1+5 안)는 CAM에 넘기지 마십시오.
- **패키지 ID를 정하는 파일은 신중히 고칩니다.** 모든 패키지는 생성기의 최상위 모듈, `engine/`, `presets/`, 입력 스키마를 `source/`에 복사하고 그 해시를 패키지 ID에 넣습니다. 이 파일을 고치면 같은 입력이라도 패키지 ID가 바뀝니다. 웹 코드와 LLM 도구를 `hanok_generator/web/`, `llm/`에 따로 둔 이유입니다.

## R3 확정 규격

- 완성 외곽 463 × 586 mm, 창짝 187 × 500 mm 좌우 2짝, 중앙 고정 기둥 없음
- 창살 창짝당 세로 2 + 가로 4, 빈칸 약 35.67 × 80 mm
- A3 그림 297 × 420 mm 한 장을 고정틀 뒤 별도 후판에 설치
- 원판 1220 × 900 × 20 mm 한 장, 목재 24개

통합 경위와 변경 내역은 [r3_reference/01_plan/SPEC_UNIFICATION.md](r3_reference/01_plan/SPEC_UNIFICATION.md)에 있습니다.

## 이력

| 태그 | 내용 |
|---|---|
| `R1`, `R2`, `R3`, `v0.2.0` | 첫 커밋 `d974f4a`. 지금은 정리한 `from_codex/`, `from_claude/`, `research/`가 들어 있습니다 |
| `v0.3.0` | 로컬 웹 화면 |
| `v0.3.1` | 웹 서버를 켜고 끄는 `web.sh` |
| `v0.4.0` | LLM 도구 7개, MCP 서버, 함수 호출 정의 |

- `from_codex/`: PORTRAIT_DL_R1. 창살 패턴은 지금과 같지만 규격을 손으로 관리하던 버전입니다. 계획서 원본(`01_prompt/`)이 병합 계획서의 뼈대가 되었습니다.
- `from_claude/`: 창살 세로 1 + 가로 5 안. 2026-09-10에 세로 2 + 가로 4로 확정하면서 채택하지 않았습니다. 중앙 맞댐부에 반턱을 넣지 않는 이유 같은 고유 내용은 병합 계획서에 흡수했습니다.
- `research/`: R2 보관본(`baselines/`)과 범용 생성기 요건 조사·검토 기록. R3 회귀 시험의 R2 DXF 대조(`--record`)에는 `research/baselines/`가 필요합니다.

작업 트리를 건드리지 않고 옛 리비전을 보려면 별도 폴더에 꺼냅니다. 꺼낸 폴더에서는 R3 원본이 옛 이름 `unified/`로 보입니다.

```bash
git worktree add ../hanok_window_R1 R1      # 다 본 뒤: git worktree remove ../hanok_window_R1
```

## 시험

```bash
cd generator
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_generator.py'   # 약 100초
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_web.py'         # 약 15초
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_llm.py'         # 약 5초
```

세 명령은 기록 파일을 바꾸지 않습니다. 시험 범위와 기록을 새로 남기는 방법은 [generator/README.md의 검증](generator/README.md#검증)에 있습니다.
