한옥 창호 CAD 패키지 / HANOK_GEN_V1_f844adc5013a
형식: DOUBLE LEAF
외곽: 484 x 658 mm. 창짝 2개, 각각 197.5 x 572 mm.
크기 기준: 내경(고정틀 안목) 420 x 594 mm 입력. 외경 484 x 658, 내경 404 x 578 mm.
창짝당 창살: 세로 2, 가로 4. 교차점 8개.
부품 28, 홈 104, 도그본 48, 결합쌍 52.
원판: 2400 x 1200 x 20 mm. 부재 길이는 목리 X 방향.
가공 깊이: 10 mm. 모든 가공은 A면. 공구 지름 6, 도그본 R3.2.
창짝-고정틀 간극 3 mm. 창짝 사이 간극 3 mm.
화판: 420 x 594 x 3 mm. 고정틀이 각 변 8 mm를 덮습니다.
뒤틀(B01·B02) 4개: 폭 31 mm, 안쪽 422 x 596 mm, 끼움 여유 1 mm, 맞댄 이음.
층: 고정틀·창짝·창살은 Z 0~20 mm, 뒤틀은 Z -20~0 mm. 그 안에 스페이서 3 mm와 화판 3 mm가 들어갑니다.
스페이서·뒷판·걸이 철물은 별도 조달이며 PENDING입니다. 뒤틀 모서리 맞댄 이음의 접착·고정 방법도 확인해야 합니다.
실제 존재하는 결합 상세: J1, J2, J3, J4V, J4H, BF
경첩 4, 손잡이 2, 캐치 2: 실물 선정 전 참고 위치.
경첩 부재: S01-1/F01-1, S01-4/F01-2
손잡이 부재: S01-2, S01-3

저장 DXF 재검증: 71개 검사 PASS. 검사 ID·기대값·실측값·허용 오차는 validation_report.json.
실측 최소 홈 사이 폭: 32.766666666666424; 가장자리 폭: 16.799999999999955; 잔존 두께: 10.0 mm.
제작용 최소값은 미확정(null/PENDING). 명목 기하 합격은 제작 승인이나 강도 보증이 아닙니다.
부재는 명목 무공차입니다. 시험편·끼움 공차·재료·하드웨어·후판 고정·개폐 간섭·CAM·고정 지그를 확인해야 합니다.
CUT_THROUGH는 전체 두께. POCKET과 DOGBONE은 부모 홈과 합쳐 절삭합니다. 개방 경계는 폐기물 방향 오버런이 필요합니다.
HINGE_REF와 LATCH_REF는 생산 가공에서 제외합니다. 공구 경로·탭·이송·회전수·G-code는 포함하지 않습니다.

파일: window.dxf, window.ai, PNG 5장, CSV 4종, design_request.json, design_parameters.json, design_spec.json,
resolved_parameters.json, validation_report.json, environment.json, package_manifest.json, source/.
재생성: source/requirements.txt를 설치하고 PYTHONPATH=source python -m hanok_generator build --input design_request.json --output rebuilt
검증: PYTHONPATH=source python -m hanok_generator verify .
DXF는 고정 해시 시드와 메타데이터를 사용합니다. PNG 재현에는 environment.json의 폰트와 라이브러리도 같아야 합니다.
파일을 수정한 뒤 기존 매니페스트를 덮어쓰지 마십시오. 새 입력으로 새 패키지를 생성하십시오.
