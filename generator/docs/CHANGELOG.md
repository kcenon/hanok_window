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

2026-09-14. 한국어 로캘(cp949) Windows에서 저장소를 받고 시험을 돌릴 수 있게 했다([#3](https://github.com/kcenon/hanok_window/issues/3)). Windows 호환을 세 단계(#3~#5)로 나눈 계획의 첫 단계로, 패키지 `source/`에 들어가는 파일(최상위 모듈·`engine/`·`presets/`·스키마)은 고치지 않았다. 그래서 모든 package_id가 그대로다. 배포 버전은 `environment.json`에 들어가지 않으므로 0.4.2로 올려도 package_id는 바뀌지 않고, 엔진 `__version__`은 0.2.0 그대로다.

| 파일 | 내용 |
|---|---|
| `.gitattributes` (새 파일) | 글 파일을 모든 OS에서 LF로 받는다. `r3_reference/`는 `-text`로 두어 CRLF로 커밋된 R3 CSV 4개까지 바이트 그대로 받는다. 이 파일이 없으면 Git for Windows 기본값(`core.autocrlf=true`)이 LF 파일을 CRLF로 받아, R3 원본 SHA-256 대조와 소스 해시 대조가 실패했다 |
| `tests/test_web.py` | fcntl을 쓰는 `web.control`은 POSIX에서만 불러온다. 그전에는 Windows에서 웹 시험이 import 단계에서 멈춰 하나도 돌지 않았다. 하위 프로세스 출력 6곳을 UTF-8로 읽는다 |
| `tests/test_llm.py` | 하위 프로세스 출력 3곳을 UTF-8로 읽는다 |
| `tests/test_generator.py` | 하위 프로세스 출력 3곳, 파일 읽기 9곳, 파일 쓰기 2곳에 UTF-8을 지정한다. 스크립트로 실행할 때 쓰는 `results.json`은 UTF-8·LF 바이트로 쓴다 |
| `llm/__main__.py` | `hanok-window-llm`의 표준 입력·출력·오류를 UTF-8로 바꾼다. 그전에는 파이프로 받은 JSON이 cp949로 나왔다 |
| `llm/tools.py` | 모델에게 주는 문구 두 곳(`build_package` 설명, `describe_generator`의 workflow). package_id는 같은 실행 환경에서만 같고, 같은 설계인지는 `check_design`·`get_package`의 `revision`으로 비교하라고 적었다 |
| `.github/workflows/tests.yml` (새 파일) | pull request와 main push에서 ubuntu·macOS로 세 시험을 돌리고, 시험 뒤 추적 파일이 바뀌지 않았는지 `git diff --exit-code`로 확인한다. 가상환경을 `generator/.venv`에 만들어 `web.sh` 시험도 돈다 |
| `README.md`, 저장소 `README.md`, `docs/manual/README.md` | Windows 설치·웹 화면·MCP 등록·시험 안내, package_id가 같은 범위 |
| `pyproject.toml` | 0.4.2 |

엔진이 인코딩을 지정하지 않고 파일을 읽고 쓰는 곳(`model.py` 등)은 고치면 모든 package_id가 한 번 바뀌므로 [#4](https://github.com/kcenon/hanok_window/issues/4)(엔진 0.3.0)로 넘겼다. 그때까지 Windows에서는 `PYTHONUTF8=1`이 필요하고, 엔진이 README를 CRLF로 쓰므로 `test_llm.py`의 `test_read_package_file_in_pages` 1개가 실패한다. Windows CI도 #4에서 켠다.
package_id는 도면 PNG(글꼴)와 `environment.json`(OS, Python과 라이브러리 버전, 소스 해시)을 담으므로 실행 환경이 같을 때만 같다. OS와 무관하게 같은 설계인지는 `revision`으로 본다. 이 뜻으로 이슈 #3의 할 일 목록에 없던 곳도 고쳤다: `build_package` 설명의 “The same request always yields the same package_id”, 설명서 준비물 표의 컴퓨터 줄(macOS만 적혀 있었다), 설명서 패키지 생성 절의 “같은 입력은 언제나 같은 패키지 ID”.

| 확인 | 결과 |
|---|---|
| package_id 경계 | main과 다른 파일에 `package.source_files()`가 모으는 파일이 없다 |
| 줄 끝 | `.gitattributes`를 넣고 다시 받은 뒤 `git status`가 깨끗하고, `git add --renormalize .`가 아무것도 올리지 않으며, 작업 트리가 CRLF인 파일은 R3 CSV 4개뿐이다 |
| Windows 시험 | Windows 11 한국어 로캘, CPython 3.11.15, `PYTHONUTF8=1`. 생성기 14개 PASS(199.4초), 웹 20개 중 15개 PASS·5개 건너뜀(`web.sh` 시험, 16.7초), LLM 21개 중 20개 PASS·1개 실패(`test_read_package_file_in_pages`, 19.0초). 시험 뒤 추적 파일은 바뀌지 않았다 |
| package_id 불변 | 같은 PC에서 main(LF로 받은 worktree)과 이 버전의 소스로 `examples/double_r3.json`을 만들면 package_id가 둘 다 `669c09fb…`다. macOS 예제의 `3d8e6187…`과 다른 것은 실행 환경이 달라서다 |
| macOS 예제 5종 | 이 PC에서는 만들 수 없어 직접 확인하지 않았다. 경계 안의 파일을 고치지 않았고, 웹 시험이 소스 해시 16개가 `tests/results.json`과 같음을 확인하므로 바뀌지 않는다 |
