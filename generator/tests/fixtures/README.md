# 이전 패키지 검증 기준

`legacy_v0_4_1.zip`은 태그 `v0.4.1`의 생성 소스
(`9202934a29f1a34e5d489eb30c5a14abf9128c88`)로 `examples/double_r3.json`을
2026-09-27에 다시 만든 패키지다. 파일 34개, 검사 67개이며 AI 출력과
`environment.json`의 `package_format`이 도입되기 전 형식을 보존한다.

- 패키지 ID: `e6539f1c13eff237acc19478c5d50d418a02305cd8623871e543b76bbe3a5c8b`
- ZIP SHA-256: `e2345662a780677d9562dc6607d310da58fd6cfdc27b5d0a765b13f3b1d4ae29`
- 재생성 환경: CPython 3.11.15, macOS arm64, 현재 `requirements.txt`의 의존성.
  태그 배포 당시 PNG 바이트를 재현하려는 자료는 아니다.
- 포함 소스는 태그에서 추출했으며 생성과 동시에 당시 검증기가 PASS를 확인했다.
  시험은 이 코드를 실행하지 않고 패키지 파일을 읽기 전용으로 확인한다.
- `test_package_compatibility.py`가 현행 Python API·CLI·웹 서비스·LLM의 검증과
  변조 거절, 파일·매니페스트 무변경을 확인한다.

`r3_reference.json`은 기존 R3 기하와 원본 해시 기준이며 위 ZIP과 별개다.
