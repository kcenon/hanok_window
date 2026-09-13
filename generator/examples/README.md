# 생성 예제

예제 입력 5종과, 그 입력으로 만든 실제 패키지 5종입니다. 각 패키지는 저장 DXF 검사 67개와 패키지 파일 34개 무결성 대조를 통과했습니다.
JSON을 고쳐 새 설계를 만들 수 있고, 웹 화면에서는 "JSON 불러오기"로 같은 입력을 폼에 채울 수 있습니다.

| 예제 | 형식 | 크기 (mm) | 창살 (세로 × 가로) | 프리셋 | 부품 | 홈 | 도그본 |
|---|---|---|---|---|---|---|---|
| [double_r3](double_r3.json) | 양문 | 외경 463 × 586 | 2 × 4 | `hanok_A3_portrait_R3` | 24 | 104 | 48 |
| [double_inner_r3](double_inner_r3.json) | 양문 | 내경 383 × 506 | 2 × 4 | `hanok_A3_portrait_R3` | 24 | 104 | 48 |
| [single_right](single_right.json) | 단문, 오른쪽 경첩 | 외경 420 × 900 | 2 × 6 | `standard_v1` | 16 | 72 | 32 |
| [single_empty](single_empty.json) | 단문, 왼쪽 경첩 | 외경 420 × 900 | 0 × 0 | `standard_v1` | 8 | 16 | 0 |
| [double_600_800](double_600_800.json) | 양문 | 외경 600 × 800 | 2 × 4 | `standard_v1` | 24 | 104 | 48 |

`double_r3`는 R3 확정 설계를 생성기로 다시 만든 것입니다. `double_inner_r3`는 같은 창을 내경으로 입력한 것이어서 생산 윤곽이 `double_r3`와 같습니다.
프리셋을 적지 않은 예제는 기본 프리셋 `standard_v1`을 씁니다.

## 만들어진 패키지

[packages/](packages/)에 예제마다 생성기가 만든 패키지를 그대로 넣었습니다. 폴더 이름만 `output/packages/<패키지 ID>/` 대신 예제 이름으로 바꿨습니다. 패키지 ID는 각 폴더의 `package_manifest.json`에 있고, 무결성 대조는 폴더 이름과 관계없습니다.

> **제작 전 확인:** 이 DXF도 명목 CAD 기하만 검사했습니다. 끼움 공차·하드웨어·CAM을 시험편으로 확인하기 전에는 기계로 보내지 마십시오.

도면 번호는 01 원판 배치, 02 결합 상세, 03 조립 기준, 04 열림 기준, 05 전체 홈 확대입니다. 각 도면과 파일의 쓰임은 사용 설명서의 [패키지에 들어 있는 것](../docs/manual/README.md#패키지에-들어-있는-것)에 있습니다.

| 예제 | 패키지 ID | 도면 (PNG) | 파일 |
|---|---|---|---|
| [double_r3](packages/double_r3/) | `3d8e6187…` | [01](packages/double_r3/01_one_board_nesting.png) · [02](packages/double_r3/02_joinery_details.png) · [03](packages/double_r3/03_assembly_reference.png) · [04](packages/double_r3/04_opening_reference.png) · [05](packages/double_r3/05_all_pockets_closeup.png) | [README](packages/double_r3/README.txt) · [DXF](packages/double_r3/window.dxf) · [부품표](packages/double_r3/parts_manifest.csv) · [홈 좌표](packages/double_r3/pocket_manifest.csv) · [검사 기록](packages/double_r3/validation_report.json) |
| [double_inner_r3](packages/double_inner_r3/) | `633d258d…` | [01](packages/double_inner_r3/01_one_board_nesting.png) · [02](packages/double_inner_r3/02_joinery_details.png) · [03](packages/double_inner_r3/03_assembly_reference.png) · [04](packages/double_inner_r3/04_opening_reference.png) · [05](packages/double_inner_r3/05_all_pockets_closeup.png) | [README](packages/double_inner_r3/README.txt) · [DXF](packages/double_inner_r3/window.dxf) · [부품표](packages/double_inner_r3/parts_manifest.csv) · [홈 좌표](packages/double_inner_r3/pocket_manifest.csv) · [검사 기록](packages/double_inner_r3/validation_report.json) |
| [single_right](packages/single_right/) | `46b4d41d…` | [01](packages/single_right/01_one_board_nesting.png) · [02](packages/single_right/02_joinery_details.png) · [03](packages/single_right/03_assembly_reference.png) · [04](packages/single_right/04_opening_reference.png) · [05](packages/single_right/05_all_pockets_closeup.png) | [README](packages/single_right/README.txt) · [DXF](packages/single_right/window.dxf) · [부품표](packages/single_right/parts_manifest.csv) · [홈 좌표](packages/single_right/pocket_manifest.csv) · [검사 기록](packages/single_right/validation_report.json) |
| [single_empty](packages/single_empty/) | `58b3a3ca…` | [01](packages/single_empty/01_one_board_nesting.png) · [02](packages/single_empty/02_joinery_details.png) · [03](packages/single_empty/03_assembly_reference.png) · [04](packages/single_empty/04_opening_reference.png) · [05](packages/single_empty/05_all_pockets_closeup.png) | [README](packages/single_empty/README.txt) · [DXF](packages/single_empty/window.dxf) · [부품표](packages/single_empty/parts_manifest.csv) · [홈 좌표](packages/single_empty/pocket_manifest.csv) · [검사 기록](packages/single_empty/validation_report.json) |
| [double_600_800](packages/double_600_800/) | `c5cb9d35…` | [01](packages/double_600_800/01_one_board_nesting.png) · [02](packages/double_600_800/02_joinery_details.png) · [03](packages/double_600_800/03_assembly_reference.png) · [04](packages/double_600_800/04_opening_reference.png) · [05](packages/double_600_800/05_all_pockets_closeup.png) | [README](packages/double_600_800/README.txt) · [DXF](packages/double_600_800/window.dxf) · [부품표](packages/double_600_800/parts_manifest.csv) · [홈 좌표](packages/double_600_800/pocket_manifest.csv) · [검사 기록](packages/double_600_800/validation_report.json) |

## 확인하기

받은 패키지가 생성 당시 그대로인지 파일 해시로 대조합니다. PASS와 패키지 ID, 파일 34개가 나오면 그대로입니다.

```bash
cd generator
.venv/bin/python -m hanok_generator verify examples/packages/double_r3
```

패키지 안의 파일을 고치거나 새 파일을 두면 대조가 실패합니다. 패키지를 다시 만들어 볼 때는 `--output`을 패키지 밖에 두십시오.
같은 입력을 이 생성기로 만들면 같은 패키지 ID가 나옵니다. 다만 PNG는 설치된 폰트와 라이브러리에 따라 달라지므로 다른 컴퓨터에서는 패키지 ID가 다를 수 있습니다. 여기 패키지를 만든 환경(macOS arm64, Python 3.11.15, Arial 폰트)은 각 패키지의 `environment.json`에 있습니다.

## 만들기

예제 하나를 직접 만들 때는 명령줄을 씁니다. 결과는 `output/packages/<패키지 ID>/`에 생깁니다.

```bash
cd generator
.venv/bin/python -m hanok_generator build --input examples/double_r3.json --output output
```

`packages/`의 예제 패키지는 스크립트로 한꺼번에 다시 만듭니다. 패키지 ID를 정하는 생성기 파일이나 예제 입력을 바꾼 뒤에 실행합니다.

```bash
cd generator
.venv/bin/python examples/make_packages.py      # 약 8초
```

스크립트는 예제를 모두 임시 폴더에 만들고, 전부 통과했을 때만 `packages/`를 바꾼 뒤 사본마다 무결성을 대조합니다. 명령이 출력하는 JSON(패키지 ID, 검사 수, 부품·홈·도그본 수)을 모은 [built_packages.json](built_packages.json)도 새로 쓰며, 경로는 `generator/` 기준으로 저장소 안의 사본을 가리킵니다.
