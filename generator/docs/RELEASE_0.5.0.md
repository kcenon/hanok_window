# 0.5.0 릴리스 안내

배포 버전은 **0.5.0**, 생성 엔진은 **0.3.0**입니다. 마지막 태그 `v0.4.1` 이후의 Windows 호환 수정, 액자형 설계, DWG 내려받기와 AI 출력, 검증 보강을 함께 담습니다. 상세 구현과 당시의 측정 결과는 [변경 기록](CHANGELOG.md)에 있습니다.

## 0.4.x에서 전환할 때

**같은 입력이라도 0.5.0에서 다시 만든 모든 패키지의 `package_id`는 0.4.x에서 만든 값과 달라집니다.** 패키지에는 재생성용 소스가 들어가고 그 바이트도 ID 계산에 포함됩니다. 엔진의 파일 입출력 수정과 뒤이은 소스 추가·변경이 모두 영향을 줍니다. 배포 버전과 엔진 버전은 의도적으로 구분합니다.

- 같은 설계인지 비교할 때는 `revision`을 사용합니다. 같은 `revision`이어도 패키지의 파일 바이트와 ID는 다를 수 있습니다.
- 같은 ID를 재현하려면 입력과 소스뿐 아니라 운영체제, Python·라이브러리 버전, 글꼴 등 실행 환경도 같아야 합니다. 다른 운영체제 사이의 전체 패키지 ID 일치를 보장하지 않습니다.
- 기존 패키지와 포함 소스는 생성 당시 기록으로 보관합니다. 새로 생성한 패키지의 DXF·AI·CSV·검증 기록은 그 패키지 안의 파일을 함께 사용합니다.
- 0.5.0 전체에는 참고 도면과 가공 메모의 위치, 원판 두께에 따른 홈 색 수정도 들어 있습니다. 0.4.x와 비교해 DXF·PNG가 모두 그대로라고 해석하면 안 됩니다.

현재 새 패키지는 **검사 71개**, 매니페스트에 기록하는 **파일 38개**입니다. 전체 ZIP은 `package_manifest.json`까지 **39개**입니다. `window.ai`는 이 파일 목록에 들어가고, 요청할 때 변환하는 DWG는 들어가지 않습니다.

## 바뀐 기능

| 범위 | 0.5.0의 동작 |
|---|---|
| Windows와 파일 입출력 | 엔진이 글 파일을 UTF-8·LF로 읽고 써서 한국어 로캘에서도 `PYTHONUTF8` 없이 실행합니다. 빌더의 전역 설계 상태를 줄이고, 동시에 끝나는 생성 작업의 `latest.json` 교체를 재시도합니다. ([#4](https://github.com/kcenon/hanok_window/issues/4), [#5](https://github.com/kcenon/hanok_window/issues/5), [#9](https://github.com/kcenon/hanok_window/issues/9)) |
| 참고 도면 위치 | 원판 길이에 따라 조립도·상세도·열림도를 원판 밖에 배치하고, 저장한 도면에서 겹침을 검사합니다. ([#11](https://github.com/kcenon/hanok_window/issues/11)) |
| 홈 색 | 원판 두께가 20 mm가 아닌 설계도 원판 배치와 전체 홈 확대 PNG에 홈 색을 표시합니다. ([#12](https://github.com/kcenon/hanok_window/issues/12)) |
| 4×8 원판 | `standard_4x8_v1` 프리셋의 기본 원판은 2400 × 1200 × 20 mm, 가장자리 여유는 10 mm, 부재 간격은 12 mm입니다. 가공 메모와 결 방향 화살표도 원판 밖으로 옮겼습니다. ([#13](https://github.com/kcenon/hanok_window/issues/13)) |
| 조립 깊이 | 부재별 Z 위치를 두어 두께 방향으로 떨어진 부재를 입체 겹침으로 세지 않습니다. ([#14](https://github.com/kcenon/hanok_window/issues/14)) |
| 액자형 | 화판 크기·두께, 덮는 폭, 끼움 여유를 받아 창 크기를 계산하고, 같은 원판에서 뒤틀 4개를 더 만듭니다. ([#15](https://github.com/kcenon/hanok_window/issues/15)) |
| 액자형 화면과 도구 | 웹 입력·미리보기·고침 제안, LLM 도구의 입력과 설명, 그림 설명서에 액자형을 반영했습니다. ([#16](https://github.com/kcenon/hanok_window/issues/16)) |
| DWG 내려받기 | ODA File Converter를 별도로 설치하면 패키지 화면에서 AutoCAD 2010 형식 DWG를 받습니다. 변환기가 없으면 설치 안내를 표시하고 나머지 패키지 기능은 그대로 사용할 수 있습니다. ([#17](https://github.com/kcenon/hanok_window/issues/17)) |
| AI 출력 | 외부 변환기 없이 Illustrator 8 계열의 옛 PostScript 텍스트 AI를 만들고 되읽어 DXF와 대조합니다. 원판 가공 도형·부재 번호·하드웨어 참고 표시를 레이어로 나눠 담으며, 조립도·상세도·열림도와 치수·가공 메모는 포함하지 않습니다. ([#18](https://github.com/kcenon/hanok_window/issues/18)) |

DWG는 같은 DXF를 변환해도 바이트가 달라질 수 있어 내려받을 때마다 변환합니다. 변환기 버전은 웹 응답과 화면에 표시하며, 패키지의 `environment.json`에는 넣지 않습니다. 변환기는 릴리스에 함께 배포하지 않습니다. 설치와 이 저장소의 비상업적 CI 사용 조건은 [DWG CI 안내](DWG_CI.md)에 있습니다.

## 검증과 유지보수 보강

- 세 운영체제의 R3 매니페스트를 실제로 비교하고, AI 해시를 바꾼 산출물은 실패하는지 확인합니다. 기존 운영체제·글꼴 차이만 지정된 파일과 운영체제 쌍에서 허용하며, `window.ai`는 엄격하게 비교합니다. CI 의존성 다운로드에는 pip 캐시를 사용합니다. ([#27](https://github.com/kcenon/hanok_window/issues/27), [#28](https://github.com/kcenon/hanok_window/issues/28))
- 윈도 CI에 선택적 ODA 설치와 R3·액자형 A2의 실제 DWG 왕복 시험을 추가했습니다. 변환기를 사용할 수 없으면 해당 시험을 명시적으로 건너뜁니다. 우분투·맥은 변환기를 설치하지 않습니다. 윈도 웹 서버의 시작·종료·재시작과 실패 처리도 시험합니다. ([#29](https://github.com/kcenon/hanok_window/issues/29), [#30](https://github.com/kcenon/hanok_window/issues/30))
- LLM 도구 설명의 검사 수는 순서가 있는 검사 목록에서 계산합니다. 도구 결과는 `jsonschema`로 실제 출력 스키마와 대조합니다. ([#31](https://github.com/kcenon/hanok_window/issues/31), [#32](https://github.com/kcenon/hanok_window/issues/32))
- 설명서 그림 스크립트가 Windows의 Chrome을 찾고, `--check`로 기준 그림을 바꾸지 않고 최신 여부를 확인합니다. 현재 설명서의 일부 화면은 파일 37개였던 패키지의 촬영 기록이며 새 패키지의 파일 38개와 구분해 설명합니다. ([#33](https://github.com/kcenon/hanok_window/issues/33))
- AI 쓰기·읽기 검증·필수 파일·검사 목록·생성 README의 연결을 출력 형식 등록 정보로 모았습니다. 확장 방법은 [출력 형식 등록 안내](OUTPUT_FORMATS.md)에 있습니다. PNG·CSV·README 함수 분리와 전체 검사 이름 상수화는 후속 범위입니다. ([#34](https://github.com/kcenon/hanok_window/issues/34))

#34만의 변경 전후 비교에서는 동일 윈도 환경의 예제 5종에서 DXF·AI·PNG·CSV·설계 JSON·README·검증 기록의 내용 파일 17개가 바이트까지 같았습니다. 포함 소스, 환경 기록의 소스 해시, 매니페스트가 달라져 ID와 파일 수가 바뀌었습니다. 이 결과는 0.4.x에서 0.5.0으로 넘어갈 때 모든 생성 파일이 같다는 뜻은 아닙니다.

## 설치와 시험

Python **3.11 이상**이 필요합니다. [설치 안내](../README.md#설치), [Windows 안내](../README.md#windows), [그림 설명서](manual/README.md)를 따릅니다. 실행 의존성은 `generator/requirements.lock`에 고정하며, 시험할 때는 이를 포함하는 `generator/requirements-test.lock`을 설치합니다. 시험 의존성은 일반 실행이나 생성 패키지의 `source/requirements.txt`에 추가되지 않습니다.

현재 [CI](https://github.com/kcenon/hanok_window/actions/workflows/tests.yml)는 윈도·맥·우분투에서 인코딩, 패키지 비교, 설명서 그림, 출력 등록, 생성기, 웹, LLM의 일곱 시험 묶음을 실행합니다. 실제 산출물의 운영체제 간 비교는 별도 작업에서 수행합니다. 실행 명령과 비교 예외의 근거는 [검증 안내](../README.md#검증)에 있습니다. 문서만 바꾼 PR도 이 검증을 모두 거칩니다.

## 아직 직접 확인하지 못한 것

- 사용자 PC의 Illustrator에서 R3 `window.ai`를 열어 레이어 7종과 실제 크기·배율을 확인하는 항목은 [#18](https://github.com/kcenon/hanok_window/issues/18)에 남아 있습니다. 자동 되읽기 검증을 통과했지만 Illustrator에서 직접 열어 본 결과는 없습니다.
- 사용하려는 프로그램에서 2010 형식 DWG를 직접 여는 항목은 [#17](https://github.com/kcenon/hanok_window/issues/17)에 남아 있습니다. ODA 왕복과 검사 71개 통과는 그 프로그램의 직접 열기 확인과 별도로 기록합니다.
- 실제 제작의 끼움 공차·하드웨어·CAM 경로 등은 계속 확인 전입니다. [범위와 한계](../README.md#범위와-한계)를 따릅니다.
