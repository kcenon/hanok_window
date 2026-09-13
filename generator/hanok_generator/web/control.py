"""Keep the web server running in the background: ``./web.sh start|stop|restart|status|log``.

``start`` launches ``python -m hanok_generator.web`` in a session of its own, so closing the
terminal leaves it running, and returns once the server answers. The server inherits a locked
descriptor of ``<output>/.web/server.json`` and holds that lock until it exits, so the pid in
the record is trusted only while the lock is held: a record left behind by a crash or a reboot
never gets a signal, and no process listing is needed (the BSD pidfile(3) approach). ``stop``
sends SIGTERM, which the server handles like Ctrl+C. POSIX only (fcntl).
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import http.client
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import urllib.request
import webbrowser

DEFAULT_PORT = 8765
READY_S = 20  # a new server answers in about a second
STOP_S = 150  # running builds finish first, each within its 120 s job limit


def home(port):
    return f"http://127.0.0.1:{port}/"


def answers(port, timeout=1.0):
    """True when a web interface answers on 127.0.0.1:port (asked directly, never through a proxy)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(home(port) + "api/meta", timeout=timeout) as response:
            return response.status == 200
    except (OSError, http.client.HTTPException):
        return False


def shown(path):
    """The path from the working folder when inside it (web.sh runs from generator/)."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)


def pid_of(record):
    return f"(pid {record['pid']})" if record.get("pid") else ""


class Record:
    """The server start launched for one output folder: <output>/.web/server.json and server.log."""

    def __init__(self, output):
        self.output = Path(output).resolve()
        self.folder = self.output / ".web"
        self.path = self.folder / "server.json"
        self.log = self.folder / "server.log"

    def inspect(self):
        """(held, record): whether a live server holds the lock, and what the record says."""
        try:
            file = open(self.path, "rb")
        except FileNotFoundError:
            return False, None
        with file:
            try:
                fcntl.flock(file, fcntl.LOCK_SH | fcntl.LOCK_NB)
                held = False
            except BlockingIOError:
                held = True
            try:
                record = json.loads(file.read())
            except ValueError:  # emptied by stop, or read while start writes it
                record = None
        if not isinstance(record, dict):
            record = {} if held else None
        return held, record

    def running(self):
        """The record while its server is alive, else None."""
        held, record = self.inspect()
        return record if held else None

    def forget(self):
        """Empty the record unless a server holds it."""
        try:
            file = open(self.path, "r+b")
        except FileNotFoundError:
            return
        with file:
            try:
                fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            file.truncate(0)

    def launch(self, port):
        """Start the server with the record's lock; None if another start holds the lock right now."""
        self.folder.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return None
            with open(self.log, "wb") as log:
                child = subprocess.Popen(
                    [sys.executable, "-m", "hanok_generator.web", "--output", str(self.output), "--port", str(port)],
                    stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                    start_new_session=True, pass_fds=(fd,))
            os.ftruncate(fd, 0)
            os.pwrite(fd, json.dumps(dict(pid=child.pid, port=port)).encode(), 0)
            return child
        finally:
            os.close(fd)  # the server's inherited copy keeps the lock until it exits

    def tail(self, lines):
        try:
            return self.log.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:]
        except FileNotFoundError:
            return None


def other_server(port):
    """Mention a server on the port that has no record here, e.g. one started by hand."""
    if answers(port):
        print(f"다만 127.0.0.1:{port}에서 이 기록에 없는 서버가 응답합니다. "
              "직접 켠 서버라면 그 터미널에서 Ctrl+C로 끄세요.")


def wait_ready(child, port):
    """None once the new server answers, else what went wrong."""
    deadline = time.monotonic() + READY_S
    while time.monotonic() < deadline:
        if child.poll() is not None:
            return "서버를 켜지 못했습니다."
        if answers(port):
            return None
        time.sleep(0.2)
    child.terminate()
    try:
        child.wait(timeout=10)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait()
    return f"서버가 {READY_S}초 안에 응답하지 않아 멈췄습니다."


def start(record, port, open_browser):
    current = record.running()
    if current is None:
        if answers(port):
            print(f"127.0.0.1:{port}에서 이미 다른 서버가 응답합니다. "
                  "직접 켠 서버라면 그 터미널에서 Ctrl+C로 끄거나 --port로 다른 포트를 쓰세요.", file=sys.stderr)
            return 1
        child = record.launch(port)
        if child is None:  # a start run at the same moment got the lock first
            time.sleep(0.5)
            return start(record, port, open_browser)
        problem = wait_ready(child, port)
        if problem:
            print(f"{problem} 서버 기록 {shown(record.log)}의 마지막 줄:", file=sys.stderr)
            for line in record.tail(20) or []:
                print(f"  {line}", file=sys.stderr)
            record.forget()
            return 1
        print(f"켜졌습니다: {home(port)}\n끄려면 ./web.sh stop (Finder에서는 web-stop.command)")
    else:
        port = current.get("port", port)
        print(f"이미 켜져 있습니다: {home(port)} {pid_of(current)}".rstrip())
    if open_browser and not webbrowser.open_new_tab(home(port)):
        print("브라우저를 열지 못했습니다. 위 주소를 직접 여세요.", file=sys.stderr)
    return 0


def stop(record, port):
    current = record.running()
    if current is None:
        record.forget()
        print("꺼져 있습니다.")
        other_server(port)
        return 0
    pid = current.get("pid")
    if not pid:
        print("서버를 켜는 중입니다. 잠시 뒤 다시 하세요.", file=sys.stderr)
        return 1
    with contextlib.suppress(ProcessLookupError):
        os.kill(pid, signal.SIGTERM)
    began, told = time.monotonic(), False
    while record.running() is not None:
        waited = time.monotonic() - began
        if waited > STOP_S:
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
            while record.running() is not None and time.monotonic() - began < STOP_S + 5:
                time.sleep(0.1)
            record.forget()
            print(f"{STOP_S}초 안에 끝나지 않아 강제로 껐습니다. 서버 기록: {shown(record.log)}", file=sys.stderr)
            return 1
        if waited > 1 and not told:
            print("진행 중인 생성이 끝나기를 기다립니다(작업당 최대 120초)…", flush=True)
            told = True
        time.sleep(0.1)
    record.forget()
    print("껐습니다.")
    return 0


def restart(record, port, open_browser):
    if port is None:
        port = (record.running() or {}).get("port", DEFAULT_PORT)
    return stop(record, port) or start(record, port, open_browser)


def status(record, port):
    held, current = record.inspect()
    if held:
        port = current.get("port", port)
        if answers(port, timeout=2):
            print(f"켜져 있습니다: {home(port)} {pid_of(current)}".rstrip())
            return 0
        print(f"켜져 있지만 응답하지 않습니다{pid_of(current)}. 서버 기록: {shown(record.log)}")
        return 1
    if current:
        print(f"꺼져 있습니다. 지난번 서버{pid_of(current)}는 ./web.sh stop 없이 끝났습니다. "
              f"서버 기록: {shown(record.log)}")
    else:
        print("꺼져 있습니다.")
    other_server(port)
    return 3


def show_log(record, lines):
    tail = record.tail(lines)
    if tail is None:
        print(f"서버 기록이 없습니다: {shown(record.log)}", file=sys.stderr)
        return 1
    print("\n".join(tail))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="web.sh", description="한옥 창호 웹 화면 서버를 백그라운드에서 켜고 끕니다.")
    commands = parser.add_subparsers(dest="command", metavar="명령")
    with_output = argparse.ArgumentParser(add_help=False)
    with_output.add_argument("--output", type=Path, default=Path("output"),
                             help="패키지 폴더 (기본 ./output). 서버 기록은 그 안의 .web/에 둡니다")
    with_port = argparse.ArgumentParser(add_help=False)
    with_port.add_argument("--port", type=int, help=f"127.0.0.1의 포트 (기본 {DEFAULT_PORT})")
    with_browser = argparse.ArgumentParser(add_help=False)
    with_browser.add_argument("--no-open", action="store_true", help="브라우저를 열지 않습니다")
    commands.add_parser("start", parents=[with_output, with_port, with_browser], help="켜고 기본 브라우저로 엽니다")
    commands.add_parser("stop", parents=[with_output, with_port], help="끕니다. 진행 중인 생성은 끝까지 기다립니다")
    commands.add_parser("restart", parents=[with_output, with_port, with_browser],
                        help="껐다가 다시 켭니다 (--port가 없으면 쓰던 포트)")
    commands.add_parser("status", parents=[with_output, with_port], help="켜짐 0, 응답 없음 1, 꺼짐 3으로 끝납니다")
    logs = commands.add_parser("log", parents=[with_output], help="서버 기록의 마지막 줄을 보여 줍니다")
    logs.add_argument("--lines", type=int, default=40, help="보여 줄 줄 수 (기본 40)")
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if getattr(args, "port", None) is not None and not 1 <= args.port <= 65535:
        parser.error("--port는 1–65535 사이여야 합니다.")
    record = Record(args.output)
    try:
        if args.command == "start":
            return start(record, args.port or DEFAULT_PORT, not args.no_open)
        if args.command == "stop":
            return stop(record, args.port or DEFAULT_PORT)
        if args.command == "restart":
            return restart(record, args.port, not args.no_open)
        if args.command == "status":
            return status(record, args.port or DEFAULT_PORT)
        return show_log(record, max(args.lines, 1))
    except KeyboardInterrupt:
        print("\n중단했습니다.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
