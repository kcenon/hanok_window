"""Loopback HTTP server: routes, request limits, security headers and static files."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
import json
from pathlib import PurePosixPath
import re
import socketserver
import traceback
from urllib.parse import unquote, urlsplit

from ..jobs import run_job
from ..package import PackageError
from .builds import BuildQueue, QueueFull
from .service import Service, failure

MAX_BODY = 64 * 1024
LOOPBACK_NAMES = ("127.0.0.1", "localhost", "[::1]")
CSP = ("default-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; "
       "form-action 'none'; frame-ancestors 'none'")
SECURITY_HEADERS = (("Content-Security-Policy", CSP), ("X-Content-Type-Options", "nosniff"),
                    ("Referrer-Policy", "no-referrer"), ("X-Frame-Options", "DENY"),
                    ("Cross-Origin-Opener-Policy", "same-origin"),
                    ("Cross-Origin-Resource-Policy", "same-origin"))
# A package id is the hash of its files, so the same URL can never name other bytes.
IMMUTABLE = "private, max-age=31536000, immutable"
FILE_TYPES = {".png": "image/png", ".json": "application/json; charset=utf-8", ".csv": "text/csv; charset=utf-8",
              ".txt": "text/plain; charset=utf-8", ".py": "text/plain; charset=utf-8", ".dxf": "application/dxf"}
# A fixed list: a request path is never joined onto a file system path.
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/preview.js": ("preview.js", "text/javascript; charset=utf-8"),
          "/packages.js": ("packages.js", "text/javascript; charset=utf-8"),
          "/messages.js": ("messages.js", "text/javascript; charset=utf-8")}
# (method, full-match path pattern, handler method); captured groups become arguments.
ROUTES = [(method, re.compile(pattern), name) for method, pattern, name in (
    ("GET", r"/api/meta", "get_meta"),
    ("POST", r"/api/preview", "post_preview"),
    ("POST", r"/api/builds", "post_build"),
    ("GET", r"/api/builds/([0-9a-f]{32})", "get_build"),
    ("GET", r"/api/packages", "get_packages"),
    ("GET", r"/api/packages/([0-9a-f]{64})", "get_package"),
    ("GET", r"/api/packages/([0-9a-f]{64})/verify", "get_verify"),
    ("GET", r"/thumbs/([0-9a-f]{64})/([0-9a-z_]+\.png)", "get_thumb"),
    ("GET", r"/files/([0-9a-f]{64})\.zip", "get_zip"),
    ("GET", r"/files/([0-9a-f]{64})/(.+)", "get_file"),
)]


class HttpError(Exception):
    def __init__(self, status, rule_id, message, headers=(), **details):
        super().__init__(message)
        self.status, self.headers = status, headers
        self.body = failure(rule_id, message, details)


def found(value):
    if value is None:
        raise HttpError(404, "http.not_found", "없는 패키지나 파일입니다.")
    return value


class Handler(BaseHTTPRequestHandler):
    server_version = "hanok-window-web"
    sys_version = ""
    timeout = 30  # a stalled client cannot hold a handler thread forever
    body_read = False

    def do_GET(self):
        try:
            self.check_host()
            self.check_origin()
            self.route(urlsplit(self.path).path, "GET" if self.command == "HEAD" else self.command)
        except HttpError as exc:
            self.send_json(exc.status, exc.body, exc.headers)
        except PackageError as exc:
            self.send_json(409, failure("package.integrity", "패키지 파일이 매니페스트와 다릅니다. 무결성 확인을 실행하세요.",
                                        {"reason": str(exc)}))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception:
            self.log_error("%s", traceback.format_exc())
            self.send_json(500, failure("server.error", "서버 내부 오류입니다. 서버를 실행한 창의 기록을 확인하세요."))

    do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_GET

    def route(self, path, method):
        allowed = set()
        for route_method, pattern, name in ROUTES:
            match = pattern.fullmatch(path)
            if match:
                if route_method == method:
                    return getattr(self, name)(*match.groups())
                allowed.add(route_method)
        if path in STATIC:
            if method == "GET":
                return self.send_static(*STATIC[path])
            allowed.add("GET")
        if allowed:
            raise HttpError(405, "http.method", "이 주소에서 허용하지 않는 요청 방식입니다.",
                            headers=[("Allow", ", ".join(sorted(allowed)))])
        raise HttpError(404, "http.not_found", "없는 주소입니다.")

    def check_host(self):
        # DNS rebinding: a hostile page can reach 127.0.0.1 under its own name only.
        host = (self.headers.get("Host") or "").strip().lower()
        if host not in self.server.allowed_hosts:
            raise HttpError(421, "http.host", "이 서버는 127.0.0.1 또는 localhost 주소로만 접속합니다.", host=host[:200])

    def check_origin(self):
        origin = self.headers.get("Origin")
        if origin is not None and origin.strip().lower() != "http://" + self.headers["Host"].strip().lower():
            raise HttpError(403, "http.origin", "다른 사이트에서 보낸 요청은 받지 않습니다.", origin=origin[:200])

    def read_json(self):
        # Only application/json: a cross-site form cannot send it without a CORS preflight,
        # and this server never answers one.
        kind = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if kind != "application/json":
            raise HttpError(415, "http.content_type", "요청 본문은 application/json이어야 합니다.")
        length = self.headers.get("Content-Length", "")
        if not length.isdigit():
            raise HttpError(411, "http.length_required", "Content-Length가 필요합니다.")
        if int(length) > MAX_BODY:
            raise HttpError(413, "input.too_large", "입력 JSON은 64 KiB 이하로 제한합니다.", limit=MAX_BODY)
        raw = self.rfile.read(int(length))
        self.body_read = True

        def constant(value):
            raise HttpError(400, "input.number", "NaN과 Infinity는 사용할 수 없습니다.", value=value)
        try:
            return json.loads(raw.decode("utf-8"), parse_constant=constant)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
            raise HttpError(400, "input.json", "요청 본문이 올바른 JSON이 아닙니다.") from exc

    def drain(self):
        """Read an unread body (bounded) so the client gets the error before the socket closes."""
        if self.body_read:
            return
        self.body_read = True
        length = self.headers.get("Content-Length", "") if self.headers else ""
        if length.isdigit() and 0 < int(length) <= 1 << 20:
            try:
                self.rfile.read(int(length))
            except OSError:
                pass

    def end_headers(self):
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        super().end_headers()

    def send_bytes(self, status, data, content_type, headers=(), cache="no-store"):
        if status >= 400:
            self.drain()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_json(self, status, body, headers=()):
        data = json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_bytes(status, data, "application/json; charset=utf-8", headers)

    def send_static(self, name, content_type):
        try:
            data = files(__package__).joinpath("static", name).read_bytes()
        except OSError:
            raise HttpError(404, "http.not_found", "화면 파일이 없습니다.", file=name) from None
        self.send_bytes(200, data, content_type, cache="no-cache")

    def log_request(self, code="-", size="-"):
        value = getattr(code, "value", code)
        if self.server.verbose or not (isinstance(value, int) and value < 400):
            super().log_request(code, size)

    def get_meta(self):
        self.send_json(200, self.server.service.meta())

    def post_preview(self):
        status, body = self.server.service.preview(self.read_json())
        self.send_json(status, body)

    def post_build(self):
        data = self.read_json()
        status, checked = self.server.service.preview(data)
        if status != 200:
            return self.send_json(status, checked)  # the build would stop at the same rule
        try:
            record = self.server.builds.submit(data)
        except QueueFull as exc:
            raise HttpError(429, "build.queue_full", "생성 대기열이 가득 찼습니다. 진행 중인 생성이 끝난 뒤 다시 시도하세요.",
                            headers=[("Retry-After", "5")], limit=exc.args[0]) from None
        self.send_json(202, record, [("Location", f"/api/builds/{record['build_id']}")])

    def get_build(self, build_id):
        record = self.server.builds.status(build_id)
        if record is None:
            raise HttpError(404, "build.not_found", "생성 기록이 없습니다. 서버를 다시 켜면 진행 기록은 사라지고 패키지만 남습니다.")
        self.send_json(200, record)

    def get_packages(self):
        self.send_json(200, self.server.service.packages())

    def get_package(self, package_id):
        self.send_json(200, found(self.server.service.package(package_id)))

    def get_verify(self, package_id):
        self.send_json(200, found(self.server.service.verify(package_id)))

    def get_file(self, package_id, name):
        data, filename = found(self.server.service.package_file(package_id, unquote(name)))
        kind = FILE_TYPES.get(PurePosixPath(filename).suffix, "application/octet-stream")
        disposition = "inline" if kind == "image/png" else "attachment"
        self.send_bytes(200, data, kind, [("Content-Disposition", f'{disposition}; filename="{filename}"')],
                        cache=IMMUTABLE)

    def get_thumb(self, package_id, name):
        self.send_bytes(200, found(self.server.service.thumbnail(package_id, name)), "image/png", cache=IMMUTABLE)

    def get_zip(self, package_id):
        data, filename = found(self.server.service.package_zip(package_id))
        self.send_bytes(200, data, "application/zip", [("Content-Disposition", f'attachment; filename="{filename}"')],
                        cache=IMMUTABLE)


class WebServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, service, builds, *, port=8765, verbose=False):
        # Loopback only: there is no login, so the server is never reachable from the network.
        super().__init__(("127.0.0.1", port), Handler)
        self.service, self.builds, self.verbose = service, builds, verbose
        self.port = self.server_address[1]
        self.allowed_hosts = {f"{name}:{self.port}" for name in LOOPBACK_NAMES}
        if self.port == 80:
            self.allowed_hosts.update(LOOPBACK_NAMES)

    def server_bind(self):
        # HTTPServer.server_bind() also sets server_name from socket.getfqdn(host). On the GitHub macOS runner
        # that reverse lookup of 127.0.0.1 takes over 30 s per process, and nothing here reads server_name.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def close(self):
        """Refuse new connections, then wait for running builds and cancel waiting ones."""
        self.server_close()
        self.builds.shutdown()


def make_server(output, *, port=8765, workers=2, waiting=8, runner=run_job, verbose=False):
    service = Service(output)
    builds = BuildQueue(service.root, workers=workers, waiting=waiting, runner=runner)
    return WebServer(service, builds, port=port, verbose=verbose)
