# 변경 기록

생성기의 버전별 구현·검증 기록이다. 오래된 것부터 적는다.
2026-09-13에 `generator/IMPLEMENTATION.md`에서 이 파일로 옮겼다. 그 전 기록에 나오는 `unified/`는 지금의 `r3_reference/`다.

## 0.1.0: 첫 구현 범위

버전 0.1.0, 2026-09-12. Python 3.11.15 환경에서 구현·검증했다.
기존 `unified/`를 수정하지 않고 R3 기하 코드를 `hanok_generator/engine/`에서 확장했다.
R3의 부품·홈·도그본 및 네스팅 기준과 176개 생산 윤곽은 `tests/fixtures/r3_reference.json`에 고정했다.

| 범위 | 구현 | 확인 |
|---|---|---|
| 1. 회귀 기반 | R3 규격·윤곽·원본 파일 해시 기준 | 176개 생산 윤곽의 좌표·bulge·메타데이터와 전체 spec(리비전 제외) 동일 |
| 2. 외곽 기준 입력 | `model.py`, JSON 스키마, 두 프리셋, 그림 포함 검사, 깊이 유도 | 600×800을 외곽 입력만으로 생성; 그림 크기·세장비는 선택 프리셋 규칙 |
| 3. 형식 일반화 | `formats.py`, 명시적 빌더 설정, 단문 하드웨어·열림도·조건부 상세도, 고정 검사 ID | 단문 좌우/양문 × 2+4·0+4·2+0·0+0 및 추가 크기·그림·창살 입력, 각 66개 검사 |
| 4. 작업별 CLI | `cli.py`, `jobs.py`, `worker.py`, `package.py` | 완성 패키지 동시 생성, 실패 격리, 읽기 전용 검증, 포함 소스로 재생성 |

빌더의 전역 치수와 도면 공간은 전용 작업 프로세스 안에서만 사용한다. import 시 입력 파일을 읽는 동작은 제거했다.
공개 API는 `run_job()`이며 같은 프로세스에서 빌더를 여러 스레드로 호출하는 API를 제공하지 않는다.
치수·부재·결합·네스팅 유도 자체는 입력 사전으로 호출하는 순수 계산 모듈이다.

R3에서 고정된 수치 비교·실제 원호 측정·홈 절삭 영역 분리·비개방 가장자리 검사는 유지했다.
0개 방향에서는 실제 창짝 개구부 전체를 빈칸 하나로 측정한다. 도그본 0개 CSV도 헤더를 기록한다.
J3/J4V/J4H 상세는 실제 창살 조합에 따라 생략되며 저장 도면의 상세 종류와 부재 계열을 검사한다.
단문 경첩은 지정 세로재에, 손잡이와 캐치 참고 형상은 반대 세로재에 배치한다.

패키지는 한 작업 폴더에서 모두 생성한 뒤 누락·PNG 디코딩·DXF 해시·파일 해시를 검증한다.
완료 폴더를 새 내용 ID로 보존하고 `latest.json` 참조만 교체한다.
CAD·CSV·렌더·매니페스트·공개·참조 전환 단계의 예외와 렌더 단계의 작업 프로세스 종료를 주입해
이전 공개 패키지의 무결성이 유지됨을 확인했다. 실제 전원 장애 후 파일 영속성을 시험한 것은 아니다.

재생성 입력은 사용자가 제출한 필드를 그대로 보관하고, 정규화된 입력·실제 값·출처는 별도 resolved 기록에 둔다.
이 구분이 있어 기본값을 생략한 입력도 포함 소스로 다시 실행했을 때 출처 기록까지 동일해진다.
소스 번들을 독립 경로에서 `-O`로 실행한 결과 DXF뿐 아니라 전체 패키지 내용 ID도 동일했다.

`tests/results.json`은 현재 실행 소스의 SHA-256과 결과를 기록한다.
12개 시험 메서드 안에서 일반·최적화 각각 소수 외곽 200건, 입력 거부·잘못된 상세/경첩 주입,
완성 패키지 16개 기본 행렬, 성공 8건/실패 2건 동시 실행, 7종 실패 단계, 무결성 변조를 확인한다.
소수 400건은 DXF 저장·재읽기까지이며 모든 건의 PNG를 다시 렌더한 것은 아니다.
출력 경로가 소스 폴더 아래에 있어도 이전 산출물·소스 번들을 실행 소스로 재귀 수집하지 않도록,
소스 내보내기는 패키지 모듈·엔진·프리셋·스키마만 명시적으로 수집한다.

최종 설치용 wheel을 별도 경로에 설치해 단문 우측 경첩·창살 0+4의 전체 패키지를 생성했다.
저장 DXF 66개 검사와 파일 34개 무결성 검사를 통과했고, 설치된 소스가 회귀 시험에 사용한 소스와 일치했다.
예제 4종도 같은 최종 소스로 생성했다. 최종 대조 기록(`tests/release_verification.json`, 지금은 커밋 `a489cad`에만 있음)에
wheel 해시, 예제 패키지 ID, R3 28개·from_codex 37개 원본의 무변경 결과를 기록했다.

다중 원판, 웹 화면, 실물 하드웨어·부재 강도·끼움 공차·동적 개폐 간섭·CAM 경로는 이 버전에서 확정하지 않는다.
현재 원판 초과는 단일 부재 초과와 전체 배치 부족을 서로 다른 규칙으로 거부한다.
제작용 최소 잔존 폭은 임의 값으로 합격 처리하지 않고 실측값과 PENDING을 함께 기록한다.

## 0.2.0 추가: 외경/내경 기준 입력

2026-09-12. 크기를 `outer_mm`(외경, 완성 외곽) 또는 `inner_mm`(내경, 고정틀 안목) 중 하나로 받는다. 둘 다 주거나 둘 다 빠지면 `input.size_basis`로 거부한다.
CLI는 `--size`에 `--size-basis outer|inner`를 더하며 기본은 `outer`다.
내경은 창짝이 들어가는 고정틀 안쪽 치수다. `model.resolve()`가 외곽 = 내경 + 2 × `frame.member_width`로 유도해 엔진에 넘기므로 `generate_spec.py`는 바꾸지 않았다. 유도한 외곽도 3000 mm 상한을 따른다.
외경 입력의 정규화 요청은 0.1.0과 같게 두어 기존 revision을 유지한다(R3 `HANOK_GEN_V1_04a2ec4c4f06`, 600 × 800 `HANOK_GEN_V1_4ab69eea15db`). 내경 입력은 `inner_mm`를 요청에 남긴다.
입력 기준과 요청 치수는 `design_parameters.json`의 `size`에, 유도 근거는 `resolved_parameters.json`의 provenance에 기록한다.

저장 DXF 검사에 `requested_size_matches_measured_frame`를 추가해 설계당 검사가 67개가 되었다. 조립된 고정틀 도형의 바깥 경계와 안쪽 개구부를 다시 재어 입력 기준의 치수와 대조하고, `targets`에는 `outer_mm` 또는 `inner_mm`를 기록한다.
조립도는 외경과 내경 치수를 모두 그리고 입력 기준에 `(INPUT)`을 붙인다. PNG 일람표와 패키지 README에도 기준과 두 치수를 적는다.

| 확인 | 결과 |
|---|---|
| 내경 383 × 506 + R3 프리셋 | 외경 463 × 586 빌드와 design_spec(리비전 제외)·생산 윤곽·메타데이터 동일 |
| 소수 내경 340.3 × 820.7 단문 | 저장 DXF 재측정 차이 1e-7 mm 이내로 PASS |
| CLI `--size-basis inner` | 요청이 `inner_mm`로 해석되고 외곽 463.5 × 586.25 유도 |
| 입력 거부 | 둘 다 지정·둘 다 누락은 `input.size_basis`, 내경 1 mm 미만·유도 외곽 3000 mm 초과는 `input.range` |
| 회귀 시험 | 14개 메서드 PASS, 101.6초. `tests/results.json`의 소스 해시 16개가 현재 소스와 일치 |
| 예제 | `double_inner_r3` 추가, 5종 재생성. 각 67개 검사와 파일 34개 무결성 대조 PASS |

0.2.0 wheel 설치 검증은 하지 않았다.

### 작업 트리 정리 (0.2.0 이후)

git 도입 뒤 과거 파일을 작업 트리에서 정리했다. 아래 추적 파일은 첫 커밋 `a489cad`(태그 `R1`·`R2`·`R3`·`v0.2.0`)에 그대로 있어 `git checkout R1 -- from_codex`처럼 복원할 수 있다.
- `from_codex/`(R1), `from_claude/`(기각된 1+5 안), `research/`(R2 보관본과 조사 기록)
- 0.1.0 배포 기록 `tests/release_verification.json`·`tests/wheel_result.json`

생성기 시험의 원본 무변경 대조는 `unified/` 28개 파일만 남겼다. 추적하지 않던 0.1.0 wheel·`build/`·`egg-info`와 참조되지 않는 0.1.0 산출 패키지 8개는 삭제했다.

## 0.3.0 추가: 로컬 웹 화면

2026-09-13. 웹 화면 설계 문서의 결정 5가지를 추천안대로 확정해 구현했다. 이 컴퓨터에서만 쓰고(`127.0.0.1`), 표준 라이브러리 HTTP 서버와 빌드 단계 없는 HTML·CSS·ES 모듈로 만든다. 배포 버전은 0.3.0, 엔진 `__version__`은 0.2.0이다. 내경은 고정틀 안목으로 확정했고, 외경↔내경을 바꾸면 같은 창이 되도록 값을 바꿔 넣는다.

| 파일 | 내용 |
|---|---|
| `web/server.py` | `ThreadingHTTPServer`, 고정 경로표, Host·Origin·본문 형식·64 KiB 검사, CSP 등 보안 헤더, 정적 파일 고정 목록 |
| `web/service.py` | meta(프리셋 규칙은 `model.resolve`에 물어 기술), 사전 확인(`resolve` → `derive`·`build_parts` → `build`), 패키지 요약 캐시, 매니페스트 해시를 대조한 파일·ZIP·480 px 축소판 |
| `web/builds.py` | `run_job`을 기다리는 스레드 풀(동시 2개·대기 8개), 최근 100개 상태 기록, 실패 검사 요약 |
| `web/static/` | `index.html`, `app.css`, `app.js`(폼·요청 구성·경로), `preview.js`(엔진 사각형 → SVG), `packages.js`(기록·패키지 화면·도면 뷰어), `messages.js`(`rule_id` → 한국어) |

설계 문서의 모듈 목록에서 `packages.js`를 따로 뗐다. 기록·패키지 화면과 뷰어는 설계 화면과 상태를 공유하지 않기 때문이다.
패키지 `source/`에 들어가는 파일은 바꾸지 않았다(`package.source_files()`는 하위 폴더를 수집하지 않는다). 웹 시험이 `tests/results.json`의 소스 해시 16개와 현재 소스가 같음을 확인한다.
builder는 서버 프로세스에 올리지 않는다. 사전 확인은 순수 계산 모듈만 쓰며, 그림을 기준영역 가운데에 놓는 식 한 줄만 `builder.configure`와 같은 식을 서비스에 두었다.

오류는 두 단계로 나눈다. 사전 확인 오류는 422와 함께 입력 묶음(`where`)을 돌려주어 해당 칸에 표시한다. 창살 빈칸이 닫히면 엔진 규칙을 그대로 써서 개수를 줄여 가며 통과하는 최대 개수를 찾아 제안한다.
생성 실패는 실패한 검사만 줄여서 돌려주고, 전체 기록은 `failures/`에 남는다. 예를 들어 창살 9+30은 사전 확인을 통과하지만 3.5초 뒤 `distinct_machining_regions_separated`로 실패한다. 화면에는 S01-1의 홈 P03과 P04가 붙는다는 것(겹침 5.89 mm²)과, 빈칸 4.52 mm가 도그본 반지름 합 6.4 mm보다 좁다는 것을 적는다.

| 확인 | 결과 |
|---|---|
| 웹 시험 `tests/test_web.py` | 13개 PASS, 약 9초. 예제 5종의 웹 생성과 `run_job` 패키지 ID 일치, 사전 확인 = `hanok-window resolve`, 오류 12종의 규칙·표시 위치, 보안 거절 12종, 파일 34개와 ZIP 35개 해시, 변조 파일 409, 대기열 429, builder 미로드, 소스 해시, `app.js` 요청 구성(node) |
| 기존 시험 | 14개 메서드 PASS, 100.6초 |
| R3 바이트 대조 | 웹에서 `examples/double_r3.json`으로 만든 패키지의 package_id가 예제 `3d8e6187…`과 같고, 파일 35개가 모두 동일. 생성 1.7초 |
| 사전 확인 속도 | HTTP 포함 R3 2.2 ms |
| 화면 | Chrome을 DevTools 프로토콜로 조작해 1440 px·390 px, 밝은·어두운 테마에서 확인했다. 대상은 설계, 원판 배치, 입력 오류, 생성 실패, 생성 성공, 기록, 패키지, 도면 뷰어, JSON 불러오기·저장이다. 390 px에서 모든 화면의 문서 폭이 화면 폭과 같다 |
| 키보드 | Tab 31번으로 건너뛰기 링크부터 생성 버튼까지 모든 입력을 지나고, 화살표로 창살 수를 바꾼 뒤 Ctrl+Enter로 생성해 패키지 화면에 도착 |

0.3.0 wheel 설치 검증은 하지 않았다. `hanok-window-web` 명령은 이 작업 공간의 편집 가능 설치(`pip install -e .`)를 다시 해서 만들었다.

## 0.3.1 추가: 웹 서버 켜고 끄기

2026-09-13. 웹 서버를 터미널 앞에 띄워 두고 Ctrl+C로 끄던 방식에 더해, 백그라운드에서 켜고 끄는 `web.sh`와 Finder용 `web-start.command`·`web-stop.command`를 추가했다. 형태(터미널 명령과 더블클릭 파일), 켤 때 브라우저 자동 열기, 0.3.1 태그는 사용자가 추천안대로 골랐다. 배포 버전만 0.3.1이고 엔진은 0.2.0 그대로다.

| 파일 | 내용 |
|---|---|
| `web.sh` | generator 폴더로 옮겨 `.venv/bin/python -m hanok_generator.web.control`을 실행한다. 가상환경이 없으면 설치 명령을 알려 준다 |
| `web-start.command`, `web-stop.command` | Finder에서 두 번 누르면 `web.sh start`, `web.sh stop`을 실행한다 |
| `web/control.py` | `start`·`stop`·`restart`·`status`·`log`. 서버를 새 세션에서 띄우고 `/api/meta`가 응답할 때까지 기다린 뒤 브라우저를 연다 |
| `web/__main__.py` | SIGTERM을 Ctrl+C와 같은 종료 경로로 받는다. 포트 오류 문구를 "127.0.0.1:8765을" 대신 "127.0.0.1:8765 포트를"로 고쳤다(숫자에 따라 조사가 틀렸다) |

pid 파일에는 비정상 종료나 재부팅 뒤 남은 pid가 다른 프로세스에 다시 쓰일 수 있다는 약점이 있어, 이를 잠금으로 막는다. `start`는 `output/.web/server.json`을 배타 잠금한 채 서버를 띄우고 그 파일 기술자를 서버에 넘긴다(`pass_fds`). 잠금은 서버가 끝나야 풀리므로, 잠금이 걸려 있을 때만 기록의 pid가 살아 있는 그 서버다. BSD `pidfile(3)`와 같은 방식이다. `ps`로 명령줄을 대조하지 않으므로 프로세스 목록을 볼 수 없는 환경(이 작업의 sandbox)에서도 시험이 돌고, 같은 순간 두 번 눌러도 잠금을 먼저 잡은 쪽만 서버를 띄운다.
`stop`은 SIGTERM을 보내고 잠금이 풀릴 때까지 기다린다. 서버는 이를 Ctrl+C처럼 받아 진행 중인 생성을 끝내고 대기 중인 생성을 취소한다. 신호는 서버 프로세스에만 가므로 생성 작업 프로세스는 끊기지 않는다. 150초(작업 제한 120초에 여유를 더함) 안에 끝나지 않으면 SIGKILL을 보낸다.
`start`는 그 포트에서 이미 다른 서버가 응답하면 새로 띄우지 않고, 띄운 서버가 바로 끝나면 서버 기록의 마지막 줄을 보여 준다.

| 확인 | 결과 |
|---|---|
| 웹 시험 `tests/test_web.py` | 18개 PASS, 14.6초. 새 시험 5개: 켜기·다시 켜기·끄기(브라우저 열기는 `BROWSER` 환경 변수로 대신 확인), 죽은 서버의 기록과 그 pid를 이어받은 다른 프로세스는 건드리지 않음, 다른 서버가 쓰는 포트 거절, 시작 실패 때 서버 기록 표시, `web.sh`와 두 `.command` 파일 |
| 기존 시험 | 14개 메서드 PASS, 102.2초 |
| 생성 중 끄기 | `web.sh`로 켠 서버에 R3 생성을 넣고 바로 `stop`: 대기 안내를 띄우고 1.7초 뒤 꺼졌으며, 생성은 끝까지 진행되어 예제와 같은 패키지 `3d8e6187…`을 남겼다 |
| Finder | 더블클릭은 사용자 화면에 Terminal 창을 띄우므로 하지 않았다. 두 `.command` 파일을 다른 폴더에서 직접 실행해 확인했고, 파일에는 격리 속성(`com.apple.quarantine`)이 없다 |

## 저장소 문서·폴더 정리 (0.3.1 이후)

2026-09-13. 저장소 입구와 문서 배치를 정리했다. 문서는 사용자 결정에 따라 한국어로 쓴다. 입구 README와 설명서 재구성, 브랜치 squash 병합(태그 없음)은 추천안대로, `unified/` 이름 변경은 사용자가 골랐다. 코드 동작과 생성 결과는 바뀌지 않아 버전을 올리지 않았다.

| 바뀐 것 | 내용 |
|---|---|
| 루트 `README.md` | 새로 만들었다. 저장소 소개, 바로 시작, 폴더 지도, 할 일별 갈 곳, 지킬 규칙, R3 규격, 태그 이력, 시험. `00_READ_FIRST.txt`의 내용을 옮기고 그 파일은 지웠다 |
| `unified/` → `r3_reference/` | 이름만 바꿨다. 파일 30개는 내용 그대로이고 회귀 시험의 경로 한 줄(`test_generator.py`)만 고쳤다. 폴더 안 문서는 해시로 고정되어 있어 옛 경로(`from_codex/` 등) 언급이 그대로 남는다 |
| `generator/README.md` | 설치 → 웹 화면 → 명령줄 → 입력 → 산출물 → 검증 → 범위와 한계 → 폴더 구성 순서로 다시 짜고 목차를 달았다. 명령 표, `requirements.lock` 설치법, 출력 폴더의 `.staging/`·`.web/`, 모듈별 역할과 패키지 ID에 들어가는 파일 설명을 더했다 |
| `IMPLEMENTATION.md` → `docs/CHANGELOG.md` | 옮기고 제목만 정리했다. 본문은 그대로다 |
| `examples/GENERATED.md` → `examples/README.md` | 예제 5종의 입력·부품 수 표와 만드는 법을 더하고, 패키지 링크를 상대 경로로 바꿨다 |
| 절대 경로 | 문서와 `examples/built_packages.json`에 있던 `/Users/…` 경로를 상대 경로로 바꿨다 |

| 확인 | 결과 |
|---|---|
| 기존 시험 | 14개 메서드 PASS, 101.3초. `r3_reference/` 파일 28개의 SHA-256이 기준과 같다 |
| 웹 시험 | 18개 PASS, 15.1초 |
| 문서 링크 | 네 문서의 상대 링크 48개와 제목 앵커가 모두 실제 파일·제목을 가리킨다 |
| 절대 경로 | `r3_reference/` 밖의 추적 파일에 `/Users/` 경로가 없다 |

## 0.4.0 추가: LLM 도구와 MCP 서버

2026-09-13. LLM이 도구 호출로 생성기를 쓰도록 도구 7개와 연동 통로를 추가했다. 범위(LLM이 생성기를 부르는 쪽만), 표준 라이브러리로 직접 만든 MCP 서버, 영어로 쓴 모델용 문구, v0.4.0 태그는 사용자가 추천안대로 골랐다. 생성기가 LLM API를 불러 대화하는 명령은 만들지 않았다. 새 의존성과 외부 네트워크는 없고 엔진은 0.2.0 그대로다.

| 파일 | 내용 |
|---|---|
| `llm/tools.py` | 도구 7개(`describe_generator`, `check_design`, `build_package`, `list_packages`, `get_package`, `verify_package`, `get_drawing`), 입력 스키마, 규칙별 영어 고침 안내(`hint`), 요청 정규화, 네 형식(`mcp`·`openai`·`openai-responses`·`anthropic`) 정의 내보내기 |
| `llm/mcp.py` | MCP stdio 서버(JSON-RPC 2.0). 프로토콜 버전 협상, `initialize`·`ping`·`tools/list`·`tools/call`, 일괄 요청, 표준 오류 코드. stdout에는 프로토콜 메시지만 쓴다 |
| `llm/__main__.py` | `hanok-window-llm tools`(도구 정의 출력)와 `call`(도구 하나 실행, 도면 이미지 파일 저장, 종료 코드 0·1·2) |
| `mcp.sh` | MCP 클라이언트에 등록하는 진입점. generator 폴더로 옮겨 `output/`을 쓰므로 클라이언트의 작업 폴더에 좌우되지 않는다 |
| `pyproject.toml` | 0.4.0, 명령 `hanok-window-llm`·`hanok-window-mcp` |

도구는 새 계산을 하지 않는다. 사전 확인은 웹의 `Service.preview`(`resolve` → `derive` → `build`)를, 생성은 `run_job`을, 조회는 패키지 색인을 그대로 쓴다. 그래서 도구로 만든 패키지는 웹·CLI와 패키지 ID가 같고, 도구를 부르는 프로세스(MCP 서버)에는 builder가 올라가지 않는다.
패키지 ID는 제출한 요청 JSON(`design_request.json`)을 포함한다. 모델은 `463.0`처럼 실수로 쓰거나 기본값을 적어 넣기 쉬우므로, 도구는 웹 폼과 같은 규칙으로 요청을 정규화한다(기본값 생략, 정수는 정수로). 잘못된 값(양문의 `hinge_side`, 모르는 필드)은 고치지 않고 `resolve`의 규칙 오류로 돌려준다.
도구 스키마에는 `oneOf`·`if/then`·`prefixItems`를 쓰지 않았다. 일부 함수 호출 API가 받지 않는 구성이며, 전체 규칙은 여전히 `resolve`가 검사한다. OpenAI 형식에는 `strict: false`를 명시했다.
오류 결과는 `rule_id`, `details`, 입력 묶음(`where`), 단계(`stage`), 영어 `hint`, 창살 개수 제안(`suggestion`)을 담는다. MCP에서는 도구 실패를 `isError: true` 결과로 돌려주어 모델이 스스로 고치게 하고, 알 수 없는 도구와 잘못된 인자 형태만 JSON-RPC 오류로 보낸다.
generator README에 LLM 연동 절(도구 표, MCP 등록, 함수 호출, 파이썬 사용)을 더했다.

| 확인 | 결과 |
|---|---|
| LLM 시험 `tests/test_llm.py` | 15개 PASS, 5.2초. 네 형식 정의(ASCII·호환 스키마), 예제 5종 정규화 불변, 실수·기본값을 섞은 요청으로 CLI와 같은 패키지 ID, 규칙 오류의 `hint`·`suggestion`, 생성 실패 보고(창살 12+4), 패키지 도구와 id 앞자리, 도면 PNG, MCP 초기화·버전 협상 3종·도구 호출·오류 코드 4종·일괄 요청, stdio로 생성하고 도면 보기, `hanok-window-llm` 종료 코드, builder 미로드 |
| 웹 시험 | 18개 PASS, 14.2초 |
| 기존 시험 | 14개 메서드 PASS, 101.3초 |
| `mcp.sh` | 편집 가능 설치를 다시 한 뒤 `initialize`에 버전 0.4.0, 프로토콜 2025-11-25로 답하고 `tools/list`가 도구 7개를 돌려준다 |
| 실제 클라이언트 | Claude·Cursor 같은 MCP 클라이언트에 등록하는 일은 사용자 환경 설정을 바꾸므로 하지 않았다. 시험은 클라이언트가 보내는 메시지를 그대로 보내 확인했다 |

## 0.4.1 추가: 고침 제안 확대와 LLM 도구 보강

2026-09-13. 0.4.0 뒤에 제시한 개선 후보 네 가지(고침 제안 확대, 패키지 파일 읽기 도구, MCP 동시 처리·진행 알림, 결과 스키마)를 사용자가 모두 골랐고, 공식 MCP SDK 클라이언트 시험과 v0.4.1 태그는 추천안대로 골랐다. 엔진은 0.2.0 그대로이고 새 의존성은 없다. 제안 계산은 `web/`에 두었으므로 패키지 ID는 바뀌지 않는다.

| 파일 | 내용 |
|---|---|
| `web/suggest.py` (새 파일) | 규칙 위반을 푸는 값을 엔진에 다시 물어 찾는다. 규칙 8종: `opening.positive_size`, `lattice.positive_gap`, `leaf.aspect_ratio`, `hardware.reference_spacing`, `picture.fits_width`·`picture.fits_height`, `nesting.part_fits_stock`, `nesting.board_width` |
| `web/service.py` | 사전 확인의 기하·배치 단계 실패에 `suggestion`을 붙인다. 내경으로 입력했으면 크기 제안도 내경으로 준다. 0.4.0의 창살 개수 제안은 `suggest.py`로 옮겼다 |
| `web/static/messages.js` | 오류 문구가 제안 값을 쓴다. 예: “외경 가로를 473 mm 이하로 줄이거나 외경 세로를 751 mm 이상으로 늘리세요.”, “원판 폭을 324 mm 이상으로 늘리거나 창살을 줄이세요.” |
| `llm/tools.py` | 여덟 번째 도구 `read_package_file`, 도구마다 결과 스키마, 규칙별 `hint`의 제안 안내, `build_package`의 단계 보고(확인 → 작업 프로세스 생성 → 결과 읽기 → 끝) |
| `llm/mcp.py` | 도구 호출을 작업 스레드 4개에서 처리하고 `notifications/progress`·`notifications/cancelled`를 지원한다. stdin이 닫히면 진행 중인 호출을 끝내 답한 뒤 종료한다 |
| `tests/interop_mcp_sdk.py` (새 파일) | 공식 MCP 파이썬 SDK 클라이언트로 `mcp.sh`를 켜서 확인하는 스크립트. SDK는 의존성이 아니므로 단위 시험에 넣지 않았다 |
| `pyproject.toml` | 0.4.1 |

제안은 규칙이 가리키는 입력 하나만 바꿔 엔진의 `derive`·`build`를 다시 돌려 찾는다. 외경 가로·세로는 정수 mm 이분 탐색으로 찾고, 그림 크기·여백과 원판 크기처럼 오류의 `details`에서 바로 나오는 값은 계산한 뒤 엔진으로 다시 확인한다. 크기를 줄이는 탐색은 앞 단계 규칙(그림, 창살)이 결과를 가리지 않도록 그림을 빼고 창살을 0으로 둔 채 하고, 찾은 값이 개구부 규칙을 어기면 버린다. 제안 값은 그 규칙만 통과시키므로 다음 규칙이 이어 나올 수 있다. 예를 들어 R3 프리셋은 외경 세로 586 mm에서 가로 463~473 mm만 A3 그림과 창짝 비율을 함께 통과한다.
결과 스키마는 성공 결과와 오류 결과(`status: FAIL`, `rule_id`, `hint`)가 모두 따라야 하므로, 두 모양에 공통인 필드만 필수로 두고 나머지 속성은 열어 두었다. 입력 스키마처럼 `oneOf`·`$ref`는 쓰지 않았고, 비어 있을 수 있는 필드는 `["string", "null"]` 같은 타입 배열로 적었다. 공식 SDK는 오류가 아닌 결과의 `structuredContent`를 이 스키마로 검증한다.
취소는 답을 보내지 않는 데까지다. 아직 시작하지 않은 호출은 실행하지 않지만, 이미 시작한 생성은 작업 프로세스에서 끝까지 진행되어 패키지를 남긴다. 패키지는 덮어쓰지 않으므로 같은 요청을 다시 보내면 그 패키지를 돌려준다.
`read_package_file`은 웹의 파일 내려받기와 같은 `Service.package_file`을 써서 매니페스트에 적힌 파일만 해시를 대조한 뒤 읽는다. 글 파일(.txt·.csv·.json·.py)만 받고 4만 자씩 나눠 준다.

| 확인 | 결과 |
|---|---|
| LLM 시험 `tests/test_llm.py` | 21개 PASS, 9.3초. 새로 넣은 시험: 제안 값으로 고친 요청이 통과, 모든 도구의 성공·오류 결과가 선언한 결과 스키마를 따름, `read_package_file` 이어 읽기(`design_spec.json`)와 오류 3종, 생성 단계 보고, MCP에서 생성 중 `ping`이 먼저 답하고 진행 알림 0→3이 결과보다 먼저 옴, 취소한 호출에 답이 없음, stdio로 CSV 읽기 |
| 웹 시험 | 20개 PASS, 14.0초. 새로 넣은 시험: 규칙 8종의 제안 값을 하나씩 적용하면 그 규칙이 풀림(내경 입력은 내경으로 제안), 화면 문구가 제안 값을 그대로 적음(node) |
| 기존 시험 | 14개 메서드 PASS, 102.7초 |
| 공식 SDK 클라이언트 | `tests/interop_mcp_sdk.py` PASS. `mcp` 2.2.0이 `mcp.sh`(0.4.1)에 프로토콜 2025-11-25로 연결했고 도구 8개가 모두 결과 스키마를 알렸다. `check_design`은 `lattice.positive_gap`과 제안(창살 27개, 외경 가로 447 mm 이상)을 돌려주었고, `build_package` 진행 알림 0·1·2·3, 도면 이미지, `read_package_file`, 성공 결과 7건의 SDK 스키마 검증이 통과했다 |

## 사용 설명서 추가 (0.4.1 이후)

2026-09-13. 설치와 사용법을 화면 그림과 함께 안내하는 설명서를 더했다. 형식(저장소 Markdown과 공유용 웹 페이지), 그림을 다시 만드는 스크립트를 저장소에 두는 것, 브랜치 → 스쿼시 병합(태그 없음)은 사용자가 추천안대로 골랐다. 생성기 코드와 패키지 ID는 바뀌지 않는다.

| 파일 | 내용 |
|---|---|
| `docs/manual/README.md` (새 파일) | 준비물, 설치, 켜고 끄기, 설계하기(입력, 단문과 경첩, 외경과 내경, 미리보기, 규칙 오류와 고치는 값, 생성, 생성 실패), 기록과 패키지 화면, 패키지 파일과 도면 다섯 장, 명령줄, LLM, 문제 해결 |
| `docs/manual/images/` (새 폴더) | 화면 13장과 R3 도면 5장, PNG 모두 3.0 MB. 화면은 밝은 테마로, 너비 1280 CSS px를 2배 해상도로 찍었다 |
| `docs/manual/make_images.py` (새 파일) | 예제 5종을 임시 폴더에 만들고, 같은 프로세스에서 띄운 웹 서버를 헤드리스 Chrome(CDP, `--remote-debugging-pipe`)으로 찍어 그림을 다시 만든다. 표준 라이브러리와 Pillow만 쓰며 실제 `output/`은 건드리지 않는다 |
| `README.md`, 저장소 `README.md` | 설명서로 가는 연결과 폴더 구성 |

그림은 화면 요소의 영역을 잘라 쓰므로 화면 구조가 바뀌면 스크립트의 선택자를 함께 고친다. 기록 화면의 출력 폴더는 임시 경로 대신 `…/hanok_window/generator/output`으로 바꿔 찍는다. 공유용 웹 페이지는 저장소 밖(claude.ai의 비공개 페이지)에 두었고 내용은 `docs/manual/README.md`와 같다.

| 확인 | 결과 |
|---|---|
| 그림 만들기 | 25초, 그림 18장. 예제 패키지 ID가 기존 기록과 같다(R3 `3d8e6187…`) |
| 그림 참조 | 설명서와 공유 페이지가 가리키는 그림 18장과 실제 파일 18장이 일치한다 |
| 문서 링크 | 다섯 문서의 상대 링크 71개와 제목 앵커가 모두 맞다 |
| 그림 확인 | 한 장씩 열어 밝은 테마, 잘린 경계, 고치는 값 문구(473·751), 실패 이유를 확인했다 |

## GitHub 공개 (0.4.1 이후)

2026-09-13. 저장소를 GitHub의 kcenon 계정에 공개(public) 저장소 https://github.com/kcenon/hanok_window 로 올렸다. 이력 정리, MIT 라이선스, 저장소 이름 `hanok_window`는 사용자가 골랐다. main과 태그 8개만 올리고 작업 브랜치는 로컬에 남겼다.

공개 전에 이력을 다시 썼다. 문서 정리(0.3.1 이후) 전의 커밋에는 로컬 계정 이름이 들어간 절대 경로가 파일 10개(`examples/built_packages.json`, `research/`의 검토 기록 등)에 남아 있었다. `git filter-branch`로 커밋 18개 전체에서 그 경로를 저장소 기준 상대 경로로 바꿨고, 다른 내용은 그대로 두었다. 그래서 모든 커밋 해시가 바뀌었다. 태그는 같은 이름으로 새 커밋을 가리키며, 첫 커밋은 `a489cad`다. 이 문서와 저장소 안내의 옛 해시 표기도 새 해시로 고쳤다.

| 태그 | 새 커밋 |
|---|---|
| `R1`, `R2`, `R3`, `v0.2.0` | `a489cad` |
| `v0.3.0` | `58bc158` |
| `v0.3.1` | `1a5a784` |
| `v0.4.0` | `d35166b` |
| `v0.4.1` | `9202934` |

| 확인 | 결과 |
|---|---|
| 이름 제거 | 모든 브랜치·태그의 커밋에서 텍스트와 이진 파일 모두 0건 |
| 현재 파일 | main의 트리 해시가 다시 쓰기 전과 같다 |
| 보존 | 커밋 18개의 작성자·날짜·메시지와 태그 8개의 메시지. `r3_reference/`(옛 `unified/`) 파일은 바뀌지 않았다 |
| 비밀값 | 모든 커밋에서 키·토큰·비밀번호 패턴 0건, 본문의 이메일 주소 0건 |

## 0.4.2 수정: package_id를 바꾸지 않는 Windows 호환

2026-09-14. 한국어 로캘(cp949) Windows에서 저장소를 받고 시험을 돌릴 수 있게 했다([#3](https://github.com/kcenon/hanok_window/issues/3)). Windows 호환을 세 단계(#3~#5)로 나눈 계획의 첫 단계로, 패키지 `source/`에 들어가는 파일(최상위 모듈·`engine/`·`presets/`·스키마)은 고치지 않았다. 그래서 이 버전의 코드 변경은 package_id를 바꾸지 않는다. 배포 버전은 `environment.json`에 들어가지 않으므로 0.4.2로 올려도 package_id는 바뀌지 않고, 엔진 `__version__`은 0.2.0 그대로다. 다만 0.4.1 뒤에 병합된 [PR #2](https://github.com/kcenon/hanok_window/pull/2)가 Pillow를 11.3.0에서 12.3.0으로 올렸다. Pillow 12.3.0은 도면 PNG를 다른 바이트로 그리고, 패키지는 설치된 라이브러리 버전을 `environment.json` 등에 적는다. 그래서 새로 설치한 환경의 package_id는 Pillow 11.3.0으로 만든 0.4.1 패키지와 다르다. 이 차이는 PR #2 병합 때 생겼고 이 버전의 코드 변경과는 무관하다.

| 파일 | 내용 |
|---|---|
| `.gitattributes` (새 파일) | 글 파일을 모든 OS에서 LF로 받는다. `r3_reference/`는 `-text`로 두어 CRLF로 커밋된 R3 CSV 4개까지 바이트 그대로 받는다. 이 파일이 없으면 Git for Windows 기본값(`core.autocrlf=true`)이 LF 파일을 CRLF로 받아, R3 원본 SHA-256 대조와 소스 해시 대조가 실패했다 |
| `tests/test_web.py` | fcntl을 쓰는 `web.control`은 POSIX에서만 불러온다. 그전에는 Windows에서 웹 시험이 import 단계에서 멈춰 하나도 돌지 않았다. 하위 프로세스 출력 6곳을 UTF-8로 읽는다 |
| `tests/test_llm.py` | 하위 프로세스 출력 3곳을 UTF-8로 읽는다 |
| `tests/test_generator.py` | 하위 프로세스 출력 3곳, 파일 읽기 9곳, 파일 쓰기 2곳에 UTF-8을 지정한다. 스크립트로 실행할 때 쓰는 `results.json`은 UTF-8·LF 바이트로 쓴다 |
| `llm/__main__.py` | `hanok-window-llm`의 표준 입력·출력·오류를 UTF-8로 바꾼다. 그전에는 파이프로 받은 JSON이 cp949로 나왔다 |
| `llm/tools.py` | 모델에게 주는 문구 두 곳(`build_package` 설명, `describe_generator`의 workflow). package_id는 같은 실행 환경에서만 같고, 같은 설계인지는 `check_design`·`get_package`의 `revision`으로 비교하라고 적었다 |
| `web/server.py` | 서버를 열 때 `127.0.0.1`의 역방향 이름 조회(`socket.getfqdn`)를 하지 않는다. `http.server`가 `server_name`을 채우려고 하는 조회인데 이 저장소는 그 값을 쓰지 않는다. GitHub macOS 러너(macos-26)에서 setup-python이 설치한 Python 3.11은 이 조회에 프로세스마다 30초 넘게 걸려, 서버가 `web.sh start`의 20초 제한 안에 응답하지 못했다 |
| `.github/workflows/tests.yml` (새 파일) | pull request와 main push에서 ubuntu·macOS로 세 시험을 돌리고, 시험 뒤 추적 파일이 바뀌지 않았는지 `git diff --exit-code`로 확인한다. 가상환경을 `generator/.venv`에 만들어 `web.sh` 시험도 돈다 |
| `README.md`, 저장소 `README.md`, `docs/manual/README.md` | Windows 설치·웹 화면·MCP 등록·시험 안내, package_id가 같은 범위 |
| `requirements.lock` | Pillow를 `pyproject.toml`과 같은 12.3.0으로 맞췄다. PR #2가 `pyproject.toml`만 올려 둘이 어긋났고, `uv pip install -r requirements.lock -e .`가 해를 찾지 못했다. 이 파일은 패키지에 들어가지 않으므로 package_id와 무관하다. 이 파일 첫 줄과 `README.md`·`docs/manual/README.md`에 적힌 검증 환경(macOS arm64만 적혀 있었다)은 Pillow 12.3.0으로 실제로 시험한 Windows 11과 CI의 ubuntu·macOS로 고쳤다 |
| `pyproject.toml` | 0.4.2 |

엔진이 인코딩을 지정하지 않고 파일을 읽고 쓰는 곳(`model.py` 등)은 고치면 모든 package_id가 한 번 바뀌므로 [#4](https://github.com/kcenon/hanok_window/issues/4)(엔진 0.3.0)로 넘겼다. 그때까지 Windows에서는 `PYTHONUTF8=1`이 필요하고, 엔진이 README를 CRLF로 쓰므로 `test_llm.py`의 `test_read_package_file_in_pages` 1개가 실패한다. Windows CI도 #4에서 켠다.
package_id는 도면 PNG(글꼴)와 `environment.json`(OS, Python과 라이브러리 버전, 소스 해시)을 담으므로 실행 환경이 같을 때만 같다. OS와 무관하게 같은 설계인지는 `revision`으로 본다. 이 뜻으로 이슈 #3의 할 일 목록에 없던 곳도 고쳤다: `build_package` 설명의 “The same request always yields the same package_id”, 설명서 준비물 표의 컴퓨터 줄(macOS만 적혀 있었다), 설명서 패키지 생성 절의 “같은 입력은 언제나 같은 패키지 ID”.

| 확인 | 결과 |
|---|---|
| package_id 경계 | main과 다른 파일에 `package.source_files()`가 모으는 파일이 없다 |
| 줄 끝 | `.gitattributes`를 넣고 다시 받은 뒤 `git status`가 깨끗하고, `git add --renormalize .`가 아무것도 올리지 않으며, 작업 트리가 CRLF인 파일은 R3 CSV 4개뿐이다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8=1`. 새로 받은 사본에 `README.md`의 Windows 절차대로 설치했다(`py -3.11`이 없어 가상환경만 `uv venv --python 3.11`로 만들었다). 생성기 14개 PASS(191.7초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.6초), LLM 21개 중 20개 PASS·1개 실패(`test_read_package_file_in_pages`, 14.3초). 시험 뒤 추적 파일은 바뀌지 않았다 |
| ubuntu·macOS CI | PR #6의 GitHub Actions에서 ubuntu 24.04(CPython 3.11.16)와 macOS 26 arm64(CPython 3.11.9) 모두 생성기 14개, 웹 20개, LLM 21개가 건너뜀 없이 통과했고, 시험 뒤 추적 파일이 바뀌지 않았다. 첫 실행에서 macOS의 서버 시험 3개가 실패한 이유는 위 `web/server.py` 행에 적었다 |
| package_id 불변 | 같은 PC, 같은 가상환경(Pillow 12.3.0)에서 main(LF로 받은 worktree)과 이 버전의 소스로 `examples/double_r3.json`을 만들면 package_id가 둘 다 `48d2e12d…`다. 같은 PC에서 Pillow 11.3.0으로 만들면 `669c09fb…`였고, macOS 예제의 `3d8e6187…`과 다른 것은 실행 환경이 달라서다 |
| macOS 예제 5종 | 이 PC에서는 만들 수 없어 직접 확인하지 않았다. 경계 안의 파일을 고치지 않았고 웹 시험이 소스 해시 16개가 `tests/results.json`과 같음을 확인하므로, 기록 당시와 같은 환경(Pillow 11.3.0)이면 이 버전의 수정으로는 바뀌지 않는다. Pillow 12.3.0으로 새로 설치한 환경에서는 PR #2 때문에 다르다 |

## 0.5.0 수정·추가: 엔진 파일 입출력을 UTF-8·LF로 고정, builder 정리, latest.json 교체 재시도, 참고 도면 위치, 4×8 원판 프리셋, PNG 홈 색, 부재별 Z 층, 액자형 화판과 뒤틀, 액자형 웹·LLM·설명서, DWG 내려받기, AI 파일 저장 (엔진 0.3.0)

2026-09-14. 엔진이 로캘 인코딩과 OS 줄 끝으로 파일을 읽고 쓰던 곳을 고쳐, 한국어 로캘(cp949) Windows에서도 `PYTHONUTF8` 없이 시험과 생성이 돈다([#4](https://github.com/kcenon/hanok_window/issues/4)). Windows 호환 세 단계(#3~#5) 중 둘째 단계이고, 셋째 단계인 builder 정리([#5](https://github.com/kcenon/hanok_window/issues/5))도 태그 전에 이 버전에 넣었다(절 끝의 「builder 정리 (#5)」). Windows에서 동시에 끝난 빌드가 `latest.json`을 바꾸지 못하던 결함([#9](https://github.com/kcenon/hanok_window/issues/9))도 고쳤다(절 끝의 「latest.json 교체 재시도 (#9)」). 원판이 1220 mm보다 길면 참고 도면이 원판 위에 그려지던 결함([#11](https://github.com/kcenon/hanok_window/issues/11))도 고쳤다(절 끝의 「참고 도면 위치 (#11)」). 4×8 원판을 기본으로 쓰는 프리셋 `standard_4x8_v1`을 더하고, 원판 안에 그리던 가공 메모와 결 방향 화살표를 원판 아래로 옮겼다([#13](https://github.com/kcenon/hanok_window/issues/13), 절 끝의 「4×8 원판 프리셋 (#13)」). 원판 두께가 20 mm가 아니면 01 원판 배치 PNG와 05 전체 홈 확대 PNG에 홈 색이 칠해지지 않던 결함([#12](https://github.com/kcenon/hanok_window/issues/12))도 고쳤다(절 끝의 「PNG 홈 색 (#12)」). 부재마다 조립 Z 위치를 두어, 입체 겹침 검사가 두께 방향으로 떨어진 부재를 겹침으로 세지 않게 했다([#14](https://github.com/kcenon/hanok_window/issues/14), 절 끝의 「부재별 Z 층 (#14)」). 창호를 그림 액자로 쓰는 액자형을 더했다. 화판 크기로 창을 지정하고, 고정틀 뒤 한 층에 같은 원판에서 깎은 뒤틀 4개를 두어 화판을 잡는다([#15](https://github.com/kcenon/hanok_window/issues/15), 절 끝의 「액자형 화판과 뒤틀 (#15)」). 웹 화면과 LLM 도구, 설명서도 액자형 입력을 받는다([#16](https://github.com/kcenon/hanok_window/issues/16), 절 끝의 「액자형 웹·LLM·설명서 (#16)」). 패키지 화면에서 도면을 DWG로도 받게 했다([#17](https://github.com/kcenon/hanok_window/issues/17), 절 끝의 「DWG 내려받기 (#17)」). 도면을 Illustrator 8 형식 AI 파일로도 저장해 패키지에 넣었다([#18](https://github.com/kcenon/hanok_window/issues/18), 절 끝의 「AI 파일 저장 (#18)」). 엔진 `__version__`은 0.3.0, 배포 버전은 0.5.0이다.
패키지 `source/`에 들어가는 파일 7개(`__init__.py`, `cli.py`, `engine/builder.py`, `jobs.py`, `model.py`, `package.py`, `worker.py`)가 바뀌고 `resolved_parameters.json`의 engine이 0.3.0이 되었으므로 모든 입력의 package_id가 바뀐다. 기하와 도면을 만드는 계산은 바꾸지 않았다. 그래서 같은 입력의 revision은 그대로이고, macOS·Linux에서 만든 DXF는 0.4.2와 바이트까지 같다(POSIX에서는 텍스트 모드도 줄 끝을 바꾸지 않는다). 다만 원판 길이가 1220 mm가 아닌 입력은 #11 수정으로 참고 도면이 옮겨져 DXF가 다르다. 또 #13 수정으로 가공 메모와 결 방향 화살표가 원판 아래로 옮겨져, 모든 입력의 DXF와 01 원판 배치 PNG가 0.4.2와 다르다. 원판 두께가 20 mm가 아닌 입력은 #12 수정으로 05 전체 홈 확대 PNG도 0.4.2와 다르다. Windows에서 만든 DXF, JSON, README는 줄 끝이 CRLF에서 LF로 바뀌어 macOS에서 만든 것과 같아졌다. Linux의 DXF는 이 변경과 무관하게 참고 그림의 점 하나가 마지막 자리에서 다르다(아래 확인 표의 OS 간 비교 행). #15로 저장 DXF 검사가 68개에서 70개가 되어 모든 입력의 `validation_report.json`과 `README.txt`도 0.4.2와 다르다. `window.dxf`, `design_spec.json`, PNG, CSV는 #15 수정으로 바뀌지 않는다. #18로 `engine/ai_export.py`가 생겨 `source/`에도 실리고 `window.ai`가 패키지에 들어가므로 패키지 파일이 34개에서 36개가 되고, 검사가 70개에서 71개가 되어 모든 설계의 `validation_report.json`과 `README.txt`가 다시 달라진다. 이로써 모든 입력의 package_id가 한 번 더 바뀐다.
0.4.1 패키지와 비교하면 package_id는 두 번 바뀐 셈이다. 이슈의 계획은 한 번이었지만, 0.4.2 절에 적은 대로 PR #2(Pillow 12.3.0)로 새로 설치한 환경의 package_id가 이미 한 번 바뀌었다.

| 파일 | 내용 |
|---|---|
| `model.py` | 프리셋 `presets/r3_parameters.json`을 UTF-8로 읽는다. 그전에는 한국어 Windows에서 cp949로 읽다가 멈췄다 |
| `cli.py` | 스키마를 UTF-8로 읽고 표준 출력·오류를 UTF-8로 바꾼다. 그전에는 `hanok-window schema`가 스키마를 cp949로 읽다가 종료 코드 2로 끝났고, 파이프로 받은 오류 JSON이 cp949였다. 출력을 `io.StringIO`로 받는 시험(`tests/test_web.py:160`)이 있어 `reconfigure`가 있는 스트림만 바꾼다 |
| `jobs.py` | 작업 프로세스를 `PYTHONIOENCODING=utf-8`로 띄우고, 그 출력과 `result.json`을 UTF-8로 읽는다 |
| `worker.py` | 작업 요청 파일을 UTF-8로 읽는다 |
| `package.py` | 검증 기록과 매니페스트를 UTF-8로 읽고, JSON과 `source/requirements.txt`를 UTF-8·LF 바이트로 쓴다. Python 3.11의 `Path.write_text()`에는 `newline` 인자가 없어, 텍스트로 쓰면 Windows에서 줄 끝이 CRLF가 된다 |
| `engine/builder.py` | `design_spec.json`, `validation_report.json`, `README.txt`를 UTF-8·LF 바이트로 쓴다. DXF는 ezdxf `saveas()` 대신 `newline='\n'`으로 연 파일에 `doc.write()`로 쓴다. ezdxf 1.4.2의 `saveas()`도 같은 인코딩과 오류 처리(`dxfreplace`)로 파일을 텍스트로 열어 `write()`를 부르므로 줄 끝만 달라지고, POSIX에서는 바이트가 같다 |
| `__init__.py`, `pyproject.toml` | 엔진 0.3.0, 배포 0.5.0 |
| `tests/test_encoding.py` (새 파일) | `hanok_generator/`와 `tests/`의 파이썬 파일을 구문 트리로 읽어, 인코딩을 적지 않은 `read_text()`·`write_text()`, 텍스트 모드 `open()`, `text=True` 하위 프로세스를 찾는다. GitHub Windows 러너는 한국어 로캘이 아니어서 CI만으로는 cp949 문제가 드러나지 않으므로 코드 모양으로 검사한다 |
| `tests/results.json` | 소스 해시 7개와 경우별 package_id 17개. 시험이 예제를 병렬로 만들고 끝난 순서대로 적으므로 경우의 순서도 바뀌었다 |
| `examples/built_packages.json`, `examples/README.md` | 예제 5종의 새 package_id. 이 PC(Windows 11 AMD64, CPython 3.11.15, Pillow 12.3.0)에서 만든 값이다 |
| `.github/workflows/tests.yml` | Windows를 매트릭스에 넣어 세 OS에서 돌린다. Windows 러너의 기본 셸이 PowerShell이라 bash로 두고, 가상환경 Python 경로를 `VENV_PYTHON`으로 나눴다. 인코딩 시험 단계와, R3를 만들어 매니페스트를 출력하는 `R3 package manifest` 단계를 더했다 |
| `tests/test_generator.py` | 소수 외곽 시험은 일반·최적화 하위 프로세스 두 개를 동시에 돌린다. 이제 두 프로세스가 마감 시각 하나(시작 뒤 900초)를 함께 쓴다. 그전에는 프로세스마다 300초였고, 첫 Windows CI에서 이 한도를 넘겨 실패했다. 이 시험은 이 PC에서 157초가 걸려 생성기 시험 시간의 약 83%를 차지하므로, 같은 비율이면 ubuntu CI(전체 356초)에서도 약 300초로 한도에 가까웠다 |
| `README.md`, 저장소 `README.md` | Windows 절에서 `PYTHONUTF8` 안내(명령 전 설정, MCP 등록, 시험)를 지웠다. 검증·시험 절과 폴더 구성에 인코딩 시험을 더하고, 버전 표기와 예시 package_id를 고쳤다 |

이슈 #4의 할 일 목록에 없던 변경은 README의 Windows·검증 절, 저장소 README의 버전·시험 절, CI의 `test_encoding.py` 단계와 `R3 package manifest` 단계, 소수 외곽 시험의 시간 한도다. CI는 시험 파일 이름 셋을 하나씩 돌리므로 새 시험은 단계를 더해야 돈다. 매니페스트 단계는 이슈의 완료 기준 「같은 요청이면 OS가 달라도 DXF, CSV, JSON, README가 바이트까지 같다」를 보려고 더했다. 엔진 0.2.0으로 만든 macOS 예제와 비교하면 엔진 버전, Pillow, 고친 소스도 함께 달라서 OS 차이만 따로 볼 수 없다.
0.4.2 절의 `PYTHONUTF8` 안내는 그때의 기록이므로 고치지 않았다.

| 확인 | 결과 |
|---|---|
| 인코딩 시험 | 엔진을 고치기 전(main `b47c9b6`)에는 8곳을 찾아 실패했다: `cli.py:78`, `jobs.py:41`·`45`, `model.py:92`, `package.py:73`·`86`·`103`, `worker.py:67`. 고친 뒤에는 통과한다. `web/`, `llm/`, `tests/`에는 걸리는 곳이 없다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음(`sys.flags.utf8_mode` 0, 로캘 인코딩 cp949). 인코딩 1개 PASS(0.2초), 생성기 14개 PASS(187.7초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.5초), LLM 21개 PASS(18.1초). 0.4.2에서 실패하던 `test_read_package_file_in_pages`도 통과한다. 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`의 소스 해시를 다시 적었다 |
| R3 | 이 PC에서 만든 R3 패키지(`fb3e99cd…`)의 revision은 `HANOK_GEN_V1_04a2ec4c4f06`이고 `window.dxf` SHA-256은 `f13d4aef…`다. `docs/example-packages` 브랜치의 macOS 예제(엔진 0.2.0, CPython 3.11.15, Pillow 11.3.0)와 파일별로 비교하면 35개 중 18개가 같다: `README.txt`, `design_parameters.json`, `design_request.json`, `design_spec.json`, CSV 4개, `window.dxf`, 바뀌지 않은 소스 9개. 다른 17개는 PNG 5장, `environment.json`, `validation_report.json`, `resolved_parameters.json`(engine), `source/requirements.txt`(Pillow), 고친 소스 7개, `package_manifest.json`이다. 이슈 본문의 「21개가 같다」보다 적은 것은 엔진 버전(`__init__.py`, `resolved_parameters.json`)과 Pillow(`source/requirements.txt`)가 달라서다. CRLF가 있는 파일은 CSV 4개뿐이다. csv 모듈의 기본 줄 끝이며 macOS 예제도 같다 |
| 파이프 | CLI를 `PYTHONUTF8`·`PYTHONIOENCODING` 없이 하위 프로세스로 불러 출력을 바이트로 받았다. 고치기 전에는 `schema`가 종료 코드 2로 끝났고 `resolve --type single --size 463x586 --lattice 2x4`의 오류 출력이 UTF-8이 아니었다. 고친 뒤에는 `schema`가 종료 코드 0과 UTF-8 3,324바이트를 내고, 같은 오류 출력(193바이트)도 UTF-8이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사·부품·홈·도그본 수는 그대로다 |
| CI | PR #7의 커밋 `08892eb`에서 세 OS 모두 네 시험이 통과했고, 시험 뒤 추적 파일이 바뀌지 않았다. ubuntu 24.04(CPython 3.11.16)는 생성기 14개(202.4초)·웹 20개(21.8초)·LLM 21개(14.1초), macOS 26 arm64(CPython 3.11.9)는 생성기 14개(162.3초)·웹 20개(19.6초)·LLM 21개(11.6초), Windows Server 2025(CPython 3.11.9)는 생성기 14개(415.4초)·웹 20개 중 15개와 5개 건너뜀(31.5초)·LLM 21개(26.1초)다. 첫 실행에서는 Windows의 소수 외곽 시험이 300초 한도를 넘겨 실패했다(위 `tests/test_generator.py` 행) |
| OS 간 비교 | 세 job이 같은 코드로 만든 R3에서 매니페스트에 적힌 파일 34개 중 26개가 세 OS에서 같다. PNG 5장, `environment.json`, `validation_report.json`은 OS마다 다르다. `window.dxf`는 macOS, Windows CI, 이 PC가 `f13d4aef…`로 같고 ubuntu만 `4ca19e06…`이다. Linux 컨테이너(Debian glibc 2.41, CPython 3.11.15)에서 만든 DXF도 `4ca19e06…`이었고, 이 PC의 DXF와 값별로 비교하면 28,085줄 가운데 두 값만 다르다. 둘 다 `ASSEMBLY_REFERENCE` 층 열림 방향 호(`engine/builder.py:317`)의 같은 점의 y좌표이고, 차이는 2.8e-14 mm(마지막 한 비트)다. `math.sin`의 결과가 45°와 120°에서 glibc와 Windows 사이에 마지막 비트가 달라서 생긴다. 참고 그림이라 가공 윤곽, CSV, `design_spec.json`은 세 OS가 같다. 계산을 바꾸지 않았고 POSIX에서는 쓰는 바이트도 같으므로 이 버전의 변경과 무관하며, 고치려면 엔진 계산을 바꿔야 해서 이 버전에서는 고치지 않았다. 그래서 이슈의 완료 기준 「OS가 달라도 DXF가 바이트까지 같다」는 macOS와 Windows에서만 맞는다 |

### builder 정리 (#5)

2026-09-14. `engine/builder.py`가 모듈 전역 변수에 두던 설계 값을 설정 객체 하나로 옮기고, 331줄이던 `validate()`를 검사 구역 일곱 개로 나눴다([#5](https://github.com/kcenon/hanok_window/issues/5)). 기하 계산, 검사 ID, 검사 수(67개), 검사 순서는 바꾸지 않았다.
패키지 `source/`에 들어가는 `engine/builder.py`와 `worker.py`가 바뀌므로, 모든 입력의 package_id가 main `1548662`의 0.5.0보다 한 번 더 바뀐다. 같은 PC에서 만든 패키지는 `environment.json`, `package_manifest.json`, 이 두 소스 파일 말고는 바이트까지 같다. `v0.5.0` 태그와 릴리스가 아직 없어 버전은 올리지 않았다. 이슈 #5가 「다른 엔진 변경이 생길 때 같은 릴리스에 넣는다」고 정했고, 그 엔진 변경(#4)의 릴리스가 0.5.0이다.

| 파일 | 내용 |
|---|---|
| `engine/builder.py` | `configure()`가 `global` 문 하나로 정하던 이름 가운데 입력과 무관한 셋(`TOL`, `ASSEMBLY_ORIGIN`, `OPENING_ORIGIN`)은 모듈 상수가 되고, 나머지 56개는 같은 이름으로 frozen dataclass `Design`의 필드가 된다. `configure()`는 같은 식을 같은 순서로 계산해 `Design`을 돌려주고, 다른 함수 24개는 이를 첫 인자 `cfg`로 받는다. 식은 이름 앞에 `cfg.`를 붙인 것 말고는 그대로다. `build()`가 전역 `MSP`에 두던 모델 공간은 `add_details(cfg,msp)`에 인자로 넘긴다. `global` 문에 있던 `i`는 어느 함수도 읽지 않아 버렸다 |
| `engine/builder.py`의 `validate()` | 검사 기록 함수(`check_recorder`)와 기대값(`check_expectations`)을 따로 두고, 구역 함수 일곱 개를 차례로 부른다. 구역 함수의 몸은 원래 줄을 바이트까지 그대로 옮겼고, 구역 사이에 넘기는 값만 인자와 반환값으로 새로 적었다. `validate()`는 38줄이 되었다 |
| `worker.py` | `configure()`가 돌려준 `cfg`를 `build`, `render_*`, `write_readme`에 넘긴다. CSV 단계 장애 주입은 `builder.write_manifests`를 바꿔 끼우는 방식 그대로이고, `build()`가 이 함수를 모듈 이름으로 부르므로 계속 동작한다 |
| `tests/test_generator.py` | 저장 DXF에 없는 상세와 틀린 경첩을 넣는 시험, 소수 외곽 시험의 하위 프로세스 코드가 `configure()`의 반환값을 `validate()`와 `build()`에 넘긴다 |
| `web/service.py`, `tests/test_web.py` | 「builder가 모듈 상태를 가진다」던 주석을 고쳤다. builder는 여전히 작업 프로세스(해시 시드 0, 시간 제한)에서만 돈다. 두 파일은 package_id 경계 밖이다 |
| `tests/results.json` | 소스 해시 2개(`engine/builder.py`, `worker.py`)와 경우별 package_id 17개. 경우의 순서도 몇 곳 바뀌었다 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 LLM 호출 예의 R3 ID |

| 구역 | 함수 | 검사 번호 |
|---|---|---|
| 부품과 원판 배치 | `check_parts_and_board` | 1~17 |
| 홈과 도그본 | `check_pockets_and_dogbones` | 18~35 |
| 도면 층·단위·부품 표기 | `check_layers_units_and_labels` | 36~38 |
| 결합 쌍과 3차원 겹침 | `check_joint_pairs_and_solids` | 39~43 |
| 조립 치수와 간격 | `check_assembly_dimensions` | 44~51 |
| 참고 도면(조립·그림·열림·하드웨어·상세) | `check_references` | 52~63 |
| 메타데이터 | `check_metadata` | 64~67 |

검증 기록은 검사를 부른 순서대로 적으므로, 순서가 이어지는 곳에서만 끊었다. 그래서 이슈가 예로 든 여섯 구역 사이에 도면 층·단위·부품 표기(36~38번)가 따로 생겼고, 홈 검사인 63번 `pockets_open_edge_intent`는 참고 구역 끝에 남았다. 조립 참고도가 부품과 맞는지 보는 52번은 참고 구역 첫머리에 두어, 조립 치수 구역에서 다음 구역으로 넘길 값이 없게 했다.
이슈 #5의 할 일 목록에 없던 변경은 주석 두 곳(`web/service.py`, `tests/test_web.py`)과 시험의 호출 모양이다.

| 확인 | 결과 |
|---|---|
| 전역 변수 | builder.py의 함수가 읽는데 import만으로는 정의되지 않는 전역을 `symtable`로 셌다. 바꾸기 전에는 `global` 문 61개, 그런 이름 60개(`configure()`가 정하는 59개와 `MSP`)였고, 바꾼 뒤에는 둘 다 0개다 |
| 같은 PC 비교 | 요청 14개(예제 5종, 단문 왼쪽 경첩 2x4, 창살 2x0·0x4·3x5, 그림 297x420, 소수 외곽 463.7x586.3, 원판 두께 24 mm, 소수 내경 단문 340.3x820.7, 검증에서 떨어지는 12x4)를 main `1548662`와 두 코드 커밋 뒤에 각각 만들어 파일별 SHA-256으로 비교했다. 두 커밋 뒤 모두 PASS 13개는 파일 35개 중 `environment.json`, `package_manifest.json`, `source/hanok_generator/engine/builder.py`, `source/hanok_generator/worker.py`만 다르고, 12x4는 실패 기록(검사 67개)이 같다. `validation_report.json`이 바이트까지 같으므로 검사 ID·수·순서가 같다. 이슈의 완료 기준(예제 5종의 `window.dxf`, CSV 4종, `design_spec.json`, `checks` 목록)도 이 비교에 들어 있다. 비교 방법은 main 사본의 두 소스 끝에 주석 한 줄씩만 더해 만든 결과로 먼저 확인했고, 그때도 같은 네 파일만 달랐다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.2초), 생성기 14개 PASS(184.4초, 바꾸기 전 main에서는 187.4초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.4초), LLM 21개 PASS(14.2초). 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`의 소스 해시를 다시 적었고, 시험 뒤 바뀐 추적 파일은 그 파일뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사·부품·홈·도그본 수는 그대로다. R3는 `6692c318…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`과 `window.dxf` SHA-256 `f13d4aef…`는 그대로다 |
| CI | PR #8의 커밋 `6e7a100`에서 세 OS 모두 네 시험이 통과했고, 시험 뒤 추적 파일이 바뀌지 않았다. ubuntu 24.04(CPython 3.11.16)는 생성기 14개(257.1초)·웹 20개(25.4초)·LLM 21개(17.2초), macOS 26 arm64(CPython 3.11.9)는 생성기 14개(253.2초)·웹 20개(24.7초)·LLM 21개(16.5초), Windows Server 2025(CPython 3.11.9)는 생성기 14개(284.8초)·웹 20개 중 15개와 5개 건너뜀(25.0초)·LLM 21개(19.4초)다 |
| OS별 비교 | OS마다 이 PR의 R3 매니페스트(파일 34개)를 main run `34813027155`의 것과 비교했다. 세 OS 모두 `environment.json`, `source/hanok_generator/engine/builder.py`, `source/hanok_generator/worker.py`만 다르고, PNG 5장, `window.dxf`, CSV 4종, `validation_report.json`을 포함한 31개는 같다. `window.dxf`는 ubuntu `4ca19e06…`, macOS와 Windows `f13d4aef…`로 main과 같다. 같은 코드로 돈 두 run(PR #7과 main)은 세 OS 모두 34개가 같았으므로, 세 OS 모두에서 생성 결과가 바뀌지 않았다. 세 OS끼리는 위 OS 간 비교 행과 같이 34개 중 26개가 같다 |

### latest.json 교체 재시도 (#9)

2026-09-14. Windows에서 두 빌드가 거의 같이 끝나거나, 교체하는 순간 다른 쪽이 `latest.json`을 읽고 있으면 `run_job()`의 `latest.json` 교체가 `PermissionError [WinError 5]`로 실패해 그 빌드가 `job.failed`로 끝났다([#9](https://github.com/kcenon/hanok_window/issues/9)). 패키지는 교체 전에 `packages/`로 옮겨져 남았지만 `latest.json`은 바뀌지 않았다. Windows의 `os.replace`는 대상 파일을 다른 핸들이 열고 있으면 실패하고, 웹 화면의 빌드 대기열은 작업자 2개로 빌드를 동시에 돌린다. PR #8의 CI에서 Windows 웹 시험 하나가 이 오류로 실패해 찾았다. 교체가 이 오류로 막히면 짧게 기다렸다가 다시 시도하게 고쳤다.
`jobs.py`는 패키지 `source/`에 들어가므로 모든 입력의 package_id가 builder 정리 뒤보다 한 번 더 바뀐다. 같은 PC에서 만든 패키지는 `environment.json`, `package_manifest.json`, `source/hanok_generator/jobs.py` 말고는 바이트까지 같다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `jobs.py` | `replace_pointer()`가 `os.replace()`를 부르고, `PermissionError`가 나면 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1초를 차례로 기다렸다가 다시 시도한다(합계 1.88초). 그래도 실패하면 마지막 시도의 오류를 그대로 올린다. POSIX의 `rename`은 대상이 열려 있어도 실패하지 않으므로 macOS와 Linux에서는 첫 시도에 끝난다 |
| `tests/test_generator.py` | `test_latest_pointer_waits_for_an_open_handle`: 대상 파일을 연 채로 교체를 시작하고 0.1초 뒤에 닫아, 교체가 새 내용으로 끝나는지 본다 |
| `tests/results.json` | 시험 수(14개에서 15개), 소스 해시 1개(`jobs.py`), 경우별 package_id 17개 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 LLM 호출 예의 R3 ID |

| 확인 | 결과 |
|---|---|
| 재현 | Windows 11에서 두 스레드가 같은 파일을 3초 동안 번갈아 교체했다. 고치기 전(`Path.replace`)에는 9,374번 중 926번, 파일을 읽는 스레드를 하나 더하면 6,795번 중 6,202번이 `WinError 5`로 실패했다. 고친 뒤에는 9,492번 중 0번, 97번 중 0번이다. 읽는 스레드가 쉬지 않고 파일을 여는 조건이라 기다리는 시간이 길어져 교체 횟수가 줄었다 |
| 새 시험 | 같은 절차를 `Path.replace`로 하면 이 PC에서 `PermissionError [WinError 5]`가 나고, `replace_pointer()`로 하면 새 내용으로 바뀐다 |
| 같은 PC 비교 | 요청 14개를 builder 정리 뒤(PR #8 헤드)와 이 수정 뒤에 만들어 파일별 SHA-256으로 비교했다. PASS 13개는 `environment.json`, `package_manifest.json`, `source/hanok_generator/jobs.py`만 다르고, 12x4는 실패 기록(검사 67개)이 같다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.2초), 생성기 15개 PASS(새 시험 포함, 193.5초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.3초), LLM 21개 PASS(14.4초). 시험 뒤 바뀐 추적 파일은 고친 두 파일과 `tests/results.json`뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사·부품·홈·도그본 수는 그대로다. R3는 `01a8fcb5…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`과 `window.dxf` SHA-256 `f13d4aef…`는 그대로다 |
| CI | PR #10의 CI(run `34834745553`)에서 세 OS 모두 네 시험이 통과했고, 시험 뒤 추적 파일이 바뀌지 않았다. ubuntu 24.04(CPython 3.11.16)는 생성기 15개(338.7초)·웹 20개(31.4초)·LLM 21개(22.7초), macOS 26 arm64(CPython 3.11.9)는 생성기 15개(230.3초)·웹 20개(25.3초)·LLM 21개(15.5초), Windows Server 2025(CPython 3.11.9)는 생성기 15개(411.1초)·웹 20개 중 15개와 5개 건너뜀(31.3초)·LLM 21개(27.7초)다 |
| OS별 비교 | OS마다 R3 매니페스트(파일 34개)를 builder 정리의 CI(PR #8, run `34830043427`)와 비교했다. 세 OS 모두 `environment.json`과 `source/hanok_generator/jobs.py`만 다르고, PNG 5장, `window.dxf`, CSV 4종, `validation_report.json`을 포함한 32개는 같다 |

### 참고 도면 위치 (#11)

2026-09-15. 원판(`stock_mm`) 길이가 1220 mm보다 길면 조립도·상세도·열림도가 원판 위에 그려져 부품과 겹쳤다([#11](https://github.com/kcenon/hanok_window/issues/11)). 두 참고 도면의 원점이 1220 mm 원판에 맞춘 고정값 (1350, 100)과 (1350, -370)이었고, 상세도는 조립도 원점 오른쪽에 놓이기 때문이다. 참고 도형을 보는 검사 `references_never_on_machining_layers`는 도형이 가공 레이어에 있는지만 봐서 이를 잡지 못했다. 참고 레이어를 끄지 않고 원판 전체를 CAM에 넣으면 창 정면도가 부재 위에 같이 들어간다. 이제 원점 x는 원판 길이 + 130 mm이고, 참고 도형이 원판과 만나면 새 검사 `references_outside_board`가 실패한다. 설계당 검사는 68개가 된다.
`engine/builder.py`는 패키지 `source/`에 들어가므로 모든 입력의 package_id가 #9 수정 뒤보다 한 번 더 바뀐다. 원판 길이 1220 mm인 입력은 원점이 1350 그대로여서 `window.dxf`, PNG 5장, CSV 4종, `design_spec.json`이 바이트까지 같고, 검사가 하나 늘어 `validation_report.json`과 `README.txt`(검사 수)가 달라진다. 원판이 1220 mm보다 짧으면 참고 도면이 왼쪽으로 옮겨져 DXF가 달라진다(예제와 시험에는 없다). 참고 도면의 가장 왼쪽(조립도 왼쪽 치수선)은 원판 길이와 상관없이 원판 오른쪽 끝에서 70 mm 떨어진다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `engine/builder.py` | 모듈 상수 `ASSEMBLY_ORIGIN`, `OPENING_ORIGIN`을 지우고 `REFERENCE_GAP_X`(130), `ASSEMBLY_Y`(100), `OPENING_Y`(-370)를 두었다. `configure()`가 두 원점을 (원판 길이 + 130, y)로 계산해 `Design` 필드로 넘기고, 원점을 읽는 7곳(`add_hardware`, `add_assembly`, `add_opening`, `add_details`, `check_references`, `render_assembly`, `render_opening`)이 `cfg.`로 읽는다. 두 원점은 builder 정리(#5)에서 입력과 무관한 모듈 상수로 남겼던 것이다. 새 검사 `references_outside_board`는 `view`가 조립·상세·열림이거나 `detail` 키가 있는 도형(상세도 치수는 `detail` 키만 있다)이 원판 영역과 만나는지 본다. 선은 선분, 폴리라인은 다각형, 글자는 기준점으로 잰다. 글자가 뻗는 길이는 글꼴에 따라 달라서다. 측정값에는 참고 도형 수와 원판과 만난 수, 정수 두 개만 적는다. 좌표 같은 소수는 OS마다 마지막 자리가 다를 수 있어 적지 않았다. 이름에 `board`가 있어 대상은 `stock_mm`이고, 웹 화면에서는 원판 묶음(3개에서 4개)에 나온다 |
| `llm/tools.py` | 모델에게 주는 문구 세 곳의 검사 수를 68로 고쳤다 |
| `tests/test_generator.py` | 생성 요청에 R3 + 원판 2400×1200×20과 900×1200 양문 창살 2+6 + 같은 원판을 더했다(경우 17개에서 19개). 기존 시험이 두 설계의 부품 수, 검사 ID 목록, 상세도도 본다. 새 시험 `test_reference_views_stay_off_a_longer_board`는 두 패키지의 참고 도형을 엔진 도우미 대신 ezdxf가 계산한 도형별 외곽 상자로 재어, 원판과 만나는 도형이 없고 새 검사가 PASS인지 본다. 이어서 원점을 옛 값(x 1350)으로 되돌린 설정으로 두 설계를 빌드해, 저장 전 검사에서 `references_outside_board` 하나만 실패하고 폴더에 파일이 남지 않는지 본다. 소수 외곽 시험의 검사 수도 68로 고쳤다 |
| `tests/test_web.py`, `tests/test_llm.py` | 검사 수를 68로 고쳤다 |
| `tests/results.json` | 시험 수(15개에서 16개), 소스 해시 1개(`engine/builder.py`), 경우별 package_id 19개 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 검사 수, LLM 호출 예의 R3 ID, `build_package` 설명의 검사 수 |
| `docs/manual/README.md` | 검사 수 네 곳(패키지 생성 절, 패키지 화면의 배지와 검사 설명, 패키지 파일 표) |

| 구역 | 함수 | 검사 번호 |
|---|---|---|
| 참고 도면(조립·그림·열림·하드웨어·상세·원판 밖 위치) | `check_references` | 52~64 |
| 메타데이터 | `check_metadata` | 65~68 |

새 검사는 `references_never_on_machining_layers`(61번) 바로 뒤의 62번이다. 기존 검사에 조건을 합치면 이름과 뜻이 어긋나서 따로 두었다. 그 뒤의 `opening_illustration_matches_leaves`는 63번, `pockets_open_edge_intent`는 64번, 메타데이터 구역은 65~68번이 되고, 1~61번은 그대로다.
설명서 스크린샷 세 장(`images/package.png`의 배지와 검사 표, `images/build-failed.png`, `images/package-checks.png`)에는 67이 그대로 찍혀 있다. 그림과 그림 설명(alt)은 고치지 않았다. 이 그림들은 엔진 0.2.0 때 찍은 것이어서 엔진 버전과 패키지 ID도 지금과 다르다.
이슈 #11의 할 일 목록에 없던 변경은 0.5.0 절 머리의 두 문장(#11 소개, 원판 길이가 1220 mm가 아닌 입력은 DXF가 다르다는 단서)이다.
참고 도면끼리 겹치는 곳은 고치지 않았다. 창짝이 넓은 900×1200 양문은 열림도 윗부분(y 최대 135.5)이 조립도 아래쪽(y 26부터)과 겹쳐, 열림도 도형 4개(제목과 부제 글자, 열린 창짝 그림 2개)가 조립도 도형 3개(고정틀 부재 F01-1·F02-1 윤곽, 치수선 1개)와 만난다. 두 원점이 같은 x로 함께 옮겨지므로 main에서도 같고 이 수정과 무관하다.

| 확인 | 결과 |
|---|---|
| 같은 PC 비교 | 요청 8개(예제 5종, R3 + 원판 2400×1200×20, 900×1200 양문 2+6 + 같은 원판, `single_empty` + 원판 1000×900×20)를 main `2220587`과 이 수정 뒤에 각각 `run_job`(작업 프로세스 해시 시드 0)으로 만들어 파일별 SHA-256으로 비교했다. main은 `git archive`로 푼 사본을 `PYTHONPATH`로 불러 같은 가상환경에서 만들었다. 원판 1220 mm인 예제 5종은 파일 35개 중 `validation_report.json`, `README.txt`, `environment.json`, `package_manifest.json`, `source/hanok_generator/engine/builder.py`만 다르고, `window.dxf`, PNG 5장, CSV 4종, `design_spec.json`은 같다. 원판을 바꾼 세 요청은 여기에 `window.dxf`가 더해지고 PNG 5장은 같다(참고 도면 PNG는 원점 기준 상대 좌표로 그린다). 검사는 main에서 67개, 이 수정 뒤 68개가 모두 통과했다 |
| 참고 도형 위치 | main에서 R3 + 2400 원판은 참고 도형 498개 중 421개(조립도 143개 전부, 상세도 293개 중 278개), 900×1200 + 2400 원판은 495개 중 99개(조립도 95개, 열림도 4개)가 원판과 만나는데도 검사 67개를 모두 통과했다. 이 수정 뒤에는 둘 다 0개이고, 조립도 원점 x는 2530, 참고 도형의 가장 왼쪽은 x 2470이다. 1000 mm 원판은 원점 x 1130, 가장 왼쪽 x 1070이고, 1220 mm 원판은 1350과 1290 그대로다. 새 검사와 같은 규칙으로 센 수와 ezdxf 외곽 상자로 센 수가 모든 요청에서 같았다 |
| 옛 원점 | 원점을 x 1350으로 되돌린 설정으로 두 2400 원판 설계를 빌드하면 저장 전 검사(`IN_MEMORY_BEFORE_SAVE`)에서 `references_outside_board` 하나만 실패하고, 빌드 폴더에 파일이 남지 않는다(새 시험) |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.2초), 생성기 16개 PASS(새 시험 포함, 201초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.8초), LLM 21개 PASS(14.2초). 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`을 다시 적었고, 시험 뒤 바뀐 추적 파일은 고친 파일과 그 파일뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사는 68개, 부품·홈·도그본 수는 그대로다. R3는 `b9a13d66…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`과 `window.dxf` SHA-256 `f13d4aef…`는 그대로다 |

### 4×8 원판 프리셋 (#13)

2026-09-15. 4×8 원판(2400 × 1200 mm)으로 가공하도록 원판 기본값, 원판 가장자리 여유, 부재 간격을 프리셋이 정하게 했다([#13](https://github.com/kcenon/hanok_window/issues/13)). 그전에는 원판 기본값 1220 × 900 × 20 mm, 여유 20 mm, 간격 12 mm가 모든 입력에 하나였고 여유와 간격을 바꿀 길이 없었다. 새 프리셋 `standard_4x8_v1`은 `standard_v1`과 규칙이 같고 기본 원판 2400 × 1200 × 20 mm, 여유 10 mm, 간격 12 mm를 쓴다. 원판 크기, 간격 고정, 새 프리셋으로 둘지는 사용자가 이슈의 권장안대로 골랐다. 여유와 간격은 요청 항목으로 열지 않았다. 부재 간격이 공구 지름보다 작으면 한 부재를 도는 공구가 옆 부재를 깎으므로, 이를 거부하는 규칙 `nesting.part_gap_tool`을 더했다.
원판 안에 그리던 가공 메모 다섯 줄, 결 방향 화살표와 글자, 남는 판 문구, 부품 길이 줄은 배치 위쪽의 빈 띠에 놓였다. 배치가 원판 위쪽까지 차면 이 글자가 부품과 겹쳤는데도 검사 68개가 모두 통과했다(아래 확인 표의 원판 안 도형 행). 그래서 모든 프리셋에서 이 주석 11개를 원판 아래로 옮기고, 원판 안에는 부재 윤곽, 홈, 도그본, 부품 번호, 하드웨어 참고 표시만 둔다.
`model.py`, `request.schema.json`, `engine/builder.py`, `engine/generate_spec.py`는 패키지 `source/`에 들어가므로 모든 입력의 package_id가 #11 수정 뒤보다 한 번 더 바뀐다. 기존 두 프리셋은 정규화 요청과 revision이 그대로이고 `window.dxf`와 01 원판 배치 PNG가 달라진다. PNG 02~05, CSV 4종, `design_spec.json`, `design_parameters.json`, `resolved_parameters.json`, `README.txt`는 바이트까지 같다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `model.py` | 프리셋 `standard_4x8_v1`, 요청이 원판을 주지 않을 때의 `DEFAULT_STOCK_MM`(1220, 900, 20), 프리셋별 기본 원판·`edge_margin`·`part_gap`을 적은 `PRESET_STOCK`. `stock_mm`을 생략하면 프리셋의 기본 원판을 채우고, 여유와 간격은 `presets/r3_parameters.json`의 값을 프리셋 값으로 덮는다. 정규화 요청의 모양은 그대로여서, 새 프리셋에서 원판을 생략한 요청과 `[2400, 1200, 20]`을 적은 요청은 revision이 같다(package_id는 `design_request.json`이 달라 다르다) |
| `request.schema.json` | `preset` 목록과 단문이 받는 프리셋에 새 프리셋, `stock_mm`에 프리셋별 기본값 설명 |
| `engine/generate_spec.py` | `derive()`의 규칙 `nesting.part_gap_tool`(부재 간격 ≥ 공구 지름). 프리셋 값(간격 12 mm, 공구 6 mm)으로는 어떤 요청도 이 규칙에 걸리지 않으므로 웹 오류 문구와 LLM 안내는 더하지 않았다. 저장 DXF에서 잰 간격은 이미 `minimum_nesting_gap`이 프리셋 간격과 비교하므로 검사는 68개 그대로다 |
| `engine/builder.py` | `add_board()`가 메모 여섯 줄을 y −60부터 20 mm 간격으로, 결 방향 글자·화살표·부품 길이 줄을 그 아래(y −195, −235, −275)에 그리고 `kind='sheet_note'`를 단다. 원판 가운데에 높이 13으로 쓰던 「UNUSED OFFCUT / NOT ADDITIONAL PARTS」는 원판 밖에서는 가리키는 곳이 없어 메모 여섯째 줄 「BOARD AREA WITHOUT PARTS: UNUSED OFFCUT / NOT ADDITIONAL PARTS」로 바꿨다. 「No G-code…」 줄은 제자리(y −35)다. DXF를 열 때의 기본 보기는 원판 아래 300 mm부터 위 85 mm까지로 넓혔다. `nest_entities()`는 `sheet_note`를 01 원판 배치 PNG에서 뺀다. 렌더러가 그림 범위 밖을 자르지 않아 그대로 두면 아래쪽 확대 영역 위에 그려지고, 같은 내용이 PNG의 제목 줄과 오른쪽 설명에 이미 있다 |
| `web/service.py` | meta의 프리셋마다 `stock_mm`, `edge_margin_mm`, `part_gap_mm`. 값은 모델에 물어 얻는다 |
| `web/static/app.js` | 요청을 폼에 불러올 때와 폼에서 요청을 만들 때 고른 프리셋의 기본 원판을 쓴다. 원판을 고치지 않은 채 프리셋을 바꾸면 원판이 새 프리셋의 기본값으로 바뀌고, 고친 원판은 그대로 둔다(`stockAfterPresetChange`) |
| `web/static/messages.js` | 프리셋 안내에 규칙 이름과 기본 원판·여유·간격 |
| `llm/tools.py` | `preset`과 `stock_mm` 설명에 새 프리셋과 프리셋별 기본 원판, `describe_generator`의 프리셋에 `default_stock_mm`·`edge_margin_mm`·`part_gap_mm`. 모델이 보낸 요청은 그 요청 프리셋의 기본 원판과 같을 때만 `stock_mm`을 뺀다. 웹 폼과 같은 요청이 되어 package_id가 같다 |
| `tests/test_generator.py` | 생성 요청에 새 프리셋의 463×586 양문 2+4와 900×1200 양문 2+6을 더했다(경우 19개에서 21개). 새 시험 `test_standard_4x8_preset_lays_out_a_4x8_board`는 두 패키지의 요청·원판·여유·간격과 검사 기대값, revision, 간격 규칙(5 mm 거부, 6 mm 통과), 원판 한 장의 한계(부재 길이 2380 mm 통과, 2381 mm는 `nesting.part_fits_stock`)를 본다. 잰 간격은 좌표 뺄셈 때문에 11.999999999999998처럼 나오므로 허용 오차 1e-7 mm로 비교한다. 새 시험 `test_board_holds_only_machining_and_labels`는 모든 패키지에서 원판 안과 만나는 도형이 허용 목록뿐인지, `sheet_note` 11개가 원판 아래와 참고 도면 왼쪽에 있는지 본다. 글자는 ezdxf 외곽 상자로 재어 폭까지 넣는다 |
| `tests/test_web.py` | meta의 프리셋별 원판·여유·간격, 새 프리셋 미리보기, 2381 mm 부재의 규칙 오류와 고침 제안(원판 길이 2401 mm 이상, 외경 세로 2380 mm 이하). 고침 제안 시험은 원판이 없는 요청의 원판을 요청 프리셋의 기본값으로 채운다. 폼 요청 구성(node)에 새 프리셋 요청 두 개와 프리셋을 바꿀 때 원판이 따라가는지를 더했다 |
| `tests/test_llm.py` | 새 프리셋의 기본 원판을 적은 요청에서 `stock_mm`이 빠지고 다른 조합은 남는지, `describe_generator`의 프리셋별 기본 원판 |
| `tests/results.json` | 시험 수(16개에서 18개), 소스 해시 4개, 경우별 package_id 21개 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 LLM 호출 예의 R3 ID. README는 입력 표, 프리셋 절, 형식과 상세도 절 |
| `docs/manual/README.md` | 입력 표의 프리셋·원판 행, 01 원판 배치 설명 |

이슈 #13의 할 일 목록에 없던 변경은 DXF 기본 보기, 01 원판 배치 PNG에서 뺀 주석, 남는 판 문구를 메모 줄로 바꾼 것, 0.5.0 절 머리의 두 문장(#13 소개, 모든 입력의 DXF와 01 원판 배치 PNG가 다르다는 단서)이다.
설명서 그림 `images/drawing-nesting.png`는 다시 만들지 않아 메모와 결 방향 화살표가 원판 안에 있는 옛 모습이다. 참고 도면끼리 겹치는 곳(#11 절 끝)은 이 수정과 무관해 그대로다.

| 확인 | 결과 |
|---|---|
| 같은 PC 비교 | 요청 8개(예제 5종, R3 + 원판 2400×1200×20, 900×1200 양문 2+6 + 같은 원판, 1100×800 양문 7+8)를 main `a399e4a`와 이 수정 뒤에 각각 CLI(작업 프로세스 해시 시드 0)로 만들어 파일별 SHA-256으로 비교했다. main은 `git archive`로 푼 사본을 `PYTHONPATH`로 불렀고, 그 사본으로 만든 예제 5종의 package_id는 `examples/built_packages.json`의 옛 값과 같았다. 8개 모두 파일 35개 중 `window.dxf`, `01_one_board_nesting.png`, `validation_report.json`(DXF 해시), `environment.json`, `package_manifest.json`, 고친 소스 4개가 다르고, PNG 02~05, CSV 4종, `design_spec.json`, `design_parameters.json`, `resolved_parameters.json`, `design_request.json`, `README.txt`를 포함한 26개는 같다. revision이 같고, 검사는 양쪽 모두 68개가 통과했다 |
| 원판 안 도형 | 원판을 1e-7 mm 줄인 사각형과 만나는 도형 가운데 허용 목록(원판 경계, 부재 윤곽, 홈, 도그본, 부품 번호, 원판 배치의 하드웨어 참고 표시) 밖의 것을 셌다. 글자는 ezdxf 외곽 상자로 쟀다. main은 8개 설계 모두 11개(`GRAIN_DIRECTION` 4개, `NOTES` 7개)이고, 배치 윗변이 798 mm인 1100×800 양문 7+8은 메모 두 줄(「HINGE_REF / LATCH_REF ARE POSITION REFERENCES ONLY. DO NOT MACHINE.」, 「NOMINAL FIT: …」)이 부품과 만나는데도 검사 68개를 모두 통과했다. 이 수정 뒤에는 새 프리셋 설계를 포함한 모든 설계가 0개다. 옮긴 주석 11개는 x 0~1079.7(1220 원판) 또는 0~2124(2400 원판), y −281.2~−56.7에 있어, 원판 끝에서 70 mm 떨어져 시작하는 참고 도면과 만나지 않는다 |
| 새 프리셋 | 463×586 양문 2+4(원판 생략, `[2400, 1200, 20]` 명시), 900×1200 양문 2+6, 단문 왼쪽 경첩 420×900 2+6, 2000×2380 양문 4+10, 463×586 + 원판 1220×900×20을 만들었다. 모두 검사 68개가 통과했고, 잰 여유는 10.0 mm, 간격은 12.0 mm 또는 11.999999999999998 mm다. 원판을 생략한 요청과 적은 요청은 revision `HANOK_GEN_V1_2aa6c8f0a9d6`과 `window.dxf`(`49d94c8b…`)가 같고 package_id만 다르다. 같은 원판을 `standard_v1`로 주면 revision이 다르다(`HANOK_GEN_V1_d22029d3ff61`). 2000×2380 4+10은 부품 40개가 x 10~2390, y 10~854에 놓이고, 2000×2381은 `nesting.part_fits_stock`(쓸 수 있는 원판 2380 × 1180)으로 거부된다. 1220 원판에 쓰면 배치는 x 10~1194, y 10~294다 |
| 간격 규칙 | 새 프리셋의 매개변수에서 부재 간격만 5 mm, 5.999 mm로 바꾸면 `derive()`가 `nesting.part_gap_tool`로 거부하고, 6 mm와 12 mm는 통과한다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.2초), 생성기 18개 PASS(새 시험 포함, 203.3초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.9초), LLM 21개 PASS(14.3초). 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`을 다시 적었고, 시험 뒤 바뀐 추적 파일은 고친 파일과 그 파일뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사는 68개, 부품·홈·도그본 수는 그대로다. R3는 `ab5a7bcd…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`은 그대로이며 `window.dxf` SHA-256은 `f13d4aef…`에서 `25ccf2f3…`로 바뀌었다 |

### PNG 홈 색 (#12)

2026-09-15. 원판(`stock_mm`) 두께가 20 mm가 아니면 01 원판 배치 PNG와 05 전체 홈 확대 PNG에서 홈이 홈 색으로 칠해지지 않았다([#12](https://github.com/kcenon/hanok_window/issues/12)). PNG를 그리는 `Renderer.entity()`는 원판 배치의 홈을 레이어 이름 `POCKET_10MM`으로 알아봤는데, 홈 레이어 이름은 홈 깊이(원판 두께의 절반)로 만든다. 18 mm 원판은 `POCKET_9MM`, 21 mm는 `POCKET_10.5MM`, 24 mm는 `POCKET_12MM`이다. 이 줄은 원판 두께가 20 mm로 정해져 있던 R3 원본(`r3_reference/02_cnc/cad_helpers.py:149`)에서 가져온 것이고, 생성기는 두께 5~60 mm를 받는다(`model.py:98`). 그래서 두께가 20 mm가 아니면 PNG 01에는 오른쪽 범례의 홈 색 칸만 남고 PNG 05에는 홈 색이 없었다. DXF와 검사는 설계의 홈 레이어 이름을 써서 영향이 없었고, 02 상세도 PNG는 홈을 `role` 메타데이터로 칠해서 영향이 없었다. 이제 원판 배치의 홈도 메타데이터로 알아본다.
`engine/cad_helpers.py`는 패키지 `source/`에 들어가므로 모든 입력의 package_id가 #13 수정 뒤보다 한 번 더 바뀐다. 두께 20 mm 입력은 `environment.json`, `package_manifest.json`, `source/hanok_generator/engine/cad_helpers.py` 말고는 바이트까지 같다. 20 mm가 아닌 입력은 여기에 01 원판 배치 PNG와 05 전체 홈 확대 PNG가 더해진다. `window.dxf`, 검사, CSV 4종, `design_spec.json`, revision은 어느 입력도 바뀌지 않는다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `engine/cad_helpers.py` | `Renderer.entity()`가 레이어 이름 대신 도형 메타데이터로 홈을 알아본다. 원판 배치의 홈은 `kind`가 `pocket`이고, 상세도의 홈은 전과 같이 `role`이 `pocket`이다. PNG는 저장한 DXF를 다시 읽어 그리는데, 메타데이터(XDATA)는 저장 뒤에도 남는다. 두께 20 mm 설계는 `POCKET_10MM` 레이어의 도형이 곧 `kind`가 `pocket`인 도형이어서 PNG가 바이트까지 같다(아래 확인 표의 홈 레이어 행). 설계의 홈 레이어 이름(`Design.POCKET_LAYER`)을 렌더러에 넘기는 안은 렌더러를 만드는 6곳을 모두 고쳐야 하고, 이름이 `POCKET_`로 시작하는지 보는 안은 레이어 이름 약속에 계속 기대므로 쓰지 않았다 |
| `tests/test_generator.py` | 생성 요청에 463×586 양문 2+4를 원판 1220×900×18과 1220×900×24로 만든 두 설계를 더했다(경우 21개에서 23개). 기존 시험이 두 설계의 부품·홈·도그본 수, 검사 ID 목록, 상세도, 원판 안 도형도 본다. 새 시험 `test_pockets_keep_their_colour_on_any_board_thickness`는 두 패키지의 DXF에 `POCKET_9MM`, `POCKET_12MM` 레이어가 있는지, PNG 01·05의 홈 색 픽셀 수가 같은 창의 20 mm 설계와 같은지 본다. 원판 배치는 부재 길이·폭, 여유, 간격만 쓰고 두께는 쓰지 않으므로, 두께만 다른 설계는 픽셀 수가 정확히 같다. 그래서 이슈 완료 기준의 「같은 규모」보다 강하게 같은 수로 비교한다. 두 설계를 같은 시험 실행에서 같은 글꼴로 그리므로 OS가 달라도 성립한다 |
| `tests/results.json` | 시험 수(18개에서 19개), 소스 해시 1개(`engine/cad_helpers.py`), 경우별 package_id 23개 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 LLM 호출 예의 R3 ID |

이슈 #12의 할 일 목록에 없던 변경은 0.5.0 절 머리의 두 문장(#12 소개, 원판 두께가 20 mm가 아닌 입력은 05 전체 홈 확대 PNG도 다르다는 단서)이다.
렌더러의 다른 레이어 판정(`CUT_THROUGH`, `DOGBONE`, `HINGE_REF`, `LATCH_REF`)은 두께와 무관한 고정 이름이라 그대로 두었다. `r3_reference/02_cnc/cad_helpers.py`의 같은 줄은 R3 원본 기록이고 시험이 이 파일의 SHA-256을 보므로 고치지 않았다. 설명서 그림 `images/drawing-nesting.png`와 `images/drawing-pockets.png`는 20 mm 원판이라 홈이 칠해져 있어 이 수정과 무관하다.

| 확인 | 결과 |
|---|---|
| 같은 PC 비교 | 요청 12개(예제 5종, 463×586 양문 2+4 + 원판 `[1220, 900, t]`(t = 20, 18, 21, 24), R3 + `[1220, 900, 18]`, `standard_4x8_v1` + `[2400, 1200, 18]`, 단문 왼쪽 경첩 420×900 2+6 + `[1220, 900, 24]`)를 main `943778a`와 이 수정 뒤에 각각 CLI(작업 프로세스 해시 시드 0)로 만들어 파일별 SHA-256으로 비교했다. main은 `git archive`로 푼 사본을 `PYTHONPATH`로 불렀고, 그 사본으로 만든 예제 5종의 package_id는 `examples/built_packages.json`의 옛 값과 같았다. `python -m`은 현재 폴더를 모듈 검색 경로 맨 앞에 넣으므로 두 엔진 모두 `hanok_generator`가 없는 폴더에서 돌리고, 불러온 모듈 위치를 확인했다. 두께 20 mm인 6개는 파일 35개 중 `environment.json`, `package_manifest.json`, `source/hanok_generator/engine/cad_helpers.py`만 다르고, 나머지 6개는 여기에 `01_one_board_nesting.png`와 `05_all_pockets_closeup.png`가 더해진다. `window.dxf`, PNG 02~04, CSV 4종, `design_spec.json`, `validation_report.json`, `README.txt`는 12개 모두 같고, revision이 같으며, 검사는 양쪽 모두 68개가 통과했다 |
| 홈 색 픽셀 | PNG 01·02·05의 홈 색(`#F3BF68`) 픽셀을 이 PC에서 셌다. main에서 20 mm가 아닌 6개는 01이 1,369(오른쪽 범례의 홈 색 칸, 37×37 픽셀), 05가 0이다. 이 수정 뒤 463×586 양문 2+4는 두께 18·21·24 mm와 R3 + 18 mm가 모두 01 615,830, 05 458,409로 20 mm 설계와 같다. `standard_4x8_v1` + 18 mm는 139,513과 97,809, 단문 420×900 2+6 + 24 mm는 403,868과 295,256이다. 두께 20 mm인 6개는 main과 이 수정 뒤의 수가 같다. PNG 02는 main에서도 모든 설계의 홈이 칠해진다 |
| 홈 레이어 | 이 수정 뒤 12개 설계의 `window.dxf`에서 홈 레이어의 도형은 모두 `kind`가 `pocket`인 폴리라인이고(설계의 홈 수와 같은 104개, 72개, 16개), `kind`가 `pocket`인 도형은 모두 홈 레이어에 있다 |
| 새 시험 | 고치기 전 엔진(main 사본)으로 이 브랜치의 시험 파일을 돌리면 새 시험이 18 mm와 24 mm 모두 `{'01_one_board_nesting.png': 1369, '05_all_pockets_closeup.png': 0} != {'01_one_board_nesting.png': 615830, '05_all_pockets_closeup.png': 458409}`로 실패하고, 이 수정 뒤에는 통과한다. 함께 돌린 `test_all_types_zero_counts_and_real_details`와 `test_board_holds_only_machining_and_labels`는 양쪽 모두 통과한다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.1초), 생성기 19개 PASS(새 시험 포함, 204.6초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.8초), LLM 21개 PASS(14.7초). 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`을 다시 적었고, 시험 뒤 바뀐 추적 파일은 고친 파일과 그 파일뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사는 68개, 부품·홈·도그본 수는 그대로다. R3는 `dc8b4509…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`과 `window.dxf` SHA-256 `25ccf2f3…`는 그대로다 |

### 부재별 Z 층 (#14)

2026-09-15. 부재마다 조립했을 때의 Z 위치를 설계 사양에 두고, 입체 겹침 검사 `no_nominal_assembled_solid_interpenetration`이 그 Z를 더해 부피를 재게 했다([#14](https://github.com/kcenon/hanok_window/issues/14)). 이 검사는 부재마다 홈이 없는 부분을 0~두께, 홈 부분을 앞면·뒷면에 따라 절반 구간으로 두고 부재끼리 부피가 겹치는지 본다. 그런데 모든 부재가 이 한 구간에 있다고 봐서, 액자형([#15](https://github.com/kcenon/hanok_window/issues/15))의 뒤틀처럼 고정틀 뒤에 겹쳐 놓는 부재는 두께 방향으로 떨어져 있어도 정면에서 고정틀과 겹치는 부분이 겹침으로 잡혀 이 검사가 바로 실패한다. Z는 조립했을 때 부재 뒷면의 위치(mm)이고, +Z는 보는 쪽(앞)이다. 지금 창의 부재는 모두 0~두께의 한 층(Z 0)에 있고, 한 층 뒤에 놓는 부재는 −두께가 된다. 층 번호(정수)로 두는 안은 모든 층을 한 두께에 묶고 검사가 어차피 mm로 바꿔 써야 해서 쓰지 않았다.
`engine/generate_spec.py`와 `engine/builder.py`는 패키지 `source/`에 들어가므로 모든 입력의 package_id가 #12 수정 뒤보다 한 번 더 바뀐다. 지금 설계는 모두 한 층이라, 같은 PC에서 만든 패키지는 `environment.json`, `package_manifest.json`, 고친 소스 2개 말고는 바이트까지 같다(`window.dxf`, `design_spec.json`, `validation_report.json`, PNG, CSV 포함). revision도 그대로다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `engine/generate_spec.py` | `Part.assembly_z`(기본 0). `build()`는 Z가 0이 아닌 부재만 `design_spec.json`의 부품 기록에 `assembly_z`를 적는다. 모든 부재에 `assembly_z: 0.0`을 적으면 모든 사양이 바뀌고, R3의 `design_spec.json`을 `tests/fixtures/r3_reference.json`과 통째로 비교하는 `test_r3_production_geometry_and_originals`의 기록도 고쳐야 한다. `build_joints()`는 같은 조립 무리이면서 같은 층인 부재끼리만 반턱을 만든다. 층이 다른 부재는 두께 방향으로만 만나므로 반턱이 되지 않는다 |
| `engine/builder.py` | `Design.PART_Z`(부재 번호별 Z). `configure()`가 매개변수로 만든 부재 목록(`build_parts()`)에서 채운다. 입체 겹침 검사는 부재마다 Z 구간에 그 부재의 Z를 더한다. 반턱 짝 검사 `joint_pairs_XY_match_opposite_faces`에는 짝을 이루는 두 부재가 한 층에 있어야 한다는 조건을 더했다. 검사가 두께와 홈 깊이를 DXF가 아니라 매개변수(`cfg.THK`, `cfg.DEPTH`)에서 읽듯이 Z도 `cfg.PART_Z`에서 읽는다. 모든 부재의 XDATA에 Z를 넣으면 모든 DXF가 바뀌고, 같은 R3 시험이 부재·홈·도그본 도형의 XDATA까지 기록과 비교하므로 시험도 실패한다. 새 검사를 만들지 않아 검사는 68개 그대로이고, 입체 겹침 검사의 `method` 문구도 고치지 않았다(문구가 `validation_report.json`에 들어간다). Z가 0이면 `0.0 + z0`이 `z0`과 비트까지 같아 지금 설계의 보고 값은 바뀌지 않는다 |
| `tests/test_generator.py` | 새 시험 `test_members_on_another_layer_may_overlap_in_the_front_view`. 이미 만드는 463×586 양문 2+4 패키지의 저장 DXF로 `validate()`를 부르고 실패한 검사 이름을 본다. F01-2(오른쪽 세로 고정틀)만 한 층 뒤로 보내면 반턱 짝 검사 하나만 실패한다. F01-2의 조립 변환을 F01-1의 것으로 바꿔 정면에서 겹치면 한 층 뒤에서는 입체 겹침 검사가 통과하고 같은 층에서는 실패한다. 조립 변환을 바꾸면 `frame_geometry` 등 다른 검사도 실패하므로, 이 두 경우는 입체 겹침 검사가 실패 목록에 있는지만 본다. F02-1(아래 가로 고정틀)을 다른 층에 두면 `build_joints()`가 만드는 반턱이 2개 줄어드는지도 본다. 생성 요청은 늘지 않았다(경우 23개 그대로) |
| `tests/results.json` | 시험 수(19개에서 20개), 소스 해시 2개(`engine/builder.py`, `engine/generate_spec.py`), 경우별 package_id 23개 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 LLM 호출 예의 R3 ID |

이슈 #14의 할 일 목록에 없던 변경은 0.5.0 절 머리의 한 문장(#14 소개)과 `build_joints()`의 층 조건이다. `build_joints()`는 검사가 아니라 사양을 만드는 쪽이지만 반턱 짝 검사와 같은 전제(한 무리의 부재는 한 층에서 반턱으로 만난다)를 쓴다.
층과 무관하거나 #15가 새 부재를 넣을 때 정할 판정은 그대로 두었다. `half_lap_depth`와 `derive()`의 반턱 깊이는 홈 깊이의 두 배가 원판 두께인지 본다. 모든 층을 한 원판에서 깎으므로 층과 무관하다. `layer_depth_and_face_separation`과 `machining_checks.measure_machining()`은 부재 하나의 두께 안에서만 잰다. `frame_geometry`, `leaf_envelopes`, `leaf_clearances`, `no_member_bridges_leaves`, 창살 간격, `assembly_reference_matches_all_cut_parts`는 정면(XY)에서 잰다. `parts_manifest.csv`의 `thickness_mm`는 원판 두께다. 02 상세도, 03 조립도, 04 열림도는 모든 부재를 한 층에 그린다. 숨은선과 층 단면, CSV의 Z 열, 작업자에게 층을 보여 주는 XDATA는 #15에서 정한다.

| 확인 | 결과 |
|---|---|
| 같은 PC 비교 | 요청 12개(예제 5종, 463×586 양문 2+4, 같은 창 + 원판 `[1220, 900, 18]`, 창살 0×0, 창살 3×5, 600×800 + 그림 297×420(여백 10), `standard_4x8_v1`, 단문 왼쪽 경첩 420×900 2+6)를 main `917dd36`과 이 수정 뒤에 각각 CLI(작업 프로세스 해시 시드 0)로 만들어 파일별 SHA-256으로 비교했다. main은 `git archive`로 푼 사본을 `PYTHONPATH`로 불렀고, 그 사본으로 만든 예제 5종의 package_id는 `examples/built_packages.json`의 옛 값과 같았다. 두 엔진 모두 `hanok_generator`가 없는 폴더에서 돌리고 불러온 모듈 위치를 확인했다. 12개 모두 파일 35개 중 `environment.json`, `package_manifest.json`, `source/hanok_generator/engine/builder.py`, `source/hanok_generator/engine/generate_spec.py`만 다르고, `window.dxf`, `design_spec.json`, `validation_report.json`, PNG 5장, CSV 4종, `README.txt`를 포함한 31개는 같다. revision이 같고, 검사는 양쪽 모두 68개가 통과했다 |
| 층 배치 | 위 463×586 양문 2+4 패키지의 저장 DXF로 `validate()`를 불렀다. 그대로 두면 main과 이 수정 모두 68개가 통과하고, 입체 겹침 최댓값은 5.7e-12 mm³(`L01-2/L02-1`)로 같다. F01-2만 한 층 뒤(−20 mm)로 보내면 `joint_pairs_XY_match_opposite_faces` 하나만 실패한다. F01-2의 조립 변환을 F01-1의 것으로 바꿔 정면에서 겹치면, 같은 층에서는 main과 같이 입체 겹침 404,800 mm³(`F01-1/F01-2`)로 실패하고 한 층 뒤에서는 입체 겹침이 통과한다. 이때 조립 변환을 바꾼 탓에 반턱 짝, `frame_geometry`, `assembly_reference_matches_all_cut_parts`, 하드웨어 검사 2개는 실패한다. 반 층 뒤(−10 mm)면 10 mm만 겹쳐 202,400 mm³로 실패한다. 404,800 mm³는 F01 부재에서 양 끝 반턱을 뺀 면적 20,240 mm²에 두께 20 mm를 곱한 값이다 |
| R3 기록 비교 | `test_r3_production_geometry_and_originals`는 R3의 `design_spec.json`과 부재·홈·도그본 도형의 XDATA를 `tests/fixtures/r3_reference.json`과 비교하고 R3 원본 파일의 SHA-256을 본다. 기록을 고치지 않고 통과한다 |
| 새 시험 | main 사본의 엔진으로 이 브랜치의 새 시험을 돌리면 `Design`에 `PART_Z`가 없어 `AttributeError`로 끝나고(설계 23개를 만드는 시간을 포함해 13.7초), 이 수정 뒤에는 통과한다. 결함을 고치는 일이 아니라 기능을 더하는 일이라, 고치기 전 동작은 위 층 배치 행의 main 값으로 대신한다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.1초), 생성기 20개 PASS(새 시험 포함, 198.1초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 14.4초), LLM 21개 PASS(14.4초). 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`을 다시 적었고, 시험 뒤 바뀐 추적 파일은 고친 파일과 그 파일뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사는 68개, 부품·홈·도그본 수는 그대로다. R3는 `204e70b0…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`과 `window.dxf` SHA-256 `25ccf2f3…`는 그대로다 |

### 액자형 화판과 뒤틀 (#15)

2026-09-16. 창호를 그림 액자로 쓰는 형식(액자형)을 엔진에 넣었다([#15](https://github.com/kcenon/hanok_window/issues/15)). 그전에는 그림이 창짝 개구부 안에 들어가야 했고 별도 후판에 붙이는 참고선일 뿐이어서, 틀이 화판을 감싸는 액자가 되지 않았다. 고정틀과 창짝이 같은 한 층이라 화판이 들어갈 깊이도 없었다. 이제 고정틀이 화판 가장자리를 덮고, 같은 원판에서 깎은 뒤틀 4개가 고정틀 뒤 한 층(#14의 `assembly_z`, −원판 두께)에서 화판을 잡는다. 크기 기준에 `artwork`를 더해 화판 크기로 창을 지정하며, 외경 = 화판 − 2 × 덮는 폭 + 2 × 고정틀 폭이다. 창살과 화판 사이는 따로 사는 스페이서로 띄우고, 뒤틀 모서리는 맞댄 이음이라 정면에서 겹치는 넓이가 없어 반턱이 생기지 않는다. 화판 두께 3 mm, 덮는 폭 8 mm, 끼움 여유 1 mm, 스페이서 3 mm가 기본값이다. 스페이서·뒷판·걸이 철물과 맞댄 이음의 접착·고정 방법은 PENDING이다.
패키지 `source/`에 들어가는 파일 6개가 바뀌므로 모든 입력의 package_id가 #14 수정 뒤보다 한 번 더 바뀐다. 검사가 68개에서 70개가 되어 모든 설계의 `README.txt`와 `validation_report.json`도 달라진다. `window.dxf`, `design_spec.json`, `design_parameters.json`, PNG 5장, CSV 4종은 같은 PC에서 바이트까지 같고 revision도 그대로다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `model.py` | 요청의 `artwork`(화판 크기와 두께·덮는 폭·끼움 여유·스페이서)를 외경·내경에 이은 셋째 크기 기준으로 받는다. `outer_mm`·`inner_mm`·`picture`와 함께 쓸 수 없고(`input.size_basis`, `input.artwork_picture`), R3 프리셋과도 함께 쓸 수 없다(`input.preset_artwork`). R3는 A3 그림을 후면 지지판에 두는 규칙이라 전제가 반대다. `artwork` 매개변수와 부재 종류 `B01`·`B02`, 네스팅 계열 `BACK_FRAME`은 액자형 요청에만 넣는다. 그래서 지금까지 만든 설계의 `design_parameters.json`이 그대로다 |
| `request.schema.json` | `artwork` 객체와 그 범위. `oneOf`에 크기 기준으로 더하고, 액자형일 때 프리셋과 `picture`를 제한한다 |
| `engine/generate_spec.py` | 뒤틀 폭 = 고정틀 폭 − (덮는 폭 + 끼움 여유). 부재 목록 맨 끝에 `B01-1`·`B01-2`(세로), `B02-1`·`B02-2`(가로)를 Z −두께로 더하므로 창 부재의 원판 배치는 액자형이 아닌 같은 창과 같다. 규칙 4개를 더했다. `artwork.covers_inner`는 화판이 내경을 덮는지, `artwork.cover_hides_edge`는 덮는 폭이 끼움 여유보다 큰지(화판이 여유만큼 밀려도 가장자리가 보이지 않아야 한다), `artwork.back_member_width`는 남는 뒤틀 폭이 창살 폭 이상인지, `artwork.depth_within_stock`은 스페이서와 화판 두께의 합이 원판 두께 안인지 본다. 사양의 화판·뒤틀 항목도 액자형에만 적는다 |
| `engine/builder.py` | 검사 2개를 더했다. `back_frame_geometry`는 뒤틀 개수와 조립한 테두리·안쪽 크기, 부재별 Z(사양과 DXF XDATA 둘 다)를 재고, `artwork_covers_inner_and_fits_back_frame`은 저장 DXF의 화판 윤곽을 뒤틀·고정틀과 견준다. 두 검사는 액자형이 아닌 설계에서도 돌며 "없음"을 확인하므로 검사 ID 목록이 설계와 상관없이 같다. 부재 계열별 개수 검사는 `B`로 시작하는 계열을 건너뛴다(뒤틀 수는 `back_frame_geometry`가 센다). `requested_size_matches_measured_frame`은 기준이 `artwork`이면 뒤틀 안쪽에서 끼움 여유를 빼 화판 크기를 다시 잰다. 03 조립도는 뒤 층 부재와 화판 가장자리를 숨은선으로 그리고 화판 치수를 적으며, 04 열림도는 뒤틀·스페이서·화판의 층 단면을, 02 상세도는 새 단면 `BF`를 그린다. `HIDDEN` 선 종류는 액자형 설계에만 만들고, Z는 0이 아닌 부재만 XDATA에 적는다. 그래서 다른 설계의 DXF는 바이트까지 같다. 원판 아래 메모는 11줄 그대로이고 뒤틀 위치는 기존 문장을 늘려 적었다 |
| `engine/cad_helpers.py` | PNG를 그릴 때 화판·스페이서·숨은선을 알아본다 |
| `formats.py` | 액자형 패키지의 상세 목록에 `BF`를 더한다 |
| `llm/tools.py` | 검사 수 68 → 70 |
| `tests/test_generator.py` | 생성 요청에 A2 420 × 594 화판을 4×8 원판으로 만든 설계를 더했다(경우 23개에서 24개). 기존 시험이 이 설계의 부품 수, 검사 ID 목록, 상세도, 원판 안 도형도 본다. 새 시험 `test_artwork_panel_sits_in_a_back_frame_one_layer_behind`는 매개변수·사양·저장 DXF·검사 결과를 읽고, 다른 설계가 같은 검사 목록을 내는지 보고, 액자형 요청을 거부하는 규칙을 하나씩 확인한다 |
| `tests/results.json` | 시험 수(20개에서 21개), 소스 해시 16개 가운데 6개, 경우별 package_id 24개, 기록 줄 `artwork_back_frame` |
| `tests/test_web.py`, `tests/test_llm.py` | 검사 수 68 → 70 |
| `examples/built_packages.json`, `examples/README.md`, `README.md` | 예제 5종의 새 package_id와 검사 수. `README.md`에는 입력 표의 `artwork` 행, 「액자형(화판 기준)」 절, 상세 목록의 `BF` 줄을 더했다 |
| `docs/manual/README.md` | 검사 수 68 → 70 |

이슈 #15의 할 일 목록에 없던 변경은 0.5.0 절 머리의 두 문장(#15 소개, 검사 수가 바뀌어 `validation_report.json`과 `README.txt`가 달라진다는 단서), 검사 68 → 70에 따른 문서와 시험의 숫자, `face_note()`의 원판 메모 문장, `Renderer`의 화판·스페이서·숨은선 표시, README의 상세 목록 `BF` 줄이다.
반턱 규칙과 부재별 홈 수 표, 하드웨어와 04 열림도의 여닫이, `parts_manifest.csv`의 열은 그대로 두었다. 뒤틀은 그 표에 `assembly_group` `FIXED`, 홈 0개로 나온다. `presets/r3_parameters.json`도 고치지 않았다. 고치면 모든 설계의 `design_parameters.json`이 바뀐다. 웹 화면의 화판 입력과 LLM 도구의 입력 스키마, 설명서의 액자형 설명은 [#16](https://github.com/kcenon/hanok_window/issues/16)이다.

| 확인 | 결과 |
|---|---|
| 같은 PC 비교 | 요청 12개(예제 5종, 463 × 586 양문 2+4, 같은 창 + 원판 `[1220, 900, 18]`, 창살 0×0, 창살 3×5, 600 × 800 + 그림 297 × 420(여백 10), `standard_4x8_v1`, 단문 왼쪽 경첩 420 × 900 2+6)를 main `799e168`과 이 수정 뒤에 각각 CLI(작업 프로세스 해시 시드 0)로 만들어 파일별 SHA-256으로 비교했다(액자형 4종을 더해 28번 빌드에 16.5초). main은 `git archive`로 푼 사본을 `PYTHONPATH`로 불렀고, 그 사본으로 만든 예제 5종의 package_id는 `examples/built_packages.json`의 옛 값과 같았다. 두 엔진 모두 `hanok_generator`가 없는 폴더에서 돌리고 불러온 모듈 위치를 확인했다. 12개 모두 파일 35개 중 `README.txt`, `validation_report.json`, `environment.json`, `package_manifest.json`, 고친 소스 6개만 다르고, `window.dxf`, `design_spec.json`, `design_parameters.json`, PNG 5장, CSV 4종을 포함한 25개는 같다. revision과 네스팅 범위가 같고, 검사는 main 68개, 이 수정 뒤 70개가 모두 통과했다 |
| 액자형 4종 | A2 420 × 594를 4×8 원판에 기본값으로 만들면 외경 484 × 658, 내경 404 × 578, 뒤틀 폭 31 mm, 뒤틀 안쪽 422 × 596, 화판 원점 (32, 32)이고 부품 28개, 홈 104개, 도그본 48개, 검사 70개가 통과한다(package `bb1a0459…`, revision `HANOK_GEN_V1_f844adc5013a`). A3 297 × 420을 1220 × 900 원판에 만들면 부품 28개에 네스팅 `[20, 20, 1134, 348]`(`34e0a845…`), 단문 왼쪽 경첩 A3에 두께 10 · 덮는 폭 12 · 여유 2 · 스페이서 5 · 창살 2×6은 부품 20개, 홈 72개(`3257f03a…`), A2에 스페이서 0은 부품 28개(`015bc6cd…`)이고 모두 검사 70개가 통과한다 |
| 저장 DXF | A2 패키지에서 뒤틀 4개가 `CUT_THROUGH`에 있고 XDATA `assembly_z_mm`이 −20이며 홈은 0개다. 다른 부재에는 `assembly_z_mm`이 없다. 03 조립도의 뒤틀 4개는 `HIDDEN`, 화판 윤곽은 `A3_DASHDOT` 선 종류다. 상세는 `BF`를 포함해 6개, 원판 아래 메모는 11줄이고 원판 위에 가공·이름표 말고 다른 도형은 없다. `parts_manifest.csv`는 열이 그대로이고 뒤틀 행은 `assembly_group` `FIXED`에 `pocket_count` 0이다 |
| 거부 규칙 | 덮는 폭 1 · 여유 1은 `artwork.cover_hides_edge`(required_greater_than 1), 덮는 폭 31은 `artwork.back_member_width`(뒤틀 폭 8, 최소 10, 덮는 폭은 29까지), 두께 18 · 스페이서 3은 `artwork.depth_within_stock`(필요 21, 원판 20), 매개변수에서 화판 가로만 400으로 바꾸면 `artwork.covers_inner`(필요 [420, 594])로 걸린다. `picture`를 함께 주면 `input.artwork_picture`, R3 프리셋은 `input.preset_artwork`, `outer_mm`을 함께 주면 `input.size_basis`, `artwork`에 모르는 항목을 넣으면 `input.artwork`, 화판 2500 × 594는 `nesting.part_fits_stock`(부재 [2564, 40], 쓸 수 있는 크기 [2380, 1180])이다 |
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.1초), 생성기 21개 PASS(새 시험 포함, 197.4초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 13.2초), LLM 21개 PASS(14.0초). 생성기 시험을 스크립트로 먼저 돌려 `tests/results.json`을 다시 적었고, 시험 뒤 바뀐 추적 파일은 고친 파일과 그 파일뿐이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사는 70개, 부품·홈·도그본 수는 그대로다. R3는 `08bb7527…`이고, revision `HANOK_GEN_V1_04a2ec4c4f06`과 `window.dxf` SHA-256 `25ccf2f3…`는 그대로다 |

### 액자형 웹·LLM·설명서 (#16)

2026-09-16. #15로 엔진이 만드는 액자형을 웹 화면·LLM 도구·설명서가 입력받게 했다([#16](https://github.com/kcenon/hanok_window/issues/16)). 설계 화면의 크기 기준에 「화판」을 더해 화판 크기로 창을 지정하고, 화판 두께·덮는 폭·끼움 여유·스페이서 네 칸을 기본값 3 · 8 · 1 · 3 mm가 채워진 채로 보여 준다. 화판 기준을 고르면 그림 칸은 잠긴다. 화판이 그림 자리를 대신하기 때문이다. 미리보기는 뒤틀을 고정틀 뒤 한 층으로 흐리게 먼저 그리고 화판을 파선 윤곽으로 덧그린다. 새 규칙 넷에 한국어 문구와 고침 제안을 붙였고, LLM 도구의 입력 스키마·설명·`hint`도 화판을 안다.
`package.source_files()`가 모으는 파일(`hanok_generator/*.py`, `engine/*.py`, `presets/*.json`, `request.schema.json`)은 하나도 고치지 않았다. 그래서 기존 패키지 ID가 그대로다. 설명서 그림을 다시 찍으며 만든 예제 5종의 package_id가 `examples/built_packages.json`의 값과 같다. `tests/results.json`도 다시 쓰지 않았다. 0.5.0 태그 전이라 버전은 올리지 않았다.

| 파일 | 내용 |
|---|---|
| `web/service.py` | 미리보기 결과에 화판 사각형(`assembly.artwork`)을 더한다. 뒤틀은 `build_parts()`가 이미 돌려주므로 따로 만들지 않는다. `meta`에 화판 기본값과 범위를 싣고, 새 규칙이 가리키는 입력 묶음을 정한다. 제안은 요청이 쓴 크기 기준으로 돌려준다. 패키지 요약에도 화판을 실어 기록·패키지 화면과 LLM 목록 도구가 액자형을 알아본다 |
| `web/suggest.py` | 액자형 규칙 셋(`cover_hides_edge`, `back_member_width`, `depth_within_stock`)에 통과하는 값을 제안하고, 깊이 규칙에는 원판 두께도 함께 제안한다. `artwork.covers_inner`는 넣지 않았다. 요청이 화판을 주면 엔진이 틀을 유도하므로 구조상 성립한다 |
| `web/static/index.html`, `app.css` | 크기 기준 라디오의 셋째 칸과 「화판 · 액자형」 입력 묶음, 뒤틀·화판 범례. 클래스 이름이 부재 계열에서 만들어지므로 `mk-back_frame`·`nk-back_frame`이 없으면 뒤틀만 색 없이 그려진다 |
| `web/static/app.js` | 화판 네 칸을 읽고 쓰고, 세 기준을 오프셋 하나로 오간다(외경 0, 내경 −2 × 고정틀 폭, 화판 2 × 덮는 폭 − 2 × 고정틀 폭). 요청에는 화판 크기를 늘 싣고 나머지 넷은 기본값과 다를 때만 싣는다. 액자형이면 그림 키를 아예 빼고 그림 칸을 잠근다 |
| `web/static/preview.js`, `messages.js` | 뒤틀을 계열 순서 맨 앞에서 그려 앞 부재가 덮게 하고, 화판을 파선으로 덧그린다. 새 규칙 일곱 가지의 한국어 문구와 제안 문장, 부재 이름 `B01`·`B02`, 크기 기준 이름 |
| `llm/tools.py` | `design_schema()`의 `artwork` 객체, 규칙별 `hint`, `check_design` 결과의 화판, `canonical_request()`의 화판 정규화. 폼과 같은 규칙으로 정규화해야 같은 설계가 화면·CLI·도구에서 같은 package_id를 받는다 |
| `docs/manual/README.md`, `README.md` | 설명서의 「액자형(화판)」 절과 그림, 입력·미리보기·규칙 표. 생성기 README의 웹 화면 표와 기준 전환 문장 |
| `docs/manual/make_images.py` | Chrome을 파이프 대신 DevTools 포트로 몬다. `--remote-debugging-pipe`는 fd 3·4를 자식에게 넘기는데 `preexec_fn`·`pass_fds`가 POSIX 전용이라 Windows에서는 이 스크립트가 아예 돌지 않았다(`AssertionError: pass_fds not supported on Windows`). 포트와 `DevToolsActivePort`, 표준 라이브러리 WebSocket으로 바꿔 세 OS가 같은 경로를 쓴다. 액자형 화면 촬영 단계도 더했다 |
| `docs/manual/images/` | 그림 20장을 이 PC에서 다시 찍었다. 새 그림은 `design-artwork.png`와 `design-artwork-preview.png`다 |
| `tests/test_web.py`, `tests/test_llm.py` | 액자형 미리보기, 규칙 일곱 가지의 입력 묶음, 제안 네 경우, node 폼 대조, `check_design`의 화판. 웹 20 → 21개, LLM 21 → 22개 |

이슈 #16의 할 일 목록에 없던 변경은 `make_images.py`의 전송 방식, 폼이 액자형 요청에서 그림을 빼는 것, 크기 제안이 화판을 틀과 함께 옮기는 것, 패키지 요약의 화판이다. 뒤의 둘은 원형에서 드러난 결함이다.
크기 제안은 `frame.outer_*`만 시험 삼아 바꾸면 「화판 = 내경 + 2 × 덮는 폭」이 깨져 `artwork.covers_inner`가 대신 걸리고, 찾던 규칙이 아니므로 탐색이 아무 값에서나 통과로 끝났다. 고치기 전에는 창살 규칙이 화판 가로 201 mm를 제안했고 그 값으로는 같은 규칙에 다시 걸렸다. 고친 뒤에는 266 mm를 제안하고 통과한다.
그림은 화면에서 칸을 잠그는 것만으로는 부족했다. R3 예제에서 시작해 기준만 화판으로 바꾸면 폼에 그림이 남아 함께 실려 `input.artwork_picture`로 거부된다. 설명서의 액자형 촬영이 이 때문에 먼저 실패했다.

| 확인 | 결과 |
|---|---|
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, `PYTHONUTF8`과 `PYTHONIOENCODING` 없음. 인코딩 1개 PASS(0.1초), 생성기 21개 PASS(200.4초), 웹 21개 중 16개 PASS·5개 건너뜀(`web.sh` 시험, 13.5초), LLM 22개 PASS(14.1초). 생성기 시험을 `unittest discover`로 돌려 `tests/results.json`을 다시 쓰지 않았다. 스크립트로 돌리면 경우 기록 순서만 바뀐 파일이 나온다 |
| 미리보기 | A2 420 × 594를 `standard_4x8_v1`로 보면 크기 기준 `artwork`, 외경 484 × 658, 내경 404 × 578이고 부재 28개 가운데 뒤틀 4개가 계열 `BACK_FRAME`·무리 `FIXED`다. 화판 사각형은 (32, 32)–(452, 626), 뒤틀 폭 31 mm, 뒤틀 안쪽 422 × 596이다. 액자형이 아닌 설계는 `assembly.artwork`가 비어 있다 |
| 제안 | 덮는 폭 1은 `artwork.cover_hides_edge`(끼움 여유 0.9 이하 또는 덮는 폭 1.1 이상), 덮는 폭 31은 `artwork.back_member_width`(덮는 폭 29 이하), 두께 18은 `artwork.depth_within_stock`(두께 17 이하, 스페이서 2 이하, 원판 두께 21 이상), 화판 2500 × 594는 `nesting.part_fits_stock`(원판 길이 2584 이상, 화판 가로 2316 이하), 화판 200 × 300에 창살 6+4는 `lattice.positive_gap`(세로 창살 2개 또는 화판 가로 266 이상)이다. 제안값 10개를 모두 새 요청으로 다시 넣어 통과를 확인했다. 액자형에서는 `leaf.aspect_ratio`에 닿을 수 없다. 세장비 규칙을 가진 프리셋은 R3뿐인데 R3는 액자형과 함께 쓸 수 없다 |
| 설명서 그림 | 이 PC에서 `make_images.py`가 끝까지 돌아 화면 15장과 도면 축소 5장을 다시 만들었다. 새 그림은 `design-artwork.png`(560 × 785)와 `design-artwork-preview.png`(1328 × 1701)다. 로그에 남는 `POST /api/preview 422` 한 줄은 일부러 규칙을 어기는 `design-error.png` 단계의 것이고, 액자형 촬영이 거치는 중간 상태 다섯은 모두 200이다 |
| 경계 | 바뀐 파일은 코드·문서 13개와 그림 20장뿐이다. 촬영이 만든 예제 5종의 package_id가 `examples/built_packages.json`의 값과 같다(R3 `08bb7527…`, `4447558f…`, `fe901c3a…`, `6ae3609b…`, `a0042ddb…`) |

### DWG 내려받기 (#17)

2026-09-16. 패키지 화면에서 `window.dxf`를 AutoCAD 2010 형식 DWG로 바꿔 받게 했다([#17](https://github.com/kcenon/hanok_window/issues/17)). 변환은 받을 때 실행하고 결과를 패키지에 넣지 않는다. ODA File Converter 27.1.0으로 같은 DXF를 세 번 바꿔 보면 길이는 같은데(R3 58,571 B) 0x118의 8바이트, 0x15E의 2바이트, 그리고 끝부분 757~825바이트가 매번 다르다. package_id가 파일 바이트의 해시인 이상 DWG는 패키지 파일이 될 수 없다.
되돌리기는 손실이 없다. DXF → DWG → DXF로 돌아온 도면은 XDATA(`HANOK_PORTRAIT_DL`)를 부재 744개(R3)·826개(액자형) 전부에서 유지하고, 레이어 14종과 선 종류(액자형의 `HIDDEN` 포함), 단위(mm), `ezdxf` 메타데이터도 그대로여서 저장 DXF 검사 70개를 다시 통과한다.
`package.source_files()`가 모으는 파일은 하나도 고치지 않았다. 새 모듈을 `hanok_generator/`에 두면 `root.glob("*.py")`에 걸려 모든 package_id가 바뀌므로 `web/` 아래에 두었다. 변환기 버전도 `environment.json`에 적지 않는다. 그 파일은 패키지 파일이라, 적으면 변환기가 있는 PC와 없는 PC가 같은 입력에서 다른 package_id를 내게 된다. 대신 `/api/packages/<id>` 응답과 패키지 화면이 변환기 버전을 보여 준다.

| 파일 | 내용 |
|---|---|
| `web/dwg.py` (새 파일) | 변환기를 찾고(`HANOK_ODAFC` → `PATH` → `C:\Program Files\ODA\ODAFileConverter*`), 폴더 이름에서 버전을 읽고, 임시 폴더에서 한 번 변환한다. 표준 라이브러리만 쓴다. `ezdxf.addons.odafc`를 쓰지 않는 이유는 둘이다. 그것을 부르면 서버 프로세스에 ezdxf가 들어와 격리 시험이 깨지고, 기본 경로가 `…\ODA\ODAFileConverter\`여서 winget이 만든 `…\ODAFileConverter 27.1.0\`을 찾지 못한다 |
| `web/service.py` | `package_dwg()`가 매니페스트 해시로 확인한 `window.dxf` 바이트만 변환기에 넘긴다. 변환기는 임시 폴더의 사본을 읽으므로 공개된 패키지 폴더는 다른 프로그램에 넘어가지 않는다. 패키지 응답에 `dwg` 상태를 싣는다 |
| `web/server.py` | `/files/<id>/window.dwg` 경로(파일 경로보다 앞에 둔다), 형식 표의 `.dwg`, 변환기가 없으면 501·변환이 실패하면 502. 바이트가 매번 다르므로 `immutable` 캐시를 붙이지 않는다 |
| `web/static/packages.js`, `messages.js`, `app.css` | 내려받기 목록 맨 위의 DWG 줄. 변환기가 없으면 설치 안내가 대신 나온다 |
| `docs/manual/README.md`, `README.md` | 설명서의 내려받기 절과 생성기 README의 「DWG 내려받기」 |
| `tests/test_web.py`, `tests/test_generator.py` | 끝점과 상태 보고, 그리고 왕복 검사 70개(변환기가 없으면 건너뛴다). 격리 시험은 DWG 요청까지 보낸 뒤에도 서버 프로세스에 ezdxf가 없음을 확인한다. 웹 21 → 22개, 생성기 21 → 22개 |

| 확인 | 결과 |
|---|---|
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0, ODA File Converter 27.1.0. 인코딩 1개 PASS(0.1초), 생성기 22개 PASS(214.5초), 웹 22개 중 17개 PASS·5개 건너뜀(`web.sh` 시험, 13.7초), LLM 22개 PASS(14.1초). `HANOK_ODAFC`를 없는 경로로 두고 웹 시험을 다시 돌려도 22개가 같은 결과로 통과한다(끝점 501). 생성기 시험을 `unittest discover`로 돌려 `tests/results.json`을 다시 쓰지 않았다 |
| 왕복 | R3와 액자형 A2를 DXF → DWG → DXF로 돌린 도면이 검사 70개를 통과하고 XDATA 부재 수가 원본과 같다(744, 826). 두 도면의 레이어는 14종이고 액자형에는 `HIDDEN`이 있다. 변환은 이 PC에서 R3 기준 한 번에 0.28초, DWG로 바꿨다가 DXF로 되돌리기까지 0.59초다 |
| 바이트 | 같은 DXF를 세 번 바꾼 DWG의 SHA-256이 모두 다르고 길이는 같다. 차이는 늘 같은 자리(0x118의 8바이트, 0x15E의 2바이트, 끝부분 한 덩어리)에서 난다 |
| 경계 | `source_files()`가 모으는 파일을 하나도 고치지 않았다. 패키지 파일은 34개 그대로이고 `window.dwg`는 매니페스트에도 ZIP에도 없다 |
| 변환기 없음 | 끝점이 501과 `dwg.converter_missing`을 돌려주고, 패키지 화면은 설치 안내를 보여 주며, 패키지 생성·내려받기·검사는 그대로 동작한다. CI 세 OS에는 변환기가 없으므로 이 경로가 CI에서 돌고 왕복 시험은 건너뛴다 |

### AI 파일 저장 (#18)

2026-09-16. 도면을 Illustrator 8 형식(옛 PostScript 텍스트 AI)으로도 저장해 패키지에 넣었다([#18](https://github.com/kcenon/hanok_window/issues/18)). Illustrator 8부터 CS6 이후 버전까지 연다. 담는 것은 원판 위 가공 도형뿐이다. 부재 윤곽·홈·도그본·부재 번호와 원판에 배치한 하드웨어 참고 표시를 레이어로 나눠 담고, 조립도·상세도·열림도·치수·가공 메모는 담지 않는다. 담을 것을 고르는 규칙은 `ai_export.board_entities()` 한 곳에 두고 시험이 그것을 부른다.
DWG와 달리 AI는 패키지 파일이다. 외부 변환기를 부르지 않고 직접 쓰므로 바이트를 고정할 수 있다. 만든 시각·작업 ID·기계 정보를 적지 않고, `%%CreationDate`도 넣지 않는다. 부재 번호도 글꼴 파일 대신 2 × 4 격자 위에 정의한 획 글꼴로 그린다. 부재 번호에 쓰이는 문자는 `BFLS0123456789-` 15종뿐이다. 글꼴 파일을 읽었다면 PNG처럼 package_id가 그 PC에 설치된 글꼴에 딸려 갔을 것이다.
좌표는 mm × 72/25.4를 소수 7자리로 쓴다. 자릿수는 취향이 아니라 되읽기 검사가 정한다. 6자리면 꼭짓점이 2.4e-7 mm 떨어져 돌아와 `LENGTH_TOL_MM`(1e-7 mm)을 넘고, 7자리면 2.4e-8 mm로 들어온다.
레이어 색에는 DXF 색 인덱스를 옮기지 않는다. `CUT_THROUGH`와 `PART_ID`는 인덱스 7이고 ezdxf 팔레트에서 이는 흰색이라, 그대로 옮기면 흰 배경에서 절단 윤곽과 부재 번호가 보이지 않는다. 도형 색은 CMYK(`K`)로 준다. RGB 연산자 `Xa`/`XA`는 사양서에 7.0 도입으로 적혀 있어 더 오래된 프로그램에서 안전하지 않다.
`%%Creator`에는 이 생성기 이름을 적는다. 사양서가 그 주석을 「PostScript 문서를 생성한 응용 프로그램을 식별한다」로 정의하므로 Illustrator 이름을 적는 것은 사실과 다르다. 형식을 알아보게 하는 것은 `%!PS-Adobe-3.0` 머리와 `Lb`/`Ln`/`LB` 레이어 연산자다. procset 본문은 넣지 않는다. Illustrator는 prolog의 주석만 읽고 자기 procset을 쓴다.
출력기를 `engine/`에 둔 것은 패키지 안 `source/`만으로 패키지를 다시 만들 수 있어야 하기 때문이다. `package.source_files()`가 `engine/*.py`를 통째로 모으므로 따로 등록할 곳은 없고, 그 대신 모든 package_id가 바뀐다. 이는 이슈가 예고한 대로다.

| 파일 | 내용 |
|---|---|
| `engine/ai_export.py` (새 파일) | 출력기와 파서. 새 의존성은 없고 표준 라이브러리와 `ezdxf`가 읽어 준 엔티티만 쓴다. 원호는 bulge를 `numeric_policy.bulge_arc()`로 푼 뒤 30° 이하 조각마다 3차 베지어 하나로 낸다(`k = 4/3 · tan(θ/4)`). `read()`는 `write()`의 자료 구조를 재사용하지 않고 텍스트만 보고 경로를 복원하므로, 출력기의 좌표 계산이 틀리면 검사에 걸린다 |
| `engine/builder.py` | `Design`에 `AI`, `configure()`에서 `OUT/'window.ai'`. `build()`가 `_validated_candidate.ai`를 후보로 쓰고 두 검사 단계를 통과한 뒤에만 자리에 넣는다. 저장 전 메모리 상태의 도면에서 쓰므로 두 단계가 같은 검사 목록을 돈다. 새 검사 `ai_export_matches_saved_dxf`(대상 `saved_ai`)는 `check_metadata()` 바로 앞에서 돈다 |
| `package.py` | `REQUIRED`에 `window.ai` |
| `web/server.py`, `web/static/packages.js` | 형식 표의 `.ai`(`application/postscript`)와 내려받기 목록의 `window.ai`. 패키지 파일이므로 DWG와 달리 `immutable` 캐시가 붙는다 |
| `llm/tools.py` | 검사 수 70 → 71. `read_package_file` 설명에서 DXF·PNG와 함께 AI도 뺀다. `TEXT_FILES`는 그대로여서 끝점이 이미 거절한다 |
| `tests/test_generator.py` | 새 시험 `test_ai_export_carries_the_board_and_nothing_else`. 모든 설계에서 레이어가 기대한 것과 같고 참고 레이어가 없으며, 되읽은 좌표가 DXF와 `LENGTH_TOL_MM` 안에서 같고, 모두 원판 안에 있으며, 두 번 써도 바이트가 같은지 본다. 좌표 대조는 출력기의 비교 함수를 쓰지 않고 시험 안에서 직접 잰다. 생성기 22 → 23개 |
| `tests/test_web.py`, `tests/test_llm.py` | 검사 70 → 71, 패키지 파일 34 → 36. `window.ai`가 파일 목록에 있는지도 본다. 개수는 그대로(웹 22개, LLM 22개) |
| `tests/results.json` | 소스 해시가 8개가 되고(`engine/ai_export.py`) 경우별 package_id 17개가 모두 바뀌었다 |
| `examples/built_packages.json`, `examples/README.md` | 예제 5종의 새 package_id와 검사 71개·파일 36개 |
| `docs/CHANGELOG.md`, `docs/manual/README.md`, `README.md` | 검사 수·파일 수, 설명서 파일 표의 `window.ai` 줄, 생성기 README의 「AI 파일」 절 |
| `docs/manual/images/` | 화면에 파일 목록과 검사 수가 나오는 `package.png`·`package-checks.png`·`package-files.png` 3장만 다시 찍었다 |

| 확인 | 결과 |
|---|---|
| Windows 시험 | Windows 11 한국어 로캘(AMD64), CPython 3.11.15, Pillow 12.3.0. 인코딩 1개 PASS(0.1초), 생성기 23개 PASS(225.2초), 웹 22개 중 17개 PASS·5개 건너뜀(`web.sh` 시험, 13.8초), LLM 22개 PASS(15.0초). 이번에는 생성기 시험을 스크립트로 돌려 `tests/results.json`을 다시 썼다. `source_files()`가 모으는 파일이 늘고 바뀌었으므로 다시 쓰지 않으면 `test_source_bundle_excludes_the_web_layer`가 실패한다 |
| AI 파일 | R3(원판 1220 × 900)는 원판 위 도형 215개를 레이어 7종에 담아 78,140 B이고 경로는 340개다(도형 191개 + 부재 번호 24개를 그린 획 149개). 액자형 A2(원판 2400 × 1200)는 도형 223개 → 82,177 B, 경로 372개(195 + 177)다. 창살 없는 단문은 도형 40개 → 10,582 B이고 도그본이 없어 레이어가 6종이다. 모두 ASCII다 |
| 되읽기 | 되읽은 꼭짓점의 최대 오차는 R3 2.397e-8 mm, 액자형 2.269e-8 mm로 `LENGTH_TOL_MM`(1e-7 mm) 안이다. 베지어 조각의 최대 오차는 1.15e-6 mm로 `ARC_CHORD_TOL_MM`(1e-5 mm) 안이다. 이 오차는 t = 0.25 · 0.5 · 0.75에서 쟀다. t = 0.5만 재면 근사가 그 점에서 원에 정확히 닿도록 만들어져 있어 1e-13 mm가 나오고, 실제 오차를 말해 주지 않는다 |
| 같은 바이트 | 같은 입력을 서로 다른 출력 폴더에 두 번 만들면 `window.ai`의 SHA-256이 같다(R3 `6e9a7ae4…`) |
| 경계 | `window.dxf`는 바이트까지 그대로다. R3의 SHA-256은 `25ccf2f3…`으로, 이 절의 「액자형 화판과 뒤틀 (#15)」에 적힌 값과 같다. 바뀐 것은 패키지 파일 수(34 → 36)와 검사 수(70 → 71), 그리고 그에 딸린 `validation_report.json`·`README.txt`·`environment.json`·`package_manifest.json`이다 |
| 예제 5종 | 새 package_id 5개가 옛 값과 모두 다르고, 검사는 71개, 부품·홈·도그본 수는 그대로다. R3는 `645289be…`다 |
| CI | PR #26의 커밋 `bfd89c2`에서 세 OS가 모두 통과했다(`macos-latest` CPython 3.11.9 arm64 6분 21초, `ubuntu-latest` CPython 3.11.16 12분 55초, `windows-latest` CPython 3.11.9 16분 5초). `R3 package manifest` 단계의 파일은 세 OS 모두 36개, 검사는 71개다. `window.ai`의 SHA-256은 세 OS와 이 PC에서 모두 `6e9a7ae4…`로 같다. 같은 단계의 `window.dxf`는 ubuntu만 `6fc8aa36…`이고 macOS·Windows는 `25ccf2f3…`다. 이 절 머리글에 적은 기존 현상이며, 그 차이는 참고 그림의 점 하나에서 나므로 원판 위 도형만 담는 AI 파일에는 나타나지 않는다 |
| Illustrator | 이 PC에 Illustrator가 없어 실제로 열어 확인하지는 못했다. 형식은 사양서(1998-02-23, AI 7)의 문서 구조·레이어·경로·색 연산자를 따랐고 파서로 되읽어 대조했지만, 프로그램에서 열리는지는 사람이 한 번 봐야 한다 |

### 운영체제 간 패키지 바이트 비교 (#27)

2026-09-17. CI에서 같은 R3 요청으로 만든 세 운영체제의 매니페스트를 아티팩트로 올리고, 세 시험 작업이 끝난 뒤 파일별 해시와 크기를 비교한다. 기존에는 매니페스트를 로그에 출력하고 사람이 읽어 비교했다. 이제 파일 목록 불일치, 아티팩트 누락·중복, 잘못된 매니페스트, 기대 목록 밖의 바이트 차이는 비교 작업을 실패시킨다. 전체 시험 작업이 실패한 경우에도 비교 작업은 성공으로 끝나지 않는다.

비교기와 기대 목록은 `tools/compare_package_manifests.py`에 두었다. 표준 라이브러리만 쓰고, `package.source_files()`가 모으는 소스 밖이므로 이 변경으로 생성 파일이나 패키지 ID가 바뀌지 않는다. 패키지 ID 자체는 운영체제 사이에서 비교하지 않는다. 예외는 환경 기록, 시스템 글꼴을 쓰는 PNG 5장, 측정값과 DXF 해시를 담는 검증 기록, 우분투 DXF이며 각 항목에 근거를 적었다. 맥과 윈도의 DXF는 같아야 하고 AI는 세 운영체제 모두 같아야 한다. 예외 파일의 차이가 없어지면 실패시키지 않고 정리 대상으로 알린다.

`tests/test_package_comparison.py`는 정상·예외 통과, 파일 순서, 해시·크기 변화, 맥과 윈도의 DXF 불일치, 파일과 아티팩트 누락·중복, 잘못된 JSON과 필드를 확인한다. 실제 아티팩트 시험은 정상 세 매니페스트의 통과 뒤 임시 사본에서 우분투 AI 해시 하나를 바꾸고 패키지 ID를 다시 계산하여, CI와 같은 비교 명령이 종료 코드 1로 실패하는지 단언한다. 비교 작업에서 내려받은 세 아티팩트로 실행한다. 실행 명령과 예외의 한계는 [생성기 검증 안내](../README.md#검증)에 적었다. 해시만 비교하므로 예외 파일 안의 변화량을 제한하거나 실제 도면 내용을 검증하는 단계는 아니다.

### CI 의존성 설치 캐시 (#28)

2026-09-17. 세 운영체제 시험 작업의 `setup-python`에 `cache: pip`와 저장소 루트 기준 `cache-dependency-path: generator/requirements.lock`을 추가했다. 다운로드한 패키지를 재사용하고, 가상환경 생성·잠금 파일 설치·현재 소스 설치는 매번 실행한다. 표준 라이브러리만 사용하는 패키지 비교 작업에는 캐시를 추가하지 않았다.

문서의 검사 개수·파일 개수도 코드와 맞아야 하므로 경로 필터는 도입하지 않았다. 문서만 바뀐 PR에도 기존 다섯 시험과 운영체제 간 패키지 비교를 실행한다. 선택 항목인 소수 외곽 시험 분리는 후속 작업으로 남기고 일반·최적화 실행 각 200건을 유지했다. 캐시 효과는 같은 PR·커밋을 다시 실행해 운영체제별 적중 여부와 설치 시간을 비교하며, 실제 실행 근거와 전체 작업 시간은 해당 PR에 기록한다. 캐시가 적중했다는 사실과 실행 시간이 줄었다는 측정 결과는 구분한다.
