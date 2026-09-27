"""Archived packages remain readable while missing and changed artifacts fail."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from hanok_generator import package
from hanok_generator.engine import output_formats
from hanok_generator.jobs import run_job
from hanok_generator.llm.tools import Toolbox
from hanok_generator.model import canonical
from hanok_generator.web.service import Service


HERE = Path(__file__).parent
LEGACY_ID = "e6539f1c13eff237acc19478c5d50d418a02305cd8623871e543b76bbe3a5c8b"


def rewrite_inventory(folder):
    """An updated inventory must not conceal a missing recorded output."""
    manifest = json.loads((folder / "package_manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = [dict(path=name, bytes=p.stat().st_size, sha256=package.digest(p))
                         for name, p in package.package_files(folder)]
    manifest["package_id"] = hashlib.sha256(canonical(manifest["files"]).encode()).hexdigest()
    package.write_json(folder / "package_manifest.json", manifest)


class PackageCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hanok-compatibility-")
        cls.root = Path(cls.temp.name)
        request = json.loads((HERE.parent / "examples/double_r3.json").read_text(encoding="utf-8"))
        cls.current = Path(run_job(request, cls.root / "current")["package"])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name)
        self.legacy = self.output / "packages" / LEGACY_ID
        with zipfile.ZipFile(HERE / "fixtures/legacy_v0_4_1.zip") as archive:
            archive.extractall(self.legacy)

    def current_copy(self):
        target = self.output / "current-copy"
        shutil.copytree(self.current, target)
        return target

    def test_archived_package_through_python_cli_web_and_llm(self):
        before = {name: package.digest(p) for name, p in package.package_files(self.legacy)}
        manifest = (self.legacy / "package_manifest.json").read_bytes()
        expected = dict(status="PASS", package_id=LEGACY_ID, files=34)
        self.assertEqual(package.verify(self.legacy), expected)
        process = subprocess.run([sys.executable, "-m", "hanok_generator", "verify", str(self.legacy)],
                                 capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(json.loads(process.stdout), expected)
        service = Service(self.output)
        self.assertEqual(service.verify(LEGACY_ID), expected)
        self.assertEqual(service.package(LEGACY_ID)["checks"]["total"], 67)
        self.assertTrue(service.package_zip(LEGACY_ID)[0])
        box = Toolbox(self.output)
        result = box.call("verify_package", {"package_id": LEGACY_ID})
        self.assertFalse(result.is_error)
        self.assertEqual(result.data, expected)
        self.assertEqual(before, {name: package.digest(p) for name, p in package.package_files(self.legacy)})
        self.assertEqual((self.legacy / "package_manifest.json").read_bytes(), manifest)

    def test_registry_growth_does_not_invalidate_existing_packages(self):
        extra = output_formats.OutputFormat("future.txt", None, None, "future_export", "future")
        with patch.object(output_formats, "FORMATS", (*output_formats.FORMATS, extra)):
            for path in (self.legacy, self.current):
                self.assertEqual(package.verify(path)["status"], "PASS")
            with self.assertRaisesRegex(package.PackageError, "Missing required artifacts.*future.txt"):
                package.seal(self.current_copy())

    def test_changed_or_missing_legacy_file_is_still_refused(self):
        path = self.legacy / "window.dxf"
        path.write_bytes(path.read_bytes() + b"changed")
        with self.assertRaisesRegex(package.PackageError, "Changed files"):
            package.verify(self.legacy)
        path.unlink()
        with self.assertRaises(package.PackageError):
            package.verify(self.legacy)

    def test_new_contract_is_hashed_and_retains_required_exports(self):
        folder = self.current_copy()
        env_path = folder / "environment.json"
        env = json.loads(env_path.read_text(encoding="utf-8"))
        self.assertEqual(env["package_format"]["required_files"], sorted(package.required_files()))
        env["package_format"]["required_files"].remove("window.ai")
        package.write_json(env_path, env)
        with self.assertRaisesRegex(package.PackageError, "Changed files.*environment.json"):
            package.verify(folder)

    def test_missing_ai_fails_even_with_rewritten_inventory(self):
        for historical in (False, True):
            with self.subTest(pre_contract=historical), tempfile.TemporaryDirectory(dir=self.output) as tmp:
                folder = Path(tmp) / "package"
                shutil.copytree(self.current, folder)
                if historical:
                    env_path = folder / "environment.json"
                    env = json.loads(env_path.read_text(encoding="utf-8"))
                    env.pop("package_format")
                    package.write_json(env_path, env)
                    rewrite_inventory(folder)
                    self.assertEqual(package.verify(folder)["status"], "PASS")
                (folder / "window.ai").unlink()
                rewrite_inventory(folder)
                with self.assertRaisesRegex(package.PackageError, "Missing recorded required artifacts.*window.ai"):
                    package.verify(folder)

    def test_unknown_or_invalid_recorded_contract_is_refused(self):
        invalid = [None, dict(version=True), dict(version=2), dict(version=1, required_files=[]),
                   dict(version=1, required_files=[{}])]
        folder = self.current_copy()
        env_path = folder / "environment.json"
        env = json.loads(env_path.read_text(encoding="utf-8"))
        for contract in invalid:
            with self.subTest(contract=contract):
                env["package_format"] = contract
                package.write_json(env_path, env)
                rewrite_inventory(folder)
                with self.assertRaises(package.PackageError):
                    package.verify(folder)


if __name__ == "__main__":
    unittest.main()
