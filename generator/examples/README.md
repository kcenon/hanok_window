# 생성 예제

예제 입력 5종과 이 작업 공간에서 만든 패키지입니다. 각 패키지는 저장 DXF 검사 71개와 패키지 파일 36개 무결성 대조를 통과했습니다.
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
| double_r3 | `08bb7527…` | [README](../output/packages/645289be237f4c571443f4866f9da6baacce2b526f92a2a9571e8a4404cd4869/README.txt) · [조립도](../output/packages/645289be237f4c571443f4866f9da6baacce2b526f92a2a9571e8a4404cd4869/03_assembly_reference.png) · [열림도](../output/packages/645289be237f4c571443f4866f9da6baacce2b526f92a2a9571e8a4404cd4869/04_opening_reference.png) · [DXF](../output/packages/645289be237f4c571443f4866f9da6baacce2b526f92a2a9571e8a4404cd4869/window.dxf) |
| double_inner_r3 | `4447558f…` | [README](../output/packages/e2a6f4a4707fcf0a470e4d6dd92c11b8a2dbbb593db0599f8826b57ab1feb604/README.txt) · [조립도](../output/packages/e2a6f4a4707fcf0a470e4d6dd92c11b8a2dbbb593db0599f8826b57ab1feb604/03_assembly_reference.png) · [열림도](../output/packages/e2a6f4a4707fcf0a470e4d6dd92c11b8a2dbbb593db0599f8826b57ab1feb604/04_opening_reference.png) · [DXF](../output/packages/e2a6f4a4707fcf0a470e4d6dd92c11b8a2dbbb593db0599f8826b57ab1feb604/window.dxf) |
| single_right | `fe901c3a…` | [README](../output/packages/1d4e969d324aa6a55db1baa15189119c26059f1b386dfc0e48fbf3aa732164e7/README.txt) · [조립도](../output/packages/1d4e969d324aa6a55db1baa15189119c26059f1b386dfc0e48fbf3aa732164e7/03_assembly_reference.png) · [열림도](../output/packages/1d4e969d324aa6a55db1baa15189119c26059f1b386dfc0e48fbf3aa732164e7/04_opening_reference.png) · [DXF](../output/packages/1d4e969d324aa6a55db1baa15189119c26059f1b386dfc0e48fbf3aa732164e7/window.dxf) |
| single_empty | `6ae3609b…` | [README](../output/packages/58985b9fab1b698124cc6d482d8bcc2eab72f254b62910fec21c1bc63c1ba3b2/README.txt) · [조립도](../output/packages/58985b9fab1b698124cc6d482d8bcc2eab72f254b62910fec21c1bc63c1ba3b2/03_assembly_reference.png) · [열림도](../output/packages/58985b9fab1b698124cc6d482d8bcc2eab72f254b62910fec21c1bc63c1ba3b2/04_opening_reference.png) · [DXF](../output/packages/58985b9fab1b698124cc6d482d8bcc2eab72f254b62910fec21c1bc63c1ba3b2/window.dxf) |
| double_600_800 | `a0042ddb…` | [README](../output/packages/8f6e70301e1e7121a73727d9eb995e4f5138a99b114723ea2bdbf62b2cb83408/README.txt) · [조립도](../output/packages/8f6e70301e1e7121a73727d9eb995e4f5138a99b114723ea2bdbf62b2cb83408/03_assembly_reference.png) · [열림도](../output/packages/8f6e70301e1e7121a73727d9eb995e4f5138a99b114723ea2bdbf62b2cb83408/04_opening_reference.png) · [DXF](../output/packages/8f6e70301e1e7121a73727d9eb995e4f5138a99b114723ea2bdbf62b2cb83408/window.dxf) |
