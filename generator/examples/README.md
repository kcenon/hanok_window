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
| double_r3 | `ab5a7bcd…` | [README](../output/packages/ab5a7bcd7c57abe302c9d98b245d3d06aea54f84085e859b14c14b9f2abdb264/README.txt) · [조립도](../output/packages/ab5a7bcd7c57abe302c9d98b245d3d06aea54f84085e859b14c14b9f2abdb264/03_assembly_reference.png) · [열림도](../output/packages/ab5a7bcd7c57abe302c9d98b245d3d06aea54f84085e859b14c14b9f2abdb264/04_opening_reference.png) · [DXF](../output/packages/ab5a7bcd7c57abe302c9d98b245d3d06aea54f84085e859b14c14b9f2abdb264/window.dxf) |
| double_inner_r3 | `cad54045…` | [README](../output/packages/cad54045a36519cd7d2e4689e63d3d26330aff142eefaf7e90e29daa3ec8d5a0/README.txt) · [조립도](../output/packages/cad54045a36519cd7d2e4689e63d3d26330aff142eefaf7e90e29daa3ec8d5a0/03_assembly_reference.png) · [열림도](../output/packages/cad54045a36519cd7d2e4689e63d3d26330aff142eefaf7e90e29daa3ec8d5a0/04_opening_reference.png) · [DXF](../output/packages/cad54045a36519cd7d2e4689e63d3d26330aff142eefaf7e90e29daa3ec8d5a0/window.dxf) |
| single_right | `951feff9…` | [README](../output/packages/951feff9ebc7d51181d651e1ac2885e1c0d0b3b97a83dc0623cb27c5def57536/README.txt) · [조립도](../output/packages/951feff9ebc7d51181d651e1ac2885e1c0d0b3b97a83dc0623cb27c5def57536/03_assembly_reference.png) · [열림도](../output/packages/951feff9ebc7d51181d651e1ac2885e1c0d0b3b97a83dc0623cb27c5def57536/04_opening_reference.png) · [DXF](../output/packages/951feff9ebc7d51181d651e1ac2885e1c0d0b3b97a83dc0623cb27c5def57536/window.dxf) |
| single_empty | `3d9f0d3f…` | [README](../output/packages/3d9f0d3fec51a1c32fbe5d9b8397afbfd9ae45de159367be25951f897fed58c9/README.txt) · [조립도](../output/packages/3d9f0d3fec51a1c32fbe5d9b8397afbfd9ae45de159367be25951f897fed58c9/03_assembly_reference.png) · [열림도](../output/packages/3d9f0d3fec51a1c32fbe5d9b8397afbfd9ae45de159367be25951f897fed58c9/04_opening_reference.png) · [DXF](../output/packages/3d9f0d3fec51a1c32fbe5d9b8397afbfd9ae45de159367be25951f897fed58c9/window.dxf) |
| double_600_800 | `25e12783…` | [README](../output/packages/25e12783ebfa85b2201be3d1ecfd642fee1203279d8db4633d9e24b4f8b2f573/README.txt) · [조립도](../output/packages/25e12783ebfa85b2201be3d1ecfd642fee1203279d8db4633d9e24b4f8b2f573/03_assembly_reference.png) · [열림도](../output/packages/25e12783ebfa85b2201be3d1ecfd642fee1203279d8db4633d9e24b4f8b2f573/04_opening_reference.png) · [DXF](../output/packages/25e12783ebfa85b2201be3d1ecfd642fee1203279d8db4633d9e24b4f8b2f573/window.dxf) |
