# 생성 예제

입력 JSON을 CLI의 `--input`으로 사용하거나 웹 화면의 JSON 불러오기로 열 수 있습니다.
생성된 파일은 [예제 패키지 목록](packages/README.md)에서 바로 볼 수 있습니다.
각 폴더에는 DXF·AI·PNG·CSV·검증 기록과 재생성 소스가 함께 있습니다.

| 예제 | 형식 | 크기 기준 | 창살 (세로 × 가로) | 프리셋 |
|---|---|---|---|---|
| [double_r3](double_r3.json) | 양문 | 외경 463 × 586 mm | 2 × 4 | hanok_A3_portrait_R3 |
| [double_inner_r3](double_inner_r3.json) | 양문 | 내경 383 × 506 mm | 2 × 4 | hanok_A3_portrait_R3 |
| [single_right](single_right.json) | 단문, 오른쪽 경첩 | 외경 420 × 900 mm | 2 × 6 | standard_v1 |
| [single_empty](single_empty.json) | 단문, 왼쪽 경첩 | 외경 420 × 900 mm | 0 × 0 | standard_v1 |
| [double_600_800](double_600_800.json) | 양문 | 외경 600 × 800 mm | 2 × 4 | standard_v1 |
| [double_4x8](double_4x8.json) | 양문 | 외경 900 × 1200 mm | 2 × 6 | standard_4x8_v1 |
| [artwork_a2](artwork_a2.json) | 양문 액자형 | 화판 420 × 594 mm | 2 × 4 | standard_4x8_v1 |

`double_r3`와 `double_inner_r3`는 같은 생산 형상을 서로 다른 크기 기준으로 입력합니다.
다른 형상·환경의 파일을 섞지 말고 같은 패키지의 도면과 표를 함께 사용합니다.
실제 제작 상태는 PENDING입니다. [사용자 프로그램과 제작 확인](../docs/ACCEPTANCE.md)을 따릅니다.

## 만들기와 검증

`generator/`에서 실행합니다.

```bash
.venv/bin/python -m hanok_generator build --input examples/double_r3.json --output output
.venv/bin/python examples/make_packages.py
.venv/bin/python examples/make_packages.py --check
```

`make_packages.py`는 모든 예제를 임시 폴더에 생성하고 검사한 뒤 `packages/`와
그 안의 `index.json`·`README.md`를 함께 교체합니다. 생성 실패 시 기존 예제를 유지합니다.
`--check`는 저장된 패키지·입력·포함 소스와 생성 목록을 읽기 전용으로 대조합니다.
엔진이나 예제 입력을 고치면 예제를 다시 생성해야 합니다.

패키지 ID는 실행 환경에도 의존합니다. 전체 바이트를 다시 만들려면 패키지의
`environment.json`에 적힌 Python·의존성·폰트 조건도 맞춰야 합니다.
[이전 생성 기록](built_packages.json)은 당시의 이력으로 보존하며 현재 패키지 목록은
[packages/index.json](packages/index.json)입니다.
