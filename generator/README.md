# 한옥 창호 생성기 0.3

창틀의 외경(완성 외곽) 또는 내경(고정틀 안목) 가로·세로, 창짝당 창살 수, 단문 좌우/양문을 입력하면 DXF·PNG 5장·CSV 4종과 검증 기록을 생성합니다.
입력·프리셋, 형식 일반화, 고정 검사 ID, 작업별 패키지 생성 CLI에 더해 0.2에서 외경/내경 기준 입력을, 0.3에서 이 컴퓨터의 브라우저로 쓰는 [웹 화면](#웹-화면)을 추가했습니다.
생성 엔진은 0.2.0 그대로이므로 같은 입력의 revision과 패키지 ID가 바뀌지 않습니다.

바로 볼 수 있는 [생성 예제 5종](generator/examples/GENERATED.md)과
[구현·검증 기록](generator/IMPLEMENTATION.md)을 함께 제공합니다.

## 실행

Python 3.11 이상이 필요합니다. 이 작업 공간에는 `.venv/`를 구성했습니다.

```bash
cd generator
.venv/bin/python -m hanok_generator build --type double --size 600x800 --lattice 2x4 --output output
.venv/bin/python -m hanok_generator build --type double --size 383x506 --size-basis inner --lattice 2x4 --output output
.venv/bin/python -m hanok_generator build --type single --hinge-side right --size 420x900 --lattice 2x6 --output output
.venv/bin/python -m hanok_generator build --input examples/single_empty.json --output output
.venv/bin/python -m hanok_generator build --input examples/double_r3.json --output output
```

다른 환경에는 다음과 같이 설치합니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/hanok-window --help
.venv/bin/hanok-window-web --help
```

명령은 생성한 패키지 경로와 수량을 JSON으로 출력합니다. 입력 오류·기하 검증 실패는 종료 코드가 0이 아니며,
고정 `rule_id`와 원인 수치가 포함된 JSON을 표준 오류로 출력합니다.
`build`의 작업 오류 기록은 `output/failures/`에 남습니다. 명령 구문 오류와 입력 파일을 읽지 못하는 오류는 작업 생성 전에 반환합니다.

## 웹 화면

명령어 대신 브라우저에서 입력하고, 입력하는 동안 정면도·원판 배치·핵심 치수를 확인한 뒤 CLI와 똑같이 검증한 패키지를 받습니다.

```bash
.venv/bin/hanok-window-web --output output --open        # http://127.0.0.1:8765
.venv/bin/python -m hanok_generator.web --port 8800      # 같은 서버, 모듈로 실행
```

| 화면 | 하는 일 |
|---|---|
| 설계 `#/design` | 형식·외경/내경·창살·프리셋·그림·원판을 입력합니다. 입력이 멈추고 150 ms 뒤 서버가 해석해 정면도와 원판 배치를 그리고, 규칙 위반은 해당 칸 옆에 원인과 고치는 방법을 적습니다. 외경↔내경을 바꾸면 같은 창이 되도록 숫자를 바꿔 넣습니다. JSON 불러오기·저장 |
| 기록 `#/packages` | `output/packages/`의 패키지를 형식·크기·창살로 보여 주고, 열기와 불러오기(그 패키지의 입력을 설계 화면에 채움)를 제공합니다 |
| 패키지 `#/packages/<id>` | 검사 결과, 읽기 전용 무결성 확인, 제작 전 확인 항목(PENDING) 6개, 도면 5장과 확대·이동 뷰어, 파일별·ZIP 내려받기 |

- 사전 확인 통과는 “도면 검사 전”입니다. 홈끼리 붙는지 같은 판정은 DXF를 저장해 다시 읽어야 알 수 있으므로, 생성 단계에서 실패하면 실패한 검사와 이유를 결과 카드에 따로 보여 줍니다.
- 생성은 CLI와 같은 `jobs.run_job`으로 합니다. 동시 2개(`--workers`로 변경), 대기 8개까지 받습니다.
- 폼은 예제 JSON과 같은 모양의 요청을 만들므로 같은 입력이면 웹과 `--input` CLI의 패키지 ID가 같습니다. CLI `--size 463x586`은 크기를 실수 `463.0`으로 기록하므로 revision은 같아도 패키지 ID가 다릅니다.
- 서버는 `127.0.0.1`에만 열리고 로그인이 없습니다. 다른 Host(421), 다른 출처(403), JSON이 아닌 본문(415), 64 KiB 초과(413)를 거절합니다. 패키지 파일은 매니페스트에 적힌 것만 해시를 대조한 뒤 보내며, 서버는 출력 폴더에 쓰지 않습니다(쓰기는 `run_job`만 합니다).
- 웹 코드는 `hanok_generator/web/`에 있습니다. 패키지 `source/`에 들어가는 파일(최상위 모듈·엔진·프리셋·스키마)을 건드리지 않아 기존 패키지 ID가 그대로입니다. 같은 이유로 `hanok-window` CLI에 명령을 붙이지 않고 별도 명령 `hanok-window-web`을 둡니다.
- 진행 중인 생성 상태는 서버 메모리에만 있습니다. 서버를 다시 켜면 진행 기록은 사라지고 완료 패키지와 `failures/` 기록은 남습니다. Ctrl+C는 진행 중인 생성을 끝까지 기다리고 대기 중인 생성은 취소합니다.

## 입력과 프리셋

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

크기는 `outer_mm`(외경)과 `inner_mm`(내경) 중 하나로 지정합니다. CLI에서는 `--size`에 `--size-basis outer|inner`를 더하며 기본은 `outer`입니다.
내경은 창짝이 들어가는 고정틀 안쪽 치수입니다. 엔진은 외곽 = 내경 + 2 × 고정틀 폭(현재 프리셋 40 mm)으로 유도하므로, 내경 383 × 506은 R3 외경 463 × 586과 같은 설계입니다.
입력한 기준의 치수는 저장 DXF의 고정틀에서 다시 재어 `requested_size_matches_measured_frame` 검사로 기록합니다. 조립도에는 외경과 내경을 모두 표기하고 입력 기준에 `(INPUT)`을 붙입니다.
외경 입력의 정규화 요청은 0.1과 같아서 기존 설계의 `revision`이 바뀌지 않습니다.

`standard_v1`은 R3의 부재 폭·공구·간극 기본값을 사용하고 그림과 세장비 제한은 두지 않습니다.
`hanok_A3_portrait_R3`은 양문 전용이며 창짝 세장비 2.6 하한과 A3 그림을 기본으로 둡니다.
그림을 지정하면 외곽에서 계산한 후면 기준영역에 중앙 배치하고 네 변의 최소 여유를 검사합니다.
그림을 외곽 치수의 등식 제약으로 사용하지 않습니다. 홈 깊이는 원판 두께의 절반으로 유도합니다.

현재 API 상한은 외곽(내경 입력이면 유도한 외곽)·원판 길이 각 3000 mm, 창살 각 32개, 두께 5~60 mm입니다.
이는 계산 범위 제한이며 제작 가능 범위를 뜻하지 않습니다. 기하·원판 배치 검사가 별도로 거부할 수 있습니다.
부재 폭·공구·경첩 모양은 공개 입력으로 열지 않고 버전 프리셋에서 공급합니다.
기본 참고 경첩 2개가 겹치지 않도록 창짝 높이가 160 mm보다 커야 합니다.

```bash
.venv/bin/python -m hanok_generator schema
.venv/bin/python -m hanok_generator presets
.venv/bin/python -m hanok_generator resolve --type double --size 600x800 --lattice 2x4
```

`resolve`는 규격과 네스팅을 유도하는 사전 확인입니다. 실제 절삭 영역의 겹침 등 저장 DXF 검사를 통과했다는 뜻은 아닙니다.

## 산출물과 공개 경계

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
└── failures/<작업 ID>.json
```

매 작업은 별도 프로세스와 `.staging/` 아래 새 폴더를 사용합니다.
DXF 저장·재읽기, CSV·PNG·README·소스 생성, 누락·PNG 디코딩·해시 검사를 모두 마친 패키지만
`packages/`로 옮깁니다. 기존 완료 폴더를 수정하지 않고, `latest.json` 파일 하나를 교체해 공개 참조를 전환합니다.
동시 요청은 각자의 완료 경로를 받으며 마지막으로 완료된 요청이 `latest.json`을 갱신합니다.

공개 참조 교체 직전 I/O 오류가 나면 이전 `latest.json`은 유지됩니다.
이 경우 참조되지 않는 새 완료 폴더가 남을 수 있으나 불완전한 폴더를 공개하지 않습니다.
강제 종료로 남은 `.staging/` 폴더도 완료 패키지로 취급하지 않습니다.
전원 장애 후 저장 영속성까지 보장하는 시스템으로 구현한 것은 아닙니다.

```bash
.venv/bin/python -m hanok_generator verify output/packages/<패키지 ID>
```

`verify`는 읽기 전용 해시·누락 대조입니다. 매니페스트를 재작성하지 않습니다.
DXF 기하 검증은 빌드 안에서 저장 전과 저장 후 모두 수행합니다.
패키지의 `source/`를 `PYTHONPATH`로 지정하면 원래 저장소 없이 재생성할 수 있습니다.
DXF와 PNG의 재현 조건은 `environment.json`에 기록하며 폰트 파일 자체는 배포하지 않습니다.

## 형식과 상세도

단문은 지정한 쪽의 세로재에 경첩 2개, 반대 세로재에 손잡이와 캐치 참고 위치를 둡니다.
양문은 양쪽 바깥 경첩을 쓰고 R3의 중앙 손잡이·상단 캐치 배치를 사용합니다.
하드웨어의 모양과 위치는 실제 제품을 선정하기 전의 참고 정보입니다.

- J1·J2: 고정틀·창짝 모서리.
- J3: 두 방향 창살이 모두 있을 때만 생성.
- J4V: 세로 창살과 가로 테두리의 결합이 있을 때만 생성.
- J4H: 가로 창살과 세로 테두리의 결합이 있을 때만 생성.

검사 결과는 `rule_id`, `expected`, `actual`, `tolerance`, `targets`, `status`를 구분합니다.
창살 수나 치수를 바꿔도 검사 ID는 변하지 않습니다. 결합 상세에 실제 존재하는 부재 계열이 쓰였는지도 확인합니다.

## 검증과 R3 보존

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/test_generator.py
```

시험은 생성기 밖의 임시 폴더에서 완성 패키지를 만듭니다. 테스트 기록은 `tests/results.json`에 저장됩니다.
기록을 바꾸지 않고 다시 확인하려면 `unittest`로 실행합니다. 웹 시험도 같은 방식입니다.

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_generator.py'
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m unittest discover -s tests -p 'test_web.py'
```

웹 시험은 임시 출력 폴더에서 예제 5종을 웹과 `run_job`으로 각각 만들어 패키지 ID를 대조하고, 사전 확인·오류 표시 위치·보안 거절·파일과 ZIP·생성 대기열·서버 프로세스 격리·소스 해시를 확인합니다.
화면의 요청 구성(`app.js`)이 예제 JSON을 그대로 만드는지는 `node`가 있을 때만 확인합니다.

R3 규격·부품·결합·네스팅 및 생산 윤곽 176개를 고정한 기준은 `tests/fixtures/r3_reference.json`입니다.
원래 `unified/`의 28개 파일도 대조합니다. 이전 리비전(R1·R2)과 조사 기록은 작업 트리에서 정리했고 git 태그 `R1`·`R2`·`R3`로 보관합니다.
새 시스템은 R3 코드를 별도 모듈로 확장했으며 기존 패키지를 덮어쓰지 않습니다.

시험 범위는 단문 좌우·양문, 외경/내경 입력 동등성과 재측정, 창살 0개 조합, 조건부 상세도, 하드웨어 부재와 열림 방향,
R3 형상 회귀, 소수 외곽 200건씩 일반/최적화 실행, 과밀·원판 초과·그림 초과 거부,
동시 성공/실패 작업, 단계별 오류·작업 프로세스 종료, 소스 번들 재생성, 무결성 검사입니다.

실제 제작용 최소 잔존 폭·끼움 공차·경첩/나사·후판/벽 고정·개폐 간섭·CAM·고정 지그는 PENDING입니다.
다중 원판은 후속 범위입니다. 개별 부재 초과(`nesting.part_fits_stock`)와
한 장 전체 배치 부족(`nesting.board_width`)은 각각 이유를 밝혀 거부합니다.
