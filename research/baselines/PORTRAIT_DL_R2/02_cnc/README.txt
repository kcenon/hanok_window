A3 세로형 한식 양개 창호 — 통합 CNC 패키지 / PORTRAIT_DL_R2
================================================================
이 폴더가 유일한 최신 제작 기준입니다. from_claude/from_codex와 혼합하지 마십시오.
모든 치수는 design_parameters.json에서 유도됩니다. design_spec.json을 직접 수정하지 마십시오.
정면은 폭 W x 높이 H, 부품은 길이 L x 폭 B x 두께 T입니다. 단위 mm.
실제 저장 DXF 재읽기: PASS_NOMINAL_DXF_GEOMETRY / 59개 검사 PASS.
이 PASS는 명목 CAD geometry 검사이지 실제 제작·하중·개폐 승인서가 아닙니다.

1. 규격
- 완성 외곽 W463 x H586; 고정틀 폭40, 내부383 x506.
- 좌우 창짝 각각 W187 x H500; 창짝 테두리 폭30.
- 바깥 고정틀 간극3, 중앙 간극3. 중앙 고정 기둥 없음.
- 각 창짝 창살 설치 개구부127 x440, 세로살2/가로살4.
- 창살 빈칸 35.67 x 80.00, 창짝당 교차점8개.
- 후면 그림 배치 기준영역317 x440, A3 세로형297 x420, 사방10 여유.
- 닫힌 정면의 연속 개구부가317 x440이라는 뜻이 아님.
- 중앙 폭63=세로재30+틈3+세로재30. 양쪽을 열면 중앙 세로재도 이동.
- 원판1220 x900 x20. 원판의1220방향(+X)이 목리, 모든 긴 부품이 X평행.
- 공구 기준 Ø6, 명목 pocket깊이10, 도그본R3.2, 관통 명목깊이20.

2. 부품표 / L x B x T
F01 고정틀 세로재 586 x 40 x 20 : 2개
F02 고정틀 가로재 463 x 40 x 20 : 2개
S01 창짝 세로재 500 x 30 x 20 : 4개
S02 창짝 가로재 187 x 30 x 20 : 4개
L01 세로 창살 460 x 10 x 20 : 4개
L02 가로 창살 147 x 10 x 20 : 8개
합계24개. 모든 부품에 별도의 ID annotation과 XDATA 메타데이터가 존재합니다.
최소 원판 여유20, 최소 부품 간격12. 부품 외접범위 X20~1111/Y20~304.

3. 가공 layer
BOARD_BOUNDARY : 원판 외곽, 절삭 금지.
CUT_THROUGH : 24개 closed LWPOLYLINE, 20두께 관통 외곽.
POCKET_10MM : 104개 closed LWPOLYLINE, A면에서 깊이10.
DOGBONE : 48개 exact circular-bulge closed LWPOLYLINE, 깊이10.
HINGE_REF : 경첩4개, 각 고정틀/창짝 날개 위치만 참고. 생산 가공 제외.
LATCH_REF : 손잡이2개/캐치2개 위치만 참고. 생산 가공 제외.
PART_ID : 부품ID. 새김가공 아님.
DIMENSIONS : 치수. 가공 금지.
GRAIN_DIRECTION : 목리방향. 가공 금지.
ASSEMBLY_REFERENCE : 조립/열림 참고. 가공 금지.
JOINT_DETAILS_REF : J1/J2/J3/J4 상세. 가공 금지.
NOTES : 제작 주석. 가공 금지.
DXF Model Space1:1, INSUNITS=mm. 모든 생산 contour의 Z=0이며 깊이는 layer/metadata에서 구분합니다.
CAM에서는 CUT_THROUGH, POCKET_10MM, DOGBONE만 명시적으로 선택하십시오.

4. 홈 수량과 실제 결합
J1 고정틀40 x40 x깊이10: 8홈, 4쌍.
J2 창짝30 x30 x깊이10: 16홈, 8쌍.
J3 창살10 x10 x깊이10: 32홈, 16개 교차점.
J4 끝단/안착10 x10 x깊이10: 48홈(끝단24+안착24), 24쌍.
J4는 창살 폭10과 삽입 길이10가 각각 다른 변이며 깊이10는 Z방향입니다.
총104개 기본 pocket / 52쌍의 결합. 도그본48개는 별도 집계.
S01 각각 안착4개; S02 각각 안착2개. 모든 창살 양 끝에 끝단 반턱2개.

5. A면 가공과 조립 시 뒤집기 — 매우 중요
원판의 공통 위쪽을 가공면A로 하여 pocket/도그본을 모두 한 면에서 가공합니다.
F01/S01/L01: 완성품에서 A면은 FRONT.
F02/S02/L02: 가공 후 뒤집어 완성품에서 A면은 BACK.
완성품 뒤z=0, 앞z=20. FRONT부품은 앞쪽z10~20을 제거,
BACK부품은 뒤쪽z0~10을 제거하여 잔존10씩이 상보적으로 맞물립니다.
모든 부품의 A면을 앞쪽으로 향하게 조립하면 안 됩니다.
좌우/상하의 정확한 조립 변환은 parts_manifest.csv의 affine에 기록됩니다.
XY 미러 그림만을 실제 뒤집기라고 오해하지 마십시오.

6. 도그본 및 개방 경계 CAM intent
모든 S01/S02 안착 pocket은 로컬 v=20~30이며 v=30쪽으로 개방됩니다.
안착 폭은 창살 폭10, 안착 깊이는 삽입 길이10로 서로 다른 값입니다.
닫힌 코너(u_min,20),(u_max,20)에 R3.2원2개를 사용합니다.
POCKET_10MM 사각형과 해당 DOGBONE 2개의 합집합을 같은 깊이10로 제거합니다.
도그본을 관통구멍이나 남겨둘 island로 처리하지 마십시오.
원은 true semicircle bulge2개를 가진 폐곡선이며 단순 참조 원이 아닙니다.
이 설계의 J1/J2/J3 및 끝단 pocket들은 전폭 또는 끝단 개방형 반턱입니다.
사각 pocket이 부품 경계에 닿는 면에서는 Ø6공구가 폐기재 쪽으로 넘어가며
어깨까지 가공할 수 있도록 CAM의 개방 경계/진입/연장 조건을 설정해야 합니다.
일반 닫힌 내부pocket 경로만 쓰면 일부 모서리에 잔재가 남을 수 있습니다.
104개 홈의 open_edges는 pocket_manifest.csv에 기록했습니다.
CAD 사각형은 부품 내부에 두고 실제 연장 toolpath는 CAM 담당자가 확정합니다.
관통컷과 pocket의 의도된 경계 공유는 중복 contour가 아닙니다.

7. 하드웨어와 후판
경첩4개: LEFT S01-1/F01-1, RIGHT S01-4/F01-2 각각2개.
기준 높이Y=103,483. 약40길이/약2깊이, 예시날개폭14는 REFERENCE ONLY.
폭14는 참고 위치를 보이기 위한 도형이며 실제 경첩 폭·구멍 치수가 아닙니다.
손잡이 참고중심(215,293),(248,293). 캐치 각창짝/고정틀에 독립1개씩.
그림 한 장과 별도 비목재 후판은 고정틀 뒤에 고정하며 창짝에 붙이지 않습니다.
그림이 창살에 닿지 않도록 실제 후방 이격과 지지방식을 확정하십시오.
현재 목재24개만으로 그림을 고정하거나 벽에 안전하게 설치할 수 있다는 뜻이 아닙니다.
후판/마운트/클립/벽고정/접착제/나사/경첩/캐치 등 별도 자재가 필요합니다.
열림 참고도의 (X,Z)=(41.5,24),(421.5,24)는 방향설명용 가상축입니다.
실제 경첩/후판/나사/두창짝의 동시회전 간섭, 하중, 90도열림은 검증미완(PENDING).
HINGE_REF/LATCH_REF를 현재 A면 가공프로그램에 포함하지 마십시오.
특히 BACK조립 부품의 하드웨어 앞면 위치가 A면 가공허용을 뜻하지 않습니다.

8. 가공·조립 순서
(1) 실제 원판 평탄도/두께/결함/목리/함수율/공구경을 확인하고 시험편으로 끼움공차 확정.
(2) 목리+X 유지, A면표시. 좁은10폭 창살이 흔들리지 않는 고정/지그/CAM방식 확정.
(3) 고정상태에서 pocket과 도그본 합집합을 먼저 깊이10 가공.
(4) 관통컷은 마지막에 실행하여 부품을 분리. 탭/얇은잔존층 등은 CAM에서 정함.
(5) 실제 부품에 ID/A면/좌우소속을 임시표시. PART_ID는 자동새김 경로가 아님.
(6) 고정틀 반턱4쌍을 가조립. 수평·직각·대각·두께를 확인.
(7) 각창짝의 L01/L02격자를 반턱으로 가조립하고 테두리안착에 넣어 맞춤 확인.
(8) 격자를 넣기 전에 테두리를 영구고정하지 말 것. 모든 홈방향/앞뒤를 맞출 것.
(9) 적합한 접착/체결방식을 작업자가 확정하여 고정틀과 각창짝을 고정.
(10) 실물경첩·캐치·손잡이를 선정하고 제품치수로 hardware별도도면을 수정한 뒤 설치.
(11) 기본3간극, 뒤틀림, 두창짝의 개폐순서/간섭/처짐을 실제확인.
(12) 별도 후판/그림/보호층/벽고정을 설치하고 나사 및 창살과의 간섭을 확인.
반턱은 위치를 기계적으로 안착시키지만 접착/체결 없이 분리되지 않는 잠금조인트는 아닙니다.
실내용 장식/그림보호용 명목설계입니다. 외기밀/수밀/유리받침/구조인증 창호가 아닙니다.

9. 검증과 한계
실제로 생성한 DXF를 저장한 뒤 ezdxf로 다시 읽어 59개 검사 PASS.
검사: 부품24, pocket104, 도그본48, 크기/위치/폐곡선/층/목리/12간격/20여유,
52쌍XY와앞뒤면/Z잔존영역, 의도치않은 재료겹침, 각부품의 조립참고 일치,
창살2/4 배치, 경첩4/손잡이2/캐치2 위치참고, DXF audit.
검사 기대값은 design_parameters.json에서 다시 유도하며 design_spec.json을 그대로 믿지 않습니다.
검증을 통과한 파일의 SHA256은 validation_report.json에 기록됩니다.
곡선포함 재료검사는 0.00001 mm 이하허용값으로 평탄화한 다각형 계산이며
반경/원호/bulge/내부포함은 별도로 DXF 원데이터에서도 확인합니다.
실제 가공맞춤·목재강도·동적개폐·벽고정·CAM시뮬레이션·기계운전은 승인하지 않았습니다.
기본10.00홈/10.00부품은 명목 무공차이며 시험편 후 공차보정이 필요합니다.

10. 파일 — 패키지 구성
패키지 루트/00_START_HERE.txt : 진입 안내
패키지 루트/package_manifest.json : 전체 파일의 경로·크기·SHA-256
패키지 루트/01_plan/MERGED_PLAN.md : 병합 계획서. 단독 재생성 사양
패키지 루트/01_plan/PLAN_RECONCILIATION.md : 선행 계획서 2건 대조와 채택 근거
패키지 루트/01_plan/SPEC_UNIFICATION.md : 구조 통일과 결함 수정 이력
이 폴더(02_cnc)의 파일:
design_parameters.json : 유일한 규격 원본. 여기만 수정합니다.
generate_spec.py : 파라미터에서 부품/홈/도그본/네스팅을 유도. design_spec.json 생성.
design_spec.json : 생성물. 직접 수정 금지.
hanok_window_A3_portrait_double_leaf_one_board_CNC.dxf : 최신 실제 DXF
01_one_board_nesting.png : 원판 전체 및 동일부품확대
02_joinery_details.png : J1/J2/J3/J4 및 깊이단면
03_assembly_reference.png : 세로형 양개 닫힘정면
04_opening_reference.png : 좌우열림 설명용 평면도 (REFERENCE ONLY)
05_all_pockets_closeup.png : 104홈/48도그본 위치 확대
validation_report.json : 실제저장DXF 재읽기검증
parts_manifest.csv / pocket_manifest.csv / dogbone_manifest.csv : 치수·좌표·대응표
hardware_reference_manifest.csv : 참고하드웨어만 분리집계
build_portrait_double_leaf.py / cad_helpers.py : DXF 생성·검증·도면 렌더링
verify_package.py : 파일 무결성 대조(기본 읽기전용). package_manifest.json 생성은 --write
requirements.txt : 검증에 사용한 Python 버전과 라이브러리

재실행: 이폴더에서 python build_portrait_double_leaf.py
기존DXF 검사만: python build_portrait_double_leaf.py --validate-only
규격 대조만: python generate_spec.py --compare <다른 design_spec.json>
무결성 대조: python verify_package.py           (읽기전용. 불일치 시 종료코드1)
매니페스트 재작성: python verify_package.py --write

재현 범위: 빌드는 PYTHONHASHSEED=0으로 스스로 재실행하고 DXF 메타데이터를 고정합니다.
- DXF는 파라미터만 같으면 항상 같은 바이트입니다. 폰트 환경과 무관합니다.
- PNG는 같은 폰트 파일과 같은 Pillow 버전이 잡힐 때만 같습니다.
  HANOK_FONT를 바꾸면 검사는 그대로 통과하지만 PNG 해시 5개가 전부 달라집니다.
  실제 사용된 폰트는 validation_report.json의 render_environment에 기록됩니다.
따라서 DXF 해시가 달라졌다면 파라미터나 코드가 바뀐 것이고,
PNG 해시만 달라졌다면 먼저 폰트 환경을 확인하십시오.
검사전용 결과는 validation_report_recheck.json이며 기존 PNG를 다시 만들지 않습니다.
필요폰트가 없으면 시스템DejaVu/Arial을 사용하며, HANOK_FONT 환경변수로 대체가능.
이패키지에는 폰트파일을 포함하지 않습니다.
