# 규격 통일 기록 / PORTRAIT_DL_R2

작성일 2026-09-11. 이 문서는 `hanok_window/` 아래 두 패키지를 하나로 합친 근거와 변경 내역입니다.

## 1. 확정된 설계 선택

**창살: 창짝당 세로 2 + 가로 4** (2026-09-10 확정)

| 항목 | 채택안 (세로2/가로4) | 미채택안 (세로1/가로5) |
|---|---|---|
| 창짝당 격자 | 3열 x 5단 | 2열 x 6단 |
| 빈칸 크기 | 약 35.67 x 80 | 58.5 x 65 |
| 창짝당 교차점 | 8 | 5 |
| 기본 홈 | 104 | 92 |
| 결합쌍 | 52 | 46 |

두 안은 부품 수(24개)는 같지만 홈 좌표와 수량이 달라 **부품표·가공 지침을 섞어 쓸 수 없습니다.**
채택안은 `from_codex`가 이미 구현한 패턴이므로, 설계 내용은 보존하고 관리 구조만 통일했습니다.

## 2. 통합 대상

| 원본 | 상태 | 사유 |
|---|---|---|
| `from_codex/.../02_CNC_current` (PORTRAIT_DL_R1) | 대체됨 | 창살 패턴은 동일. 규격이 JSON과 Python 양쪽에 중복 기술되어 있었음 |
| `from_claude/...one_board_CNC` | 미채택 | 창살 세로1/가로5. 이번 결정과 다른 설계안 |

원본 두 폴더는 **수정하지 않았습니다.** 이력 참고용으로 그대로 둡니다.

## 3. R1 대비 변경 내역

### 3.1 규격 원본을 한 곳으로 (핵심)

R1에서는 같은 규격이 두 곳에 따로 적혀 있었습니다.

- `design_spec.json` — 부품 24개, 홈 104개, 도그본 48개의 좌표를 **손으로 전부 나열**
- `build_portrait_double_leaf.py` — 검증기가 `X=[(127-20)/3+5, ...]`, `SIZES={'F01':(586.,40.,2), ...}`,
  `box(0,0,463,586)` 같은 **하드코딩 상수**로 같은 규격을 다시 기술

창살 개수나 치수를 바꾸면 양쪽을 수동으로 맞춰야 했고, 어긋나면 조용히 틀린 도면이 나옵니다.

R2에서는 `design_parameters.json` 하나만 규격 원본입니다.

```
design_parameters.json
        │
        ├─(generate_spec.py)──→ design_spec.json ──→ DXF / PNG / CSV
        │                         조립공간 교차 → 역아핀 변환 경로
        │
        └─(build 검증기)──────→ 기대 좌표
                                  창살 간격 공식 경로
                                        │
                          두 경로가 같은 좌표에 도달하는지 대조
```

생성 경로와 검증 경로를 일부러 다르게 두었기 때문에, 한쪽 계산이 틀리면
"같은 가정을 공유해서 둘 다 통과"하는 일이 아니라 **불일치로 드러납니다.**

유도 규칙 자체는 단순합니다.

- **결합부** = 같은 조립 그룹 안에서 수직재와 수평재가 겹치는 사각형 전부
- **도그본** = 홈 모서리 중 u, v 좌표가 모두 부품 내부에 갇힌 지점 전부
- **가공면** = 수직재는 A면이 앞, 수평재는 A면이 뒤 (뒤집어 조립)

이 세 규칙만으로 104개 홈, 48개 도그본, 52개 결합쌍이 정확히 재현됩니다.

### 3.2 설계 내용은 바뀌지 않았음 (검증됨)

```
$ python generate_spec.py --compare <R1의 design_spec.json>
IDENTICAL / design content vs design_spec.json / nesting positions excluded by design
```

부품 24개, 홈 104개, 도그본 48개의 **모든 좌표·ID·결합쌍·대응 관계가 1e-9 이내로 일치**합니다.
파라미터에서 유도한 결과가 R1의 수작업 좌표와 완전히 같다는 뜻이며,
파라미터화가 설계를 바꾸지 않았다는 증거입니다.

### 3.3 원판 배치(네스팅)는 알고리즘으로 대체

R1은 배치 좌표도 손으로 지정했습니다. R2는 `(계열, 부재폭)` 단위 선반 채우기
(first-fit-decreasing)로 계산합니다. 결과:

| | R1 | R2 |
|---|---|---|
| 선반 수 | 9단 | 8단 |
| 부품 외접범위 | X20~1081 / Y20~326 | X20~1111 / Y20~304 |
| 위치 동일 부품 | — | 24개 중 16개 |

바뀐 8개는 전부 가로 창살 L02입니다. R1이 비워 둔 L01 선반의 오른쪽 여유에 L02가 들어가면서
선반이 한 단 줄었습니다. 최소 부품 간격 12 mm와 원판 여유 20 mm는 그대로 만족합니다.
**배치는 가공 편의 문제이고 설계 내용이 아니므로**, 위 3.2의 대조에서는 제외했습니다.

### 3.4 실행 환경 명세 수정

R1의 `requirements.txt`는 `ezdxf==1.4.4 / shapely==2.1.2 / Pillow==12.3.0`이었으나
이 조합은 Python 3.10 이상을 요구해 현재 환경(Python 3.9.6)에서 설치되지 않습니다.
R2는 실제로 검증에 사용한 조합과 Python 버전 하한을 함께 기록합니다.

```
# Verified on Python 3.9.6 (PORTRAIT_DL_R2).
# Newer pins need Python 3.10+; these are the last releases that also run on 3.9.
ezdxf==1.4.2
shapely==2.0.7
Pillow==11.3.0
```

### 3.5 검사 항목 추가 (53 → 59)

| 추가된 검사 | 확인 내용 |
|---|---|
| `lattice_2_vertical_4_horizontal_bars_per_leaf` | 확정한 창살 패턴이 실제 DXF의 창짝별 부품 수와 맞는지 |
| `design_spec_on_disk_matches_parameters` | 디스크의 `design_spec.json`이 파라미터에서 다시 생성한 결과와 동일한지 |
| `half_lap_depth_10_is_half_of_stock_20` | 반턱 깊이가 두께의 정확히 절반인지 |
| `lattice_bars_evenly_spaced_in_measured_opening` | 조립 도형에서 직접 잰 창살 간격이 균등한지 |
| `revision_recorded_matches_parameters` | DXF에 기록된 리비전이 파라미터와 같은지 |
| `leaf_height_to_width_ratio_at_least_2.6` | 조립 도형에서 직접 잰 창짝 높이/폭이 하한 이상인지 (5절 결함 7) |

기존 53개 검사도 기대값을 상수 대신 파라미터에서 유도하도록 바꾸었고,
검사 이름에 실제 기대값이 들어가도록 했습니다 (`frame_463x586_inner383x506`,
`48_exact_R3.2_corner_reliefs_two_per_seat` 등).

### 3.6 바이트 단위 재현 빌드

같은 파라미터로 빌드하면 **항상 같은 바이트**가 나옵니다. 두 가지가 필요했습니다.

1. `ezdxf.options.write_fixed_meta_data_for_testing=True`
   — 저장 시점에 기록되던 `$TDCREATE`/`$TDUPDATE`/GUID 2개/ezdxf 스탬프를 상수로 고정.
2. `PYTHONHASHSEED=0`
   — ezdxf가 OBJECTS 섹션을 쓸 때 문자열 키 컬렉션을 순회하는데, Python의 해시
   무작위화 때문에 LAYOUT과 placeholder의 순서가 실행마다 뒤바뀌었습니다.
   빌드 스크립트가 이 변수를 세팅해 **스스로 한 번 재실행**합니다.

3회 연속 빌드에서 DXF와 PNG 해시가 모두 동일함을 확인했습니다.

**재현 범위는 산출물마다 다릅니다.** 위 두 조건은 빌드 내부의 비결정성만 제거합니다.
바깥에서 들어오는 입력이 하나 더 있습니다 — 폰트입니다.

| 산출물 | 재현 조건 | 근거 |
|---|---|---|
| DXF | 파라미터만 같으면 동일 | TEXT 엔티티만 저장하고 글리프 외곽선을 담지 않으므로 폰트와 무관 |
| PNG 5장 | 같은 폰트 파일 + 같은 Pillow 버전 | `cad_helpers.font()`가 기계에서 폰트를 찾아 래스터화 |

실측: `HANOK_FONT`만 바꿔 빌드하면 모든 검사는 그대로 통과하고 DXF는 바이트 동일한데
PNG 5장의 해시가 전부 달라집니다. 그래서 실제로 사용된 폰트를 기록합니다.

- `validation_report.json` → `render_environment.fonts`
- `requirements.txt` 주석
- `package_manifest.json` → `reproducible_build.render_environment`

**대가**: DXF 헤더의 생성일시(2000-01-01)와 GUID는 이제 의미 없는 라이브러리 상수입니다.
그래서 리비전 식별자는 다른 곳에 둡니다.

- 원판 도면 우측 상단 `REVISION PORTRAIT_DL_R2 / 2026-09-11 / GENERATED FROM ...` 표기
- DXF 문서 메타데이터 `HANOK_REVISION` / `HANOK_BUILD_DATE` / `HANOK_SOURCE_OF_TRUTH`
- `revision_recorded_matches_parameters` 검사가 저장 후에도 남아 있는지 확인

따라서 해시는 이렇게 해석하십시오.

| 목적 | 방법 |
|---|---|
| 받은 패키지가 손상·변조되지 않았는지 | `python verify_package.py` (읽기 전용, 불일치 시 종료코드1) |
| 다시 빌드한 DXF가 맞는지 | 해시가 같으면 동일. 다르면 파라미터나 코드가 바뀐 것 |
| PNG 해시만 달라졌을 때 | 먼저 `render_environment.fonts`를 이전 값과 비교 |

`verify_package.py`는 기본이 **읽기 전용 대조**이며, 매니페스트 재작성은 `--write`로
분리했습니다. 무결성을 확인하려는 명령이 발견한 내용을 그대로 기준으로 덮어써 버리면
애초에 잡으려던 변조를 잡을 수 없기 때문입니다. `.venv` 등 도구 디렉터리와
`validation_report_recheck.json`은 대상에서 제외합니다.

### 3.7 참고: from_claude 패키지에서 확인했던 문제

이번 통합안은 `from_codex` 계보 위에 세웠으므로 아래 문제는 R2에 존재하지 않습니다.
기록 목적으로만 남깁니다.

- `DOGBONE` 레이어에 생산용 R3.2 원 48개와 원판 밖 확대 상세도용 R19.2 원 2개가 섞여 있었음
  (CAM에서 레이어 전체 선택 시 오절삭 위험). R2의 `DOGBONE` 레이어는 생산용 48개뿐이며
  `references_never_on_machining_layers` 검사로 강제합니다.
- README의 검증 서술과 실제 파일 내용이 어긋났고, 재현할 검증 코드가 없었음.
  R2의 README는 검증 결과에서 자동 생성되므로 수치가 어긋날 수 없습니다.

## 4. 그대로 유지한 것

- 완성 외곽 463 x 586, 창짝 187 x 500, 고정틀 폭 40, 창짝 테두리 폭 30
- 사방 간극 3, 중앙 간극 3, 중앙 고정 기둥 없음
- 그림 배치 기준영역 317 x 440, A3 297 x 420, 사방 10 여유
- 원판 1220 x 900 x 20, 목리 +X, 최소 간격 12 / 여유 20
- 공구 기준 Ø6, 홈 깊이 10, 도그본 R3.2, 관통 20
- 레이어 구성, A면 가공 + 뒤집어 조립 원칙, 개방 경계 CAM 지침
- 참고 하드웨어 4경첩 / 2손잡이 / 2캐치 위치

## 5. 검토에서 발견되어 수정한 결함 (2026-09-11)

R2 최초본을 독립 검토한 결과 결함이 확인되어 수정했습니다. 1~4는 1차 검토,
5~6은 그 수정본의 재검토, 7~8은 병합 계획서(`MERGED_PLAN.md`, `PLAN_RECONCILIATION.md`)를
두 원문과 대조한 검토에서 나온 것입니다.
각 항목은 임시 복사본에서 결함 상황을 재현해 새 검사가 실제로 잡는지 확인했습니다.

| # | 결함 | 원인 | 수정 |
|---|---|---|---|
| 1 | `pocket_depth=9`여도 전 검사 통과. 실제로는 결합부에 2 mm 겹침 | 간섭 검사가 두께를 상보적인 두 구간으로 나눈다고 **가정** | 파라미터 단계에 `2*깊이==두께` 단언 추가. 간섭 검사를 실제 잔존 Z 구간(FRONT는 `0~두께-깊이`, BACK은 `깊이~두께`) 기반으로 재작성 |
| 2 | 무결성 확인 명령이 변조된 파일을 그대로 기준으로 덮어씀. `.venv` 포함. 빌드 후 매니페스트가 갱신되지 않음 | 생성 전용 도구를 확인 용도로 사용 | `verify_package.py`로 교체. 기본이 읽기 전용 대조, 재작성은 `--write`. 도구 디렉터리 제외. 빌드 마지막에 자동 재작성 |
| 3 | 공유 간격 함수에 **대칭** 오류를 넣어도 전 검사 통과 | 생성기와 검증기가 `bar_offsets()`를 공유. 대칭 오류는 좌표 집합의 대칭성을 유지해 기존 좌표 검사를 통과 | 조립 도형에서 창살 간격을 직접 재어 균등성을 확인하는 검사 추가. 유도값을 일절 참조하지 않음 |
| 4 | `end_lap_length=12`로 바꾸면 좌표 검사 실패 | 검증기가 안착 홈 깊이에 삽입 길이(`LAP`) 대신 창살 폭(`BW`)을 사용 | `SM-LAP`으로 수정. J4 상세도와 README 서술도 두 값을 구분하도록 수정 |
| 5 | 4번 수정 후에도 `LAP=12`에서 설명 두 곳이 여전히 `10 x 10`, `10 mm engagement` | 형상은 고쳤으나 README의 J4 요약과 상세도 단면(삽입 방향 단면인데 폭 `BW`를 사용)이 남아 있었음 | README 요약을 `BW x LAP`으로, 단면 형상과 치수·설명을 `LAP` 기준으로 수정. 라벨을 `12 mm seat depth, 10 mm in Z`로 바꿔 두 축을 분리 |
| 6 | 폰트만 바꿔도 PNG 5장 해시가 전부 변함. "해시가 다르면 파라미터나 코드가 바뀐 것"이라는 설명이 틀림 | 폰트는 패키지가 아니라 기계에서 오는 입력인데 재현 범위에 포함하지 않았음 | 산출물별로 재현 조건을 분리해 문서화(3.6절). 사용된 폰트를 `render_environment`·`requirements.txt`·매니페스트에 기록해 해시 불일치를 진단 가능하게 함 |
| 7 | 창짝 세장비 2.6 하한이 검사에 없음. 외곽 523 × 646·여유 40 → 창짝 217 × 560(2.58)인데 58개 검사와 독립 재검증 통과 | 대조표가 C 체크리스트 21번을 "흡수했다"고 적었지만, 계획서에는 "높이 > 폭" 문장만 남고 검사로 옮겨지지 않았음. 치수 사슬의 관계식은 비율을 제한하지 않음 | 파라미터 `leaf.min_height_to_width_ratio: 2.6` 신설, `derive()` 단언, 저장 DXF의 조립 도형에서 비율을 재는 `leaf_height_to_width_ratio_at_least_2.6` 추가(58 → 59). 함께 흡수했다던 대칭·맞댐부 항목도 주입 시험으로 실제 검출을 확인하고, `MERGED_PLAN.md` 15절 표 모든 행에 검사 이름을 적음 |
| 8 | 대조표가 C의 검증 시점을 "저장 전"으로만 분류 | C 13절 첫 문장만 보고 마지막 지시(407–408행: DXF 재읽기, 렌더링 육안 확인)를 빠뜨림 | 저장 후 재읽기와 렌더링 확인을 양쪽 공통 요구로 정정. 실제 차이인 "재읽기 파일에 적용하는 검사 범위"를 표로 구분(`PLAN_RECONCILIATION.md` 2.7절) |

재현 결과:

```
[CAUGHT] pocket_depth=9, 파라미터 단언 있음  → 빌드 거부: "half-lap joints need pocket_depth (9) ..."
[CAUGHT] pocket_depth=9, 단언 제거          → no_nominal_assembled_solid_interpenetration 실패
                                              half_lap_depth_9_is_half_of_stock_20 실패
[CAUGHT] bar_offsets() 대칭 오류            → lattice_bars_evenly_spaced_in_measured_opening 만 실패
                                              (기존 좌표 검사는 통과 — 이 검사가 없으면 못 잡음)
[  OK  ] end_lap_length=12                  → 58개 검사 통과
                                              README "안착10 x12", 상세도 "12 mm seat depth, 10 mm in Z"
                                              J4 헤더 "10 x 12 pocket / depth 10 / stock 20"
[CAUGHT] README 변조 + .venv 추가            → verify_package.py: CHANGED README.txt, 종료코드1, .venv 무시
[  OK  ] HANOK_FONT만 변경                   → 58개 검사 통과, DXF 바이트 동일,
                                              PNG 5장 전부 변경, render_environment.fonts에 변경 기록
```

정정 두 가지:

- "바이트 단위 재빌드 불가"라는 최초 설명은 틀렸습니다. 3.6절 방식으로 재현 가능하며
  현재 빌드는 실제로 재현됩니다.
- 그 다음 "같은 파라미터면 항상 같은 바이트"라는 설명도 PNG에 대해서는 틀렸습니다.
  DXF에만 해당하며, PNG는 폰트 환경까지 같아야 합니다.

7~8 재현 결과:

```
[CAUGHT] 외곽 523x646 / 여유 40, 단언 있음       → 빌드 거부: "leaf height / width (560 / 217
                                                   = 2.5806) is below the required minimum 2.6"
[CAUGHT] 같은 조건, 단언 제거 (저장 전 검증)     → leaf_height_to_width_ratio_at_least_2.6 만 실패
[CAUGHT] 2.58로 저장한 DXF를 --validate-only     → leaf_height_to_width_ratio_at_least_2.6 만 실패
[CAUGHT] S01-2 맞댐 모서리에 전장 10 mm 반턱     → total_base_pockets_104, pockets_per_part,
                                                   all_pocket_coordinates_match_exact_formulas,
                                                   52_joint_pairs_XY_match_opposite_faces 실패
[CAUGHT] 우측 창짝 창살 1개만 +2 mm (결합은 유도) → all_pocket_coordinates_match_exact_formulas,
                                                   lattice_bars_evenly_spaced_in_measured_opening 실패
[  OK  ] 확정 규격                               → 59개 통과, 실측 세장비 2.673797 (좌우 동일)
[  OK  ] 미채택 1 + 5                            → 59개 통과, 홈 92개
```

## 6. 남은 미결 항목 (제작 전 필수)

이 패키지는 명목 CAD geometry까지만 보증합니다. 다음은 여전히 PENDING입니다.

1. 실물 경첩·나사·캐치·손잡이 선정과 제품 치수 반영
2. 후판 / 벽 고정 방식, 그림과 창살의 후방 이격
3. 끼움 공차 — 현재 홈과 부재 모두 명목 10.00 (무공차). 시험편 필수
4. 두 창짝 동시 개폐 간섭, 처짐, 하중
5. CAM 경로 — 개방 경계 오버런, 공구 보정, 고정 지그, 탭/잔존층, 이송·회전수

---

전체 재생성 및 검증 결과는 `validation_report.json`,
파일별 해시는 `package_manifest.json`에 있습니다.
