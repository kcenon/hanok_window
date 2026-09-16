"""Remake the pictures of the user manual (docs/manual/images/).

Builds the example designs into a temporary output folder, serves them with the local web
server in this process, drives headless Chrome over the DevTools protocol to photograph each
screen, and saves reduced copies of the R3 package drawings. The real output folder is never
touched. Needs Google Chrome or Chromium; uses only the standard library and Pillow, which the
generator already depends on. Nothing here is part of a package, so package ids do not change.
Chrome is driven over a DevTools port (macOS, Linux and Windows alike), so no file descriptor is
handed to the child process.

    cd generator
    .venv/bin/python docs/manual/make_images.py
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
from pathlib import Path
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.parse

from PIL import Image

from hanok_generator.jobs import run_job
from hanok_generator.package import PNG_FILES
from hanok_generator.web.server import make_server

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent.parent / "examples"
CHROMES = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "google-chrome-stable",
           "chromium", "chromium-browser")
WIDTH, HEIGHT, SCALE = 1280, 1000, 2  # CSS viewport and device pixel ratio of every screenshot
FULL_WIDTH = 1920  # whole-screen shots are reduced to this many pixels across
DRAWING_WIDTH = 1200
DRAWINGS = dict(zip(("nesting", "joinery", "assembly", "opening", "pockets"), PNG_FILES))
DESIGN_READY = "document.querySelector('#panel-elev svg') && !document.getElementById('build').disabled"
PACKAGE_READY = ("!document.getElementById('pkg-body').hidden"
                 " && document.getElementById('pkg-integrity')?.textContent.includes('파일')"
                 " && [...document.querySelectorAll('#pkg-thumbs img')].every((i) => i.complete && i.naturalWidth)")
VISIBLE_ERRORS = "[...document.querySelectorAll('[id^=\"err-\"]')].filter((e) => !e.hidden && e.textContent.trim())"


class Wire:
    """One WebSocket connection to a DevTools endpoint, with the little of RFC 6455 it needs.

    Client frames are masked and server frames are not, so only masking is implemented here;
    a message may arrive in several frames, and the server may ping while a screenshot is
    being encoded.
    """

    def __init__(self, url, timeout=120):
        parsed = urllib.parse.urlparse(url)
        self.sock = socket.create_connection((parsed.hostname, parsed.port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {parsed.path} HTTP/1.1\r\n"
                           f"Host: {parsed.hostname}:{parsed.port}\r\n"
                           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        self.buffer = b""
        head = self._until(b"\r\n\r\n")
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise RuntimeError(f"DevTools refused the WebSocket upgrade: {head[:120]!r}")

    def _recv(self):
        chunk = self.sock.recv(1 << 16)
        if not chunk:
            raise EOFError("Chrome closed the DevTools connection")
        self.buffer += chunk

    def _until(self, marker):
        while marker not in self.buffer:
            self._recv()
        head, self.buffer = self.buffer.split(marker, 1)
        return head

    def _take(self, count):
        while len(self.buffer) < count:
            self._recv()
        data, self.buffer = self.buffer[:count], self.buffer[count:]
        return data

    def _frame(self, opcode, payload):
        mask = os.urandom(4)
        header = bytearray([0x80 | opcode])
        size = len(payload)
        if size < 126:
            header.append(0x80 | size)
        elif size < 1 << 16:
            header.append(0x80 | 126)
            header += struct.pack(">H", size)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", size)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def send(self, text):
        self._frame(0x1, text.encode())

    def receive(self):
        """The next text message, joined from its frames. Pings are answered on the way."""
        parts = []
        while True:
            first, second = self._take(2)
            final, opcode, size = first & 0x80, first & 0x0F, second & 0x7F
            if size == 126:
                size = struct.unpack(">H", self._take(2))[0]
            elif size == 127:
                size = struct.unpack(">Q", self._take(8))[0]
            payload = self._take(size)
            if opcode == 0x9:  # ping
                self._frame(0xA, payload)
                continue
            if opcode == 0xA:  # pong
                continue
            if opcode == 0x8:
                raise EOFError("Chrome closed the DevTools connection")
            parts.append(payload)
            if final:
                return b"".join(parts).decode("utf-8")

    def close(self):
        try:
            self._frame(0x8, b"")
        except OSError:
            pass
        self.sock.close()


class Chrome:
    """Headless Chrome over a DevTools port: JSON commands and replies on one WebSocket.

    --remote-debugging-pipe would need preexec_fn and pass_fds, which POSIX has and Windows does
    not, so the port Chrome writes to DevToolsActivePort is used on every platform instead.
    """

    def __init__(self, binary):
        self.profile = tempfile.TemporaryDirectory(prefix="hanok-manual-chrome-")
        self.proc = subprocess.Popen(
            [binary, "--headless=new", "--remote-debugging-port=0", "--use-mock-keychain",
             "--password-store=basic", "--no-first-run", "--no-default-browser-check",
             "--disable-extensions", "--disable-gpu", "--hide-scrollbars",
             f"--user-data-dir={self.profile.name}", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.wire, self.next_id = Wire(self._endpoint()), 0

    def _endpoint(self, timeout=60):
        """Chrome writes the port it took and the browser path to DevToolsActivePort."""
        path = Path(self.profile.name) / "DevToolsActivePort"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f"Chrome exited with {self.proc.returncode} before opening a DevTools port")
            try:
                port, browser = path.read_text(encoding="utf-8").splitlines()[:2]
                return f"ws://127.0.0.1:{port}{browser}"
            except (OSError, ValueError):
                time.sleep(0.05)
        raise TimeoutError("Chrome did not write DevToolsActivePort")

    def send(self, method, params=None, session=None):
        self.next_id += 1
        message = {"id": self.next_id, "method": method, "params": params or {}}
        if session:
            message["sessionId"] = session
        self.wire.send(json.dumps(message))
        while True:
            reply = json.loads(self.wire.receive())
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def close(self):
        try:
            self.send("Browser.close")
        except (EOFError, OSError, RuntimeError):
            pass
        self.wire.close()
        try:
            self.proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.profile.cleanup()


class Page:
    """One tab in its own browser context, so no saved draft carries over from another page."""

    def __init__(self, chrome, url, ready):
        self.chrome = chrome
        context = chrome.send("Target.createBrowserContext")["browserContextId"]
        target = chrome.send("Target.createTarget", {"url": "about:blank", "browserContextId": context})["targetId"]
        self.session = chrome.send("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        self.call("Page.enable")
        self.call("Runtime.enable")
        self.call("Emulation.setDeviceMetricsOverride",
                  {"width": WIDTH, "height": HEIGHT, "deviceScaleFactor": SCALE, "mobile": False})
        self.call("Emulation.setEmulatedMedia", {"features": [{"name": "prefers-color-scheme", "value": "light"}]})
        self.call("Page.navigate", {"url": url})
        self.wait(ready)

    def call(self, method, params=None):
        return self.chrome.send(method, params, self.session)

    def js(self, expression):
        result = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True, "awaitPromise": True})
        if "exceptionDetails" in result:
            raise RuntimeError(result["exceptionDetails"].get("exception", {}).get("description", "script error"))
        return result["result"].get("value")

    def wait(self, condition, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if self.js(f"document.readyState === 'complete' && !!({condition})"):
                    time.sleep(0.3)  # let the last paint land
                    return
            except RuntimeError:
                pass
            time.sleep(0.1)
        raise TimeoutError(f"not ready: {condition}")

    def click(self, selector):
        self.js(f"document.querySelector({json.dumps(selector)}).click(); true")

    def type(self, element_id, value):
        """Set a field the way typing does, then give the 150 ms pre-check time to start."""
        self.js(f"(() => {{ const el = document.getElementById({json.dumps(element_id)}); el.value = {json.dumps(value)};"
                " el.dispatchEvent(new Event('input', {bubbles: true})); return true; })()")
        time.sleep(0.5)

    def key(self, key):
        self.js(f"document.getElementById('viewer').dispatchEvent(new KeyboardEvent('keydown', {{key: {json.dumps(key)},"
                " bubbles: true})); true")

    def capture(self):
        data = self.call("Page.captureScreenshot", {"format": "png"})["data"]
        return Image.open(io.BytesIO(base64.b64decode(data)))

    def crop(self, *selectors, margin=10):
        """The viewport cut to the box around the elements, after scrolling the first one to the top."""
        self.js(f"document.querySelector({json.dumps(selectors[0])}).scrollIntoView({{block: 'start', behavior: 'instant'}});"
                " window.scrollBy(0, -16); true")
        time.sleep(0.2)
        boxes = [self.js(f"(() => {{ const r = document.querySelector({json.dumps(s)}).getBoundingClientRect();"
                         " return [r.left, r.top, r.right, r.bottom]; })()") for s in selectors]
        left, top = min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin
        right, bottom = max(b[2] for b in boxes) + margin, max(b[3] for b in boxes) + margin
        image = self.capture()
        box = (max(0, left), max(0, top), min(WIDTH, right), min(HEIGHT, bottom))
        return image.crop(tuple(round(v * SCALE) for v in box))

    def top(self, selector, margin=24):
        """The whole width of the viewport, from the top down to just below the element."""
        bottom = self.js(f"document.querySelector({json.dumps(selector)}).getBoundingClientRect().bottom")
        image = self.capture()
        return image.crop((0, 0, image.width, min(image.height, round((bottom + margin) * SCALE))))


def save(image, path, width=None):
    if width and image.width > width:
        image = image.resize((width, round(image.height * width / image.width)), Image.Resampling.LANCZOS)
    image.convert("RGB").save(path, "PNG", optimize=True)
    print(f"  {path.name}  {image.width} x {image.height}  {path.stat().st_size // 1024} KB")


def find_chrome(given):
    for candidate in ([given] if given else CHROMES):
        found = candidate if os.path.isabs(candidate) and os.access(candidate, os.X_OK) else shutil.which(candidate)
        if found:
            return found
    raise SystemExit("Chrome을 찾지 못했습니다. --chrome에 Chrome 또는 Chromium 실행 파일 경로를 주세요.")


def build_examples(output):
    """Every examples/*.json built the way the CLI builds it; returns {example name: package id}."""
    ids = {}
    for path in sorted(EXAMPLES.glob("*.json")):
        if path.name == "built_packages.json":
            continue
        ids[path.stem] = run_job(json.loads(path.read_text(encoding="utf-8")), output)["package_id"]
        print(f"  {path.stem}: {ids[path.stem][:12]}")
    return ids


def shoot(chrome, origin, r3, out):
    design = f"{origin}/#/design"
    p = Page(chrome, design, DESIGN_READY)
    save(p.capture(), out / "design.png", FULL_WIDTH)
    save(p.crop("#form"), out / "design-inputs.png")
    save(p.crop("aside.summary"), out / "design-summary.png")
    p.click("#tab-nest")
    p.wait("!document.getElementById('panel-nest').hidden && document.querySelector('#panel-nest svg')")
    save(p.crop("#preview-pane"), out / "design-nesting.png")

    p = Page(chrome, design, DESIGN_READY)
    p.click("#basis-inner")
    p.wait("document.getElementById('size-w').value === '383'")
    save(p.crop("#g-size"), out / "design-inner.png")

    p = Page(chrome, design, DESIGN_READY)  # the frame type: the panel is the size basis
    p.type("preset", "standard_4x8_v1")
    p.click("#basis-artwork")
    p.type("size-w", "420")
    p.type("size-h", "594")
    p.wait(f"!document.getElementById('g-artwork').hidden"
           " && document.querySelector('#panel-elev .mk-art')"
           f" && {DESIGN_READY}")
    save(p.crop("#g-size", "#g-artwork"), out / "design-artwork.png")
    save(p.crop("#preview-pane"), out / "design-artwork-preview.png")

    p = Page(chrome, design, DESIGN_READY)  # a single window shows the hinge side
    p.type("preset", "standard_v1")
    p.click("#type-single")
    p.click("#hinge-right")
    p.wait(f"!document.getElementById('hinge-row').hidden && document.getElementById('hinge-right').checked && {DESIGN_READY}")
    save(p.crop("#g-type"), out / "design-single.png")

    p = Page(chrome, design, DESIGN_READY)  # an R3 window too wide for its leaf ratio, with the suggested fix
    p.type("size-w", "600")
    p.wait(f"{VISIBLE_ERRORS}.some((e) => e.textContent.includes('473'))")
    shown = p.js(f"{VISIBLE_ERRORS}.map((e) => '#' + e.id)")
    save(p.crop("#g-size", *shown), out / "design-error.png")

    p = Page(chrome, design, DESIGN_READY)  # passes the pre-check, then fails the checks on the saved DXF
    p.type("lat-v", "9")
    p.type("lat-h", "30")
    p.wait("!document.getElementById('build').disabled")
    p.click("#build")
    p.wait("document.querySelector('.buildcard.fail')", timeout=150)
    save(p.crop("aside.summary"), out / "build-failed.png")

    p = Page(chrome, f"{origin}/#/packages", "document.querySelectorAll('#hist-rows tr').length >= 5")
    # Name the usual output folder rather than this run's temporary one.
    p.js("(() => { const n = document.getElementById('hist-note'); n.textContent = n.textContent.replace("
         r"/\S*hanok-manual-[^/]+\/output/, '…/hanok_window/generator/output'); return true; })()")
    save(p.top("#view-packages .pane"), out / "history.png", FULL_WIDTH)

    p = Page(chrome, f"{origin}/#/packages/{r3}", PACKAGE_READY)
    save(p.top("#view-package .pkg"), out / "package.png", FULL_WIDTH)
    save(p.crop("section[aria-labelledby='h-checks']"), out / "package-checks.png")
    save(p.crop("section[aria-labelledby='h-files']"), out / "package-files.png")
    p.js("window.scrollTo(0, 0); true")
    p.click("#pkg-thumbs .thumb:nth-of-type(3)")
    p.wait("document.getElementById('viewer').open && document.getElementById('viewer-img').complete"
           " && document.getElementById('viewer-zoom').textContent.endsWith('%')")
    p.key("+")
    time.sleep(0.4)
    save(p.capture(), out / "viewer.png", FULL_WIDTH)


def reduce_drawings(package, out):
    for name, file in DRAWINGS.items():
        with Image.open(package / file) as drawing:
            save(drawing, out / f"drawing-{name}.png", DRAWING_WIDTH)


def main(argv=None):
    parser = argparse.ArgumentParser(description="사용 설명서 그림(docs/manual/images/)을 다시 만듭니다.")
    parser.add_argument("--out", type=Path, default=HERE / "images", help="그림을 쓸 폴더 (기본 docs/manual/images)")
    parser.add_argument("--chrome", help="Chrome 또는 Chromium 실행 파일 (기본: 흔한 설치 위치에서 찾음)")
    args = parser.parse_args(argv)
    binary = find_chrome(args.chrome)
    args.out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="hanok-manual-") as tmp:
        output = Path(tmp) / "output"
        print("예제 생성:")
        ids = build_examples(output)
        chrome = Chrome(binary)
        server = make_server(output, port=0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            print("화면 촬영:")
            shoot(chrome, f"http://127.0.0.1:{server.port}", ids["double_r3"], args.out)
            print("도면 축소:")
            reduce_drawings(output / "packages" / ids["double_r3"], args.out)
        finally:
            chrome.close()
            server.shutdown()
            server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
