한옥 창호 CAD 패키지 / HANOK_GEN_V1_04a2ec4c4f06
형식: DOUBLE LEAF
외곽: 463 x 586 mm. 창짝 2개, 각각 187 x 500 mm.
크기 기준: 외경(완성 외곽) 463 x 586 mm 입력. 외경 463 x 586, 내경 383 x 506 mm.
창짝당 창살: 세로 2, 가로 4. 교차점 8개.
부품 24, 홈 104, 도그본 48, 결합쌍 52.
원판: 1220 x 900 x 20 mm. 부재 길이는 목리 X 방향.
가공 깊이: 10 mm. 모든 가공은 A면. 공구 지름 6, 도그본 R3.2.
창짝-고정틀 간극 3 mm. 창짝 사이 간극 3 mm.
그림: 297 x 420 mm, 후면 기준영역 안에 중앙 배치, 각 변 최소 여유 10 mm.
실제 존재하는 결합 상세: J1, J2, J3, J4V, J4H
경첩 4, 손잡이 2, 캐치 2: 실물 선정 전 참고 위치.
경첩 부재: S01-1/F01-1, S01-4/F01-2
손잡이 부재: S01-2, S01-3

저장 DXF 재검증: 67개 검사 PASS. 검사 ID·기대값·실측값·허용 오차는 validation_report.json.
실측 최소 홈 사이 폭: 29.266666666666424; 가장자리 폭: 16.799999999999955; 잔존 두께: 10.0 mm.
제작용 최소값은 미확정(null/PENDING). 명목 기하 합격은 제작 승인이나 강도 보증이 아닙니다.
부재는 명목 무공차입니다. 시험편·끼움 공차·재료·하드웨어·후판 고정·개폐 간섭·CAM·고정 지그를 확인해야 합니다.
CUT_THROUGH는 전체 두께. POCKET과 DOGBONE은 부모 홈과 합쳐 절삭합니다. 개방 경계는 폐기물 방향 오버런이 필요합니다.
HINGE_REF와 LATCH_REF는 생산 가공에서 제외합니다. 공구 경로·탭·이송·회전수·G-code는 포함하지 않습니다.

파일: window.dxf, PNG 5장, CSV 4종, design_request.json, design_parameters.json, design_spec.json,
resolved_parameters.json, validation_report.json, environment.json, package_manifest.json, source/.
재생성: source/requirements.txt를 설치하고 PYTHONPATH=source python -m hanok_generator build --input design_request.json --output rebuilt
검증: PYTHONPATH=source python -m hanok_generator verify .
DXF는 고정 해시 시드와 메타데이터를 사용합니다. PNG 재현에는 environment.json의 폰트와 라이브러리도 같아야 합니다.
파일을 수정한 뒤 기존 매니페스트를 덮어쓰지 마십시오. 새 입력으로 새 패키지를 생성하십시오.
