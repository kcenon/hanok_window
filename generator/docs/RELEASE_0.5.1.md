# 0.5.1 릴리스 안내

배포 버전은 **0.5.1**, 생성 엔진은 **0.3.0**입니다. 태그 `v0.5.0` 이후의 과거 패키지 검증 호환성, 예제 7종 공개, 빌더 분리, 운영체제 간 출력 일치 수정을 담습니다. 상세 구현과 측정 결과는 [변경 기록](CHANGELOG.md)의 `0.5.1` 항목과 [후속 작업 기록](FOLLOWUPS_2026_09.md)에 있습니다.

## 0.5.0에서 전환할 때

**같은 입력이라도 0.5.1에서 다시 만든 패키지의 `package_id`는 0.5.0에서 만든 값과 다릅니다.** 패키지에 들어가는 소스에 `rendering.py`·`reports.py`가 추가되고 `builder.py`·`package.py`가 바뀌었으며, `environment.json`에 필수 파일 목록이 기록되기 때문입니다.

- 같은 설계인지 비교할 때는 계속 `revision`을 사용합니다. R3 입력의 revision은 `HANOK_GEN_V1_04a2ec4c4f06` 그대로입니다.
- 같은 환경에서 예제 7종의 내용 파일 17개씩은 분리 전후 바이트까지 같았습니다. DXF·AI·CSV의 도면 내용은 바뀌지 않았습니다.
- 새 패키지는 **검사 71개**, 매니페스트에 기록하는 **파일 40개**, `package_manifest.json`을 포함한 ZIP **41개**입니다.
- 0.4.x처럼 AI 출력 도입 전에 만든 정상 패키지도 읽기 전용 검증(`verify`)에서 무결성 실패로 잘못 표시되지 않습니다.

## 바뀐 기능

| 범위 | 0.5.1의 동작 |
|---|---|
| 과거 패키지 검증 | 새 패키지는 생성 당시 필수 파일 목록을 해시로 보호되는 `environment.json`에 남기고, 검증은 그 목록을 씁니다. AI 도입 전 패키지는 공통 파일과 당시 AI 검사 유무로 구분합니다. |
| 예제 공개 | 액자형 A2·4×8 원판을 더한 예제 7종의 실제 패키지를 `examples/packages/`에 싣고, `examples/make_packages.py --check`로 입력·포함 소스·파일 목록을 대조합니다. |
| 빌더 분리 | PNG 렌더를 `rendering.py`, CSV·README 작성을 `reports.py`로 옮겼습니다. |
| 작업 프로세스 | 생성 작업의 표준 입력을 `DEVNULL`로 연결해 MCP 클라이언트의 입력 파이프를 물려받아 Windows에서 멈추던 문제를 고쳤습니다. |
| 기본 글꼴 기록 | 시스템 글꼴이 없어 Pillow 기본 글꼴을 쓸 때 환경 기록이 `TypeError`로 실패하던 문제를 고쳤습니다. |
| PNG 글자 배치 | CAD 주석의 글자 배치를 `ImageFont.Layout.BASIC`으로 고정해 macOS·Ubuntu PNG가 픽셀까지 같습니다. |
| CI | 세 운영체제의 Python 3.11과 Ubuntu Python 3.12·3.13, 공식 MCP SDK 연동, Chrome 브라우저 흐름, 운영체제 간 R3 패키지 비교를 실행합니다. |

## 남은 확인

AI·DWG를 실제 프로그램으로 여는 확인과 실물 제작 확인은 [#45](https://github.com/kcenon/hanok_window/issues/45)에서 계속 추적합니다. 절차는 [사용자 확인 문서](ACCEPTANCE.md)에 있습니다. 실제 증거가 생기기 전까지 `manufacturing_status=PENDING`을 유지합니다.

## 작업 흐름 변경

0.5.1부터 변경은 `develop`으로 squash 병합하고, `main`에는 `develop` → `main` 릴리스 PR만 squash 병합합니다. 자세한 내용은 [저장소 안내의 작업 흐름](../../README.md#작업-흐름)에 있습니다.
