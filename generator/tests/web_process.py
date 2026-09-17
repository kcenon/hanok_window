"""Real foreground CLI processes, including Ctrl+C in a private Windows console."""
from __future__ import annotations

import contextlib
import http.client
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time


def process_options():
    """Isolate signals from the runner; keep Windows console windows hidden."""
    if os.name != "nt":
        return dict(start_new_session=True)
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    return dict(creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=startup)


def stop_leftover(child):
    """Last-resort cleanup of this test's process tree, never a PID from a server record."""
    if child.poll() is None:
        if os.name == "nt":
            # The venv's python.exe is a launcher with a second interpreter process.
            result = subprocess.run(
                [str(Path(os.environ["SystemRoot"], "System32", "taskkill.exe")),
                 "/PID", str(child.pid), "/T", "/F"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                **dict(process_options(), creationflags=subprocess.CREATE_NO_WINDOW))
            if result.returncode and child.poll() is None:
                raise AssertionError(f"Cannot clean up child {child.pid}: {result.stdout}{result.stderr}")
        else:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=10)


def windows_console():
    """Win32 console functions, loaded only by the Windows helpers."""
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.AttachConsole.argtypes = (wintypes.DWORD,)
    kernel.AttachConsole.restype = wintypes.BOOL
    kernel.SetConsoleCtrlHandler.argtypes = (ctypes.c_void_p, wintypes.BOOL)
    kernel.SetConsoleCtrlHandler.restype = wintypes.BOOL
    kernel.GenerateConsoleCtrlEvent.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel.GenerateConsoleCtrlEvent.restype = wintypes.BOOL
    kernel.FreeConsole.argtypes = ()
    kernel.FreeConsole.restype = wintypes.BOOL
    return kernel


def windows_launch(args):
    """Give the real CLI normal Ctrl+C handling even if a CI shell ignores it."""
    import ctypes

    kernel = windows_console()
    # SetConsoleCtrlHandler's ignore flag is inherited even in a new console.
    # Change only this private launcher before creating the application child.
    if not kernel.SetConsoleCtrlHandler(None, False):
        raise ctypes.WinError(ctypes.get_last_error())
    child = subprocess.Popen([sys.executable, "-m", "hanok_generator.web", *args],
                             stdin=subprocess.DEVNULL, stdout=sys.stdout, stderr=sys.stderr)
    try:
        # The child already inherited normal handling; keep its launcher alive
        # during Ctrl+C so it can relay the application's actual exit code.
        if not kernel.SetConsoleCtrlHandler(None, True):
            raise ctypes.WinError(ctypes.get_last_error())
        return child.wait()
    finally:
        stop_leftover(child)


def windows_interrupt(pid):
    """Run only in a disposable helper; the server owns the console we attach to."""
    import ctypes

    kernel = windows_console()
    # A Python launcher may attach its interpreter despite CREATE_NO_WINDOW.
    # Detach only this disposable helper, never the unittest process.
    kernel.FreeConsole()
    if not kernel.AttachConsole(pid):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        # Attaching resets the handler table. Ignore Ctrl+C in the sender only.
        if not kernel.SetConsoleCtrlHandler(None, True):
            raise ctypes.WinError(ctypes.get_last_error())
        # CTRL_C_EVENT cannot target a process group; this console contains only
        # the test-owned server tree and this helper, never the unittest runner.
        if not kernel.GenerateConsoleCtrlEvent(0, 0):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.FreeConsole()


class WebProcess:
    def __init__(self, case, output, port=0):
        self.case, self.output, self.port = case, Path(output).resolve(), port
        folder = case.enterContext(tempfile.TemporaryDirectory(prefix="hanok-web-process-"))
        self.log = Path(folder, "server.log")
        stream = case.enterContext(self.log.open("wb"))
        command = [sys.executable, "-m", "hanok_generator.web"]
        if os.name == "nt":
            command = [sys.executable, str(Path(__file__).resolve()), "launch"]
        self.child = subprocess.Popen(
            [*command, "--output", str(self.output), "--port", str(port)],
            stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"), **process_options())
        case.addCleanup(stop_leftover, self.child)

    def diagnostic(self):
        return self.log.read_text(encoding="utf-8", errors="replace")

    def call(self, method="GET", path="/api/meta", body=None, *, timeout=10):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            connection.request(method, path, json.dumps(body) if body is not None else None,
                               {"Content-Type": "application/json"} if body is not None else {})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def ready(self):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            self.case.assertIsNone(self.child.poll(), self.diagnostic())
            match = re.search(r"http://127\.0\.0\.1:(\d+)/", self.diagnostic())
            if match:
                self.port = int(match[1])
                try:
                    status, meta = self.call(timeout=1)
                except (OSError, http.client.HTTPException):
                    pass
                else:
                    self.case.assertEqual((status, meta.get("output")), (200, str(self.output)), self.diagnostic())
                    self.case.assertIsNone(self.child.poll(), self.diagnostic())
                    return self
            time.sleep(0.05)
        self.case.fail(f"Server did not become ready:\n{self.diagnostic()}")

    def wait(self, timeout=20):
        try:
            return self.child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.case.fail(f"Server did not exit in {timeout}s:\n{self.diagnostic()}")

    def stop(self):
        self.case.assertIsNone(self.child.poll(), self.diagnostic())
        if os.name == "nt":
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "interrupt", str(self.child.pid)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10,
                env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"),
                **dict(process_options(), creationflags=subprocess.CREATE_NO_WINDOW))
            self.case.assertEqual(result.returncode, 0, result.stdout + result.stderr + self.diagnostic())
        else:
            self.child.send_signal(signal.SIGINT)
        self.case.assertEqual(self.wait(), 0, self.diagnostic())
        self.case.assertIn("종료합니다.", self.diagnostic())


if __name__ == "__main__":
    if sys.argv[1] == "launch":
        raise SystemExit(windows_launch(sys.argv[2:]))
    if sys.argv[1] != "interrupt":
        raise ValueError("Expected launch or interrupt")
    windows_interrupt(int(sys.argv[2]))
