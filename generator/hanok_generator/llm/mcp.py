"""Model Context Protocol server over stdio, written with the standard library only.

An MCP client (Claude, Cursor, VS Code, Gemini CLI and others) starts this process and speaks
JSON-RPC 2.0 over stdin and stdout, one message per line. Only protocol messages go to stdout;
anything else is sent to stderr. Tool calls run on worker threads, so ping and tools/list are
answered while a build runs. A client that sends a progressToken hears the stages of a build,
and the reply to a cancelled call is dropped (a build already running still completes).
"""
from __future__ import annotations

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
import threading

from ..web.service import app_version
from .tools import Toolbox

# Newest first. A client asking for another version gets the newest, and may then disconnect.
PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
STRUCTURED_SINCE = "2025-06-18"  # structuredContent in tool results; ISO dates compare as strings
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS, INTERNAL_ERROR = -32700, -32600, -32601, -32602, -32603
TOOL_THREADS = 4  # tool calls at once; each build also runs in a worker process of its own
INSTRUCTIONS = (
    "Designs traditional Korean (hanok) lattice windows and builds CNC packages. Call describe_generator once, then "
    "check_design with a request. If it names a rule, apply one value from its suggestion (or follow its hint) and "
    "check again, then build_package. Look at results with get_drawing, get_package and read_package_file. Sizes are "
    "millimetres as [width, height]; lattice_per_leaf is [vertical, horizontal] bars per leaf. The checks are "
    "nominal CAD geometry only: fit tolerances, hardware and CAM stay PENDING, so tell the user that a package needs "
    "trial cuts before machining.")


class ProtocolError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def error(ident, code, message):
    return {"jsonrpc": "2.0", "id": ident, "error": {"code": code, "message": message}}


class Server:
    def __init__(self, toolbox, stdout):
        self.toolbox = toolbox
        self.version = PROTOCOL_VERSIONS[0]
        self._stdout = stdout
        self._write_lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._running = {}  # request id -> Future of a tool call on a worker thread
        self._cancelled = set()
        self._pool = ThreadPoolExecutor(max_workers=TOOL_THREADS, thread_name_prefix="hanok-mcp")

    def send(self, message):
        data = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        with self._write_lock:
            self._stdout.write(data)
            self._stdout.flush()

    def receive(self, message):
        """Act on one line of input: a message, or a batch (2025-03-26), whose calls are answered together."""
        if isinstance(message, list):
            replies = [r for r in map(self.handle, message) if r is not None] if message else \
                [error(None, INVALID_REQUEST, "Invalid Request")]
            if replies:
                self.send(replies)
        elif isinstance(message, dict) and message.get("jsonrpc") == "2.0" and message.get("method") == "tools/call" \
                and "id" in message:
            self.submit(message)
        else:
            reply = self.handle(message)
            if reply is not None:
                self.send(reply)

    def handle(self, message):
        """The reply to one JSON-RPC message, or None for a notification or a stray reply."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST, "Invalid Request")
        method, ident = message.get("method"), message.get("id")
        if not isinstance(method, str):
            # A reply to a request of ours; this server sends none, so there is nothing to match.
            return None if "result" in message or "error" in message else error(ident, INVALID_REQUEST, "Invalid Request")
        params = message.get("params") or {}
        if "id" not in message:  # notifications
            if method == "notifications/cancelled" and isinstance(params, dict):
                self.cancel(params.get("requestId"))
            return None
        try:
            if not isinstance(params, dict):
                raise ProtocolError(INVALID_PARAMS, "params must be an object")
            if method == "initialize":
                result = self.initialize(params)
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": self.toolbox.definitions("mcp")}
            elif method == "tools/call":
                result = self.result(*self.checked(params))
            else:
                raise ProtocolError(METHOD_NOT_FOUND, f"Method not found: {method}")
        except ProtocolError as exc:
            return error(ident, exc.code, str(exc))
        except Exception as exc:  # keep serving; the client learns what failed
            return error(ident, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def initialize(self, params):
        asked = params.get("protocolVersion")
        self.version = asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0]
        return {"protocolVersion": self.version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "hanok-window", "title": "Hanok window generator",
                               "version": app_version() or "unknown"},
                "instructions": INSTRUCTIONS}

    def checked(self, params):
        """(tool name, arguments) of a tools/call, or ProtocolError for an unknown tool or bad arguments."""
        if not isinstance(params, dict):
            raise ProtocolError(INVALID_PARAMS, "params must be an object")
        name, arguments = params.get("name"), params.get("arguments")
        if not isinstance(name, str) or name not in self.toolbox.tools:
            raise ProtocolError(INVALID_PARAMS, f"Unknown tool: {name}")
        if arguments is not None and not isinstance(arguments, dict):
            raise ProtocolError(INVALID_PARAMS, "arguments must be an object")
        return name, arguments or {}

    def result(self, name, arguments, progress=None):
        outcome = self.toolbox.call(name, arguments, progress=progress)
        content = [{"type": "text", "text": json.dumps(outcome.data, ensure_ascii=False)}]
        content += [{"type": "image", "mimeType": mime, "data": base64.b64encode(data).decode("ascii")}
                    for mime, data in outcome.images]
        result = {"content": content, "isError": outcome.is_error}
        if self.version >= STRUCTURED_SINCE:
            result["structuredContent"] = outcome.data
        return result

    def submit(self, message):
        """Run a tools/call on a worker thread; reply when it ends, unless it was cancelled meanwhile."""
        ident, params = message["id"], message.get("params") or {}
        try:
            name, arguments = self.checked(params)
        except ProtocolError as exc:
            self.send(error(ident, exc.code, str(exc)))
            return
        meta = params.get("_meta")
        token = meta.get("progressToken") if isinstance(meta, dict) else None

        def progress(done, total, text):
            if ident not in self._cancelled:
                self.send({"jsonrpc": "2.0", "method": "notifications/progress",
                           "params": {"progressToken": token, "progress": done, "total": total, "message": text}})

        def run():
            try:
                reply = {"jsonrpc": "2.0", "id": ident,
                         "result": self.result(name, arguments, progress if token is not None else None)}
            except Exception as exc:
                reply = error(ident, INTERNAL_ERROR, f"{type(exc).__name__}: {exc}")
            with self._state_lock:
                self._running.pop(ident, None)
                dropped = ident in self._cancelled
                self._cancelled.discard(ident)
            if not dropped:
                self.send(reply)

        with self._state_lock:
            self._running[ident] = self._pool.submit(run)

    def cancel(self, ident):
        """notifications/cancelled: drop the reply; a call that has not started never runs."""
        with self._state_lock:
            future = self._running.get(ident) if isinstance(ident, (str, int)) else None
            if future is None:
                return  # finished already, or never ours: nothing to do
            self._cancelled.add(ident)
            if future.cancel():
                self._running.pop(ident, None)
                self._cancelled.discard(ident)

    def close(self):
        """Wait for running calls, so their replies still go out, then stop the worker threads."""
        self._pool.shutdown(wait=True)


def serve(server, stdin):
    """Read stdin line by line until it closes, then let the running tool calls finish."""
    try:
        for raw in stdin:
            if not raw.strip():
                continue
            try:
                message = json.loads(raw)
            except ValueError:  # also invalid UTF-8
                server.send(error(None, PARSE_ERROR, "Parse error"))
                continue
            server.receive(message)
    finally:
        server.close()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="hanok-window-mcp",
                                     description="LLM 클라이언트가 한옥 창호 생성기 도구를 쓰도록 MCP 서버(stdio)를 엽니다.")
    parser.add_argument("--output", type=Path, default=Path(os.environ.get("HANOK_WINDOW_OUTPUT", "output")),
                        help="패키지 폴더 (기본 ./output 또는 HANOK_WINDOW_OUTPUT). MCP 클라이언트는 작업 폴더가 "
                             "정해져 있지 않으니 절대 경로를 쓰세요")
    parser.add_argument("--timeout", type=int, default=120, help="생성 한 건의 제한 시간(초, 기본 120)")
    args = parser.parse_args(argv)
    stdout = sys.stdout.buffer
    sys.stdout = sys.stderr  # a stray print must not corrupt the protocol stream
    server = Server(Toolbox(args.output, timeout=args.timeout), stdout)
    try:
        serve(server, sys.stdin.buffer)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
