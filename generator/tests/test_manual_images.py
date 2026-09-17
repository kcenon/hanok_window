"""Manual capture discovery, read-only pixel checks, and cleanup without a browser."""
from __future__ import annotations

from contextlib import chdir, redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, PngImagePlugin

from docs.manual import make_images as manual


def write_images(folder):
    folder.mkdir(parents=True, exist_ok=True)
    for name in manual.IMAGE_NAMES:
        Image.new("RGB", (3, 2), "white").save(folder / name)


def snapshot(folder):
    return {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in folder.iterdir()}


class TemporaryTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="hanok-manual-test-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.messages = io.StringIO()
        self.enterContext(redirect_stdout(self.messages))
        self.enterContext(redirect_stderr(self.messages))

    def executable(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"browser fixture")
        path.chmod(0o755)
        return str(path)


class ChromeDiscoveryTests(TemporaryTest):
    def test_explicit_path_with_spaces_takes_precedence(self):
        binary = self.executable(self.root / "Custom Chrome" / "chrome.exe")
        with patch.object(manual.shutil, "which") as which:
            self.assertEqual(manual.find_chrome(binary), binary)
        which.assert_not_called()

    def test_invalid_explicit_override_never_falls_back(self):
        fallback = self.executable(self.root / "fallback")
        missing = str(self.root / "missing")
        with patch.object(manual, "CHROMES", (fallback,)), patch.object(manual.shutil, "which", return_value=None) as which:
            with self.assertRaisesRegex(RuntimeError, "--chrome"):
                manual.find_chrome(missing)
        which.assert_called_once_with(missing)

    def test_relative_explicit_path_is_resolved_before_launch(self):
        binary = self.executable(self.root / "Relative Chrome" / "chrome.exe")
        with chdir(self.root), patch.object(manual.shutil, "which") as which:
            self.assertEqual(manual.find_chrome(os.path.relpath(binary)), binary)
        which.assert_not_called()

    def test_automatic_command_names_use_path_lookup(self):
        self.executable(self.root / "chrome")
        binary = self.executable(self.root / "on PATH" / "chrome")
        with chdir(self.root), patch.object(manual, "CHROMES", ("chrome",)), \
                patch.object(manual.shutil, "which", return_value=binary) as which:
            self.assertEqual(manual.find_chrome(None), binary)
        which.assert_called_once_with("chrome")

    def test_directory_is_not_an_executable(self):
        with patch.object(manual.shutil, "which", return_value=str(self.root)):
            with self.assertRaisesRegex(RuntimeError, "Chrome"):
                manual.find_chrome(str(self.root))

    def test_windows_system_x86_and_user_installations(self):
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            with self.subTest(variable=variable):
                env = {name: str(self.root / variable / name) for name in
                       ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")}
                binary = self.executable(Path(env[variable]) / "Google" / "Chrome" / "Application" / "chrome.exe")
                with patch.dict(os.environ, env), patch.object(manual.sys, "platform", "win32"), \
                        patch.object(manual, "CHROMES", ()), patch.object(manual.shutil, "which", return_value=None):
                    self.assertEqual(manual.find_chrome(None), binary)

    def test_windows_empty_environment_uses_standard_system_roots(self):
        with patch.dict(os.environ, {"ProgramFiles": "", "ProgramFiles(x86)": "", "LOCALAPPDATA": ""}), \
                patch.object(manual.sys, "platform", "win32"):
            candidates = manual.windows_chromes()
        self.assertEqual(candidates, [str(Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe")
                                      for root in (r"C:\Program Files", r"C:\Program Files (x86)")])

    def test_existing_mac_and_path_candidates(self):
        binary = self.executable(self.root / "Google Chrome.app" / "Contents" / "MacOS" / "Google Chrome")
        for platform, candidate in (("darwin", manual.CHROMES[0]), ("linux", "google-chrome"),
                                    ("linux", "chromium-browser"), ("win32", "chrome.exe")):
            with self.subTest(platform=platform, candidate=candidate):
                with patch.object(manual.sys, "platform", platform), \
                        patch.object(manual.shutil, "which", side_effect=lambda value: binary if value == candidate else None), \
                        patch.object(manual.os.path, "isfile", side_effect=lambda value: value == binary):
                    self.assertEqual(manual.find_chrome(None), binary)

    def test_missing_browser_has_platform_specific_guidance(self):
        for platform, example in (("win32", r"C:\Program Files"), ("linux", "/경로/Google Chrome")):
            with self.subTest(platform=platform), patch.object(manual.sys, "platform", platform), \
                    patch.object(manual.os.path, "isfile", return_value=False), \
                    patch.object(manual.shutil, "which", return_value=None):
                with self.assertRaises(RuntimeError) as raised:
                    manual.find_chrome(None)
                self.assertIn('--chrome "', str(raised.exception))
                self.assertIn(example, str(raised.exception))


class ImageCheckTests(TemporaryTest):
    def setUp(self):
        super().setUp()
        self.reference, self.generated = self.root / "reference", self.root / "generated"
        write_images(self.reference)
        write_images(self.generated)
        self.name = "design.png"

    def test_equal_pixels_ignore_metadata_and_mode(self):
        info = PngImagePlugin.PngInfo()
        info.add_text("capture", "different metadata")
        Image.new("RGBA", (3, 2), "white").save(self.reference / self.name, pnginfo=info)
        self.assertNotEqual((self.reference / self.name).read_bytes(), (self.generated / self.name).read_bytes())
        self.assertEqual(manual.compare_images(self.reference, self.generated), 0)

    def test_changed_pixel_size_and_alpha_are_detected(self):
        for size, color, reason in (((3, 2), "black", "픽셀"), ((4, 2), "white", "크기"),
                                    ((3, 2), (255, 255, 255, 0), "픽셀")):
            with self.subTest(size=size, color=color):
                image = Image.new("RGBA", size, "white")
                image.putpixel((0, 0), Image.new("RGBA", (1, 1), color).getpixel((0, 0)))
                image.save(self.generated / self.name)
                self.assertEqual(manual.compare_images(self.reference, self.generated), 1)
                self.assertIn(f"{self.name}: {reason}", self.messages.getvalue())

    def test_missing_and_unexpected_pngs_are_named(self):
        (self.reference / self.name).unlink()
        Image.new("RGB", (1, 1)).save(self.reference / "extra.PNG")
        self.assertEqual(manual.compare_images(self.reference, self.generated), 1)
        self.assertIn(f"{self.name}: 기준 그림 누락", self.messages.getvalue())
        self.assertIn("extra.PNG: 예상하지 않은 기준 그림", self.messages.getvalue())

    def run_main(self, *args, renderer=None):
        with patch.object(manual, "find_chrome", return_value="browser"), \
                patch.object(manual, "render_images", side_effect=renderer or (lambda binary, out: write_images(out))):
            return manual.main(["--out", str(self.reference), *args])

    def test_check_renders_into_temporary_storage_and_preserves_reference(self):
        captured = []
        before = snapshot(self.reference)

        def render(binary, out):
            self.assertEqual(binary, "browser")
            self.assertNotEqual(out, self.reference)
            self.assertFalse(out.is_relative_to(self.reference))
            captured.append(out)
            write_images(out)

        self.assertEqual(self.run_main("--check", renderer=render), 0)
        self.assertEqual(snapshot(self.reference), before)
        self.assertFalse(captured[0].exists())

    def test_difference_and_unreadable_image_preserve_reference(self):
        for content, status in ((None, 1), (b"not a PNG", 2)):
            with self.subTest(status=status):
                if content is None:
                    Image.new("RGB", (3, 2), "black").save(self.reference / self.name)
                else:
                    (self.reference / self.name).write_bytes(content)
                before = snapshot(self.reference)
                self.assertEqual(self.run_main("--check"), status)
                self.assertEqual(snapshot(self.reference), before)
                self.assertIn(self.name, self.messages.getvalue())

    def test_missing_reference_is_not_created(self):
        missing = self.root / "missing"
        with patch.object(manual, "render_images") as render, patch.object(manual, "find_chrome") as discover:
            self.assertEqual(manual.main(["--check", "--out", str(missing)]), 1)
        self.assertFalse(missing.exists())
        render.assert_not_called()
        discover.assert_not_called()

    def test_browser_failure_is_an_operational_error_before_rendering(self):
        before = snapshot(self.reference)
        with patch.object(manual, "find_chrome", side_effect=RuntimeError("missing browser")), \
                patch.object(manual, "render_images") as render:
            self.assertEqual(manual.main(["--check", "--out", str(self.reference)]), 2)
        render.assert_not_called()
        self.assertEqual(snapshot(self.reference), before)

    def test_failed_or_incomplete_capture_never_publishes(self):
        before = snapshot(self.reference)
        captured = []

        def render(binary, out):
            captured.append(out)
            Image.new("RGB", (1, 1)).save(out / self.name)

        for check in ([], ["--check"]):
            with self.subTest(check=check):
                self.assertEqual(self.run_main(*check, renderer=render), 2)
                self.assertEqual(self.run_main(*check, renderer=Mock(side_effect=RuntimeError("capture failed"))), 2)
                self.assertEqual(snapshot(self.reference), before)
        self.assertTrue(all(not p.exists() for p in captured))

    def test_successful_generation_publishes_complete_set(self):
        (self.reference / self.name).unlink()
        self.assertEqual(self.run_main(), 0)
        self.assertEqual(manual.png_names(self.reference), manual.IMAGE_NAMES)
        self.assertEqual(manual.compare_images(self.reference, self.generated), 0)


class ResourceCleanupTests(TemporaryTest):
    def test_failed_websocket_handshake_closes_socket(self):
        sock = Mock()
        sock.recv.return_value = b"HTTP/1.1 403 Forbidden\r\n\r\n"
        with patch.object(manual.socket, "create_connection", return_value=sock):
            with self.assertRaisesRegex(RuntimeError, "upgrade"):
                manual.Wire("ws://127.0.0.1:1/devtools")
        sock.close.assert_called_once()

    def test_chrome_startup_failures_remove_profile_and_reap_child(self):
        for stage in ("spawn", "endpoint", "wire"):
            with self.subTest(stage=stage):
                profile = tempfile.TemporaryDirectory(dir=self.root)
                proc = Mock()
                proc.poll.return_value = None
                with patch.object(manual.tempfile, "TemporaryDirectory", return_value=profile), \
                        patch.object(manual.subprocess, "Popen", side_effect=OSError("spawn") if stage == "spawn" else None,
                                     return_value=proc), \
                        patch.object(manual.Chrome, "_endpoint", side_effect=TimeoutError("endpoint") if stage == "endpoint" else None,
                                     return_value="ws://127.0.0.1:1/devtools"), \
                        patch.object(manual, "Wire", side_effect=RuntimeError("wire")):
                    with self.assertRaises((OSError, RuntimeError)):
                        manual.Chrome("browser")
                self.assertFalse(Path(profile.name).exists())
                if stage != "spawn":
                    proc.terminate.assert_called_once()
                    proc.wait.assert_called_once_with(timeout=15)

    def test_unresponsive_chrome_is_killed_and_waited_for(self):
        chrome = manual.Chrome.__new__(manual.Chrome)
        chrome.profile = tempfile.TemporaryDirectory(dir=self.root)
        chrome.proc, chrome.wire, chrome.next_id = Mock(), Mock(), 0
        chrome.proc.wait.side_effect = [subprocess.TimeoutExpired("browser", 15), 0]
        with patch.object(chrome, "send", side_effect=TimeoutError("browser close")):
            chrome.close()
        chrome.wire.close.assert_called_once()
        chrome.proc.kill.assert_called_once()
        self.assertEqual(chrome.proc.wait.call_count, 2)
        self.assertFalse(Path(chrome.profile.name).exists())

    def test_render_failure_closes_server_and_browser(self):
        for stage in ("server", "thread", "shoot", "drawings", "success"):
            with self.subTest(stage=stage):
                chrome, server, thread = Mock(), Mock(port=1234), Mock()
                output_paths = []

                def examples(output):
                    output_paths.append(output)
                    return {"double_r3": "id"}

                thread.start.side_effect = RuntimeError("thread") if stage == "thread" else None
                with patch.object(manual, "build_examples", side_effect=examples), \
                        patch.object(manual, "Chrome", return_value=chrome), \
                        patch.object(manual, "make_server", return_value=server,
                                     side_effect=RuntimeError("server") if stage == "server" else None), \
                        patch.object(manual.threading, "Thread", return_value=thread), \
                        patch.object(manual, "shoot", side_effect=RuntimeError("shoot") if stage == "shoot" else None), \
                        patch.object(manual, "reduce_drawings", side_effect=RuntimeError("drawings") if stage == "drawings" else None):
                    if stage == "success":
                        manual.render_images("browser", self.root)
                    else:
                        with self.assertRaisesRegex(RuntimeError, stage):
                            manual.render_images("browser", self.root)
                chrome.close.assert_called_once()
                if stage != "server":
                    server.close.assert_called_once()
                if stage not in ("server", "thread"):
                    server.shutdown.assert_called_once()
                    thread.join.assert_called_once_with(timeout=15)
                else:
                    server.shutdown.assert_not_called()
                self.assertTrue(all(not p.parent.exists() for p in output_paths))


if __name__ == "__main__":
    unittest.main()
