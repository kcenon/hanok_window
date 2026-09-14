# 생성 예제

예제 입력 5종과 이 작업 공간에서 만든 패키지입니다. 각 패키지는 저장 DXF 검사 67개와 패키지 파일 34개 무결성 대조를 통과했습니다.
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
| double_r3 | `fb3e99cd…` | [README](../output/packages/fb3e99cd0b016dd39f3f637f8996bb4a238fcf416c9c75eb9e1ec4b10ea8acb4/README.txt) · [조립도](../output/packages/fb3e99cd0b016dd39f3f637f8996bb4a238fcf416c9c75eb9e1ec4b10ea8acb4/03_assembly_reference.png) · [열림도](../output/packages/fb3e99cd0b016dd39f3f637f8996bb4a238fcf416c9c75eb9e1ec4b10ea8acb4/04_opening_reference.png) · [DXF](../output/packages/fb3e99cd0b016dd39f3f637f8996bb4a238fcf416c9c75eb9e1ec4b10ea8acb4/window.dxf) |
| double_inner_r3 | `9a561d87…` | [README](../output/packages/9a561d87aaf8e4878c998e1f4e94179cb9086f5cf7be32da686ce736416cb112/README.txt) · [조립도](../output/packages/9a561d87aaf8e4878c998e1f4e94179cb9086f5cf7be32da686ce736416cb112/03_assembly_reference.png) · [열림도](../output/packages/9a561d87aaf8e4878c998e1f4e94179cb9086f5cf7be32da686ce736416cb112/04_opening_reference.png) · [DXF](../output/packages/9a561d87aaf8e4878c998e1f4e94179cb9086f5cf7be32da686ce736416cb112/window.dxf) |
| single_right | `08f61e5a…` | [README](../output/packages/08f61e5af3f81e25c59b4946a7702c2c6c0cb640f509baf5e3a9854f0b82fb38/README.txt) · [조립도](../output/packages/08f61e5af3f81e25c59b4946a7702c2c6c0cb640f509baf5e3a9854f0b82fb38/03_assembly_reference.png) · [열림도](../output/packages/08f61e5af3f81e25c59b4946a7702c2c6c0cb640f509baf5e3a9854f0b82fb38/04_opening_reference.png) · [DXF](../output/packages/08f61e5af3f81e25c59b4946a7702c2c6c0cb640f509baf5e3a9854f0b82fb38/window.dxf) |
| single_empty | `c1684be0…` | [README](../output/packages/c1684be062a1253c2a02e28ccecb6aa191ab671c2211560ed3cbf223f1de9ae2/README.txt) · [조립도](../output/packages/c1684be062a1253c2a02e28ccecb6aa191ab671c2211560ed3cbf223f1de9ae2/03_assembly_reference.png) · [열림도](../output/packages/c1684be062a1253c2a02e28ccecb6aa191ab671c2211560ed3cbf223f1de9ae2/04_opening_reference.png) · [DXF](../output/packages/c1684be062a1253c2a02e28ccecb6aa191ab671c2211560ed3cbf223f1de9ae2/window.dxf) |
| double_600_800 | `86afdc92…` | [README](../output/packages/86afdc9286007a18467401b00750c0a74dcd48baea05938ce4fc7182bd0c3746/README.txt) · [조립도](../output/packages/86afdc9286007a18467401b00750c0a74dcd48baea05938ce4fc7182bd0c3746/03_assembly_reference.png) · [열림도](../output/packages/86afdc9286007a18467401b00750c0a74dcd48baea05938ce4fc7182bd0c3746/04_opening_reference.png) · [DXF](../output/packages/86afdc9286007a18467401b00750c0a74dcd48baea05938ce4fc7182bd0c3746/window.dxf) |
