"""Start the local web interface: `hanok-window-web` or `python -m hanok_generator.web`."""
from __future__ import annotations

import argparse
from pathlib import Path
import signal
import sys
import webbrowser

from .server import make_server


def _interrupt(signum, frame):
    raise KeyboardInterrupt


def main(argv=None):
    parser = argparse.ArgumentParser(prog="hanok-window-web",
                                     description="이 컴퓨터의 브라우저에서 한옥 창호 CAD 패키지를 설계하고 생성합니다.")
    parser.add_argument("--output", type=Path, default=Path("output"),
                        help="패키지를 저장할 폴더 (기본 ./output, CLI build와 같은 형식)")
    parser.add_argument("--port", type=int, default=8765, help="127.0.0.1에서 열 포트 (기본 8765, 0이면 빈 포트)")
    parser.add_argument("--workers", type=int, default=2, help="동시에 실행할 생성 작업 수 (1–8, 기본 2)")
    parser.add_argument("--open", action="store_true", help="서버를 연 뒤 기본 브라우저로 엽니다")
    parser.add_argument("--verbose", action="store_true", help="성공한 요청도 기록합니다")
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port는 0–65535 사이여야 합니다.")
    if not 1 <= args.workers <= 8:
        parser.error("--workers는 1–8 사이여야 합니다.")
    try:
        server = make_server(args.output, port=args.port, workers=args.workers, verbose=args.verbose)
    except OSError as exc:
        print(f"127.0.0.1:{args.port} 포트를 열 수 없습니다: {exc.strerror or exc}", file=sys.stderr)
        return 1
    url = f"http://127.0.0.1:{server.port}/"
    print(f"한옥 창호 생성기  {url}\n출력 폴더        {server.service.root}\n끝내려면 Ctrl+C", flush=True)
    if args.open:
        webbrowser.open(url)
    # `./web.sh stop` and `kill` send SIGTERM: shut down exactly as for Ctrl+C.
    signal.signal(signal.SIGTERM, _interrupt)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n종료합니다. 진행 중인 생성은 끝날 때까지 기다리고(작업당 최대 120초) 대기 중인 생성은 취소합니다.",
              flush=True)
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
