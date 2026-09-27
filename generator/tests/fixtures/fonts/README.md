# CI 렌더 글꼴

`NotoSans.ttf`는 Google Fonts의 `NotoSans[wdth,wght].ttf` 원본이다.
파일 이름만 바꾸고 바이트는 유지했다. 라이선스는 함께 둔 `OFL.txt`다.

- 원본: https://github.com/google/fonts/blob/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf
- SHA-256: `bfb7bb691513f12e734dc346c03a03f784912432d7e3fa8e56efcf906fe86b3d`
- OFL.txt SHA-256: `cee9892f9f0cc8fe882c9e9537ee6a89621d86ee7ceaf70b02e2b2b1c25c061a`

CI는 `HANOK_FONT`로 이 파일을 지정한다. 운영체제마다 다른 시스템 글꼴을
허용하는 대신 같은 글꼴로 만든 PNG의 모든 RGBA 픽셀을 비교한다.
실행 패키지에 글꼴을 추가하지 않으며 일반 사용자 환경의 기본 선택도 유지한다.
