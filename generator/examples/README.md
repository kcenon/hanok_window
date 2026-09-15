# 생성 예제

예제 입력 5종과 이 작업 공간에서 만든 패키지입니다. 각 패키지는 저장 DXF 검사 68개와 패키지 파일 34개 무결성 대조를 통과했습니다.
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

## 만들기

```bash
cd generator
.venv/bin/python -m hanok_generator build --input examples/double_r3.json --output output
```

명령이 출력하는 JSON(패키지 ID, 검사 수, 부품·홈·도그본 수, 경로)을 예제 5종에 대해 모은 것이 [built_packages.json](built_packages.json)입니다. 경로는 `generator/` 기준 상대 경로로 바꿔 적었습니다.

## 이 작업 공간의 패키지

`output/`은 git에 넣지 않으므로 아래 링크는 이 컴퓨터에서 예제를 만든 뒤에만 열립니다. PNG는 설치된 폰트에 따라 달라지므로 다른 컴퓨터에서 만들면 패키지 ID가 다를 수 있습니다. 아래 ID는 Windows 11(AMD64), CPython 3.11.15, Pillow 12.3.0에서 만든 값입니다.

| 예제 | 패키지 ID | 파일 |
|---|---|---|
| double_r3 | `204e70b0…` | [README](../output/packages/204e70b0d19909411d34504f4456a6ebb51bb110e0ab709f8dfd5496e413c7d0/README.txt) · [조립도](../output/packages/204e70b0d19909411d34504f4456a6ebb51bb110e0ab709f8dfd5496e413c7d0/03_assembly_reference.png) · [열림도](../output/packages/204e70b0d19909411d34504f4456a6ebb51bb110e0ab709f8dfd5496e413c7d0/04_opening_reference.png) · [DXF](../output/packages/204e70b0d19909411d34504f4456a6ebb51bb110e0ab709f8dfd5496e413c7d0/window.dxf) |
| double_inner_r3 | `f5d245f0…` | [README](../output/packages/f5d245f0ea3b3773ee4ea28eb5917093dc4f1ad0b141a352ea2777d630d9b6cf/README.txt) · [조립도](../output/packages/f5d245f0ea3b3773ee4ea28eb5917093dc4f1ad0b141a352ea2777d630d9b6cf/03_assembly_reference.png) · [열림도](../output/packages/f5d245f0ea3b3773ee4ea28eb5917093dc4f1ad0b141a352ea2777d630d9b6cf/04_opening_reference.png) · [DXF](../output/packages/f5d245f0ea3b3773ee4ea28eb5917093dc4f1ad0b141a352ea2777d630d9b6cf/window.dxf) |
| single_right | `7a806eed…` | [README](../output/packages/7a806eed6eda546262336b0b9437ffb7787f54064dea7b863b78bdb255aff9c2/README.txt) · [조립도](../output/packages/7a806eed6eda546262336b0b9437ffb7787f54064dea7b863b78bdb255aff9c2/03_assembly_reference.png) · [열림도](../output/packages/7a806eed6eda546262336b0b9437ffb7787f54064dea7b863b78bdb255aff9c2/04_opening_reference.png) · [DXF](../output/packages/7a806eed6eda546262336b0b9437ffb7787f54064dea7b863b78bdb255aff9c2/window.dxf) |
| single_empty | `b22e3f8b…` | [README](../output/packages/b22e3f8b8ab28e39bac3ac7fde90ba7b0b4b34cd170293c2877f14485c72031b/README.txt) · [조립도](../output/packages/b22e3f8b8ab28e39bac3ac7fde90ba7b0b4b34cd170293c2877f14485c72031b/03_assembly_reference.png) · [열림도](../output/packages/b22e3f8b8ab28e39bac3ac7fde90ba7b0b4b34cd170293c2877f14485c72031b/04_opening_reference.png) · [DXF](../output/packages/b22e3f8b8ab28e39bac3ac7fde90ba7b0b4b34cd170293c2877f14485c72031b/window.dxf) |
| double_600_800 | `addca175…` | [README](../output/packages/addca175eb84dccec87c7bad6f36f723fe1b74dd85e05abe978411cc089d8616/README.txt) · [조립도](../output/packages/addca175eb84dccec87c7bad6f36f723fe1b74dd85e05abe978411cc089d8616/03_assembly_reference.png) · [열림도](../output/packages/addca175eb84dccec87c7bad6f36f723fe1b74dd85e05abe978411cc089d8616/04_opening_reference.png) · [DXF](../output/packages/addca175eb84dccec87c7bad6f36f723fe1b74dd85e05abe978411cc089d8616/window.dxf) |
