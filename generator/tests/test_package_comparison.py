"""Cross-OS package comparison, including a CLI negative control on real CI artifacts."""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from tools import compare_package_manifests as comparison


SCRIPT = Path(comparison.__file__)


def write_manifest(path, manifest):
    # Keep a modified manifest internally consistent, as if its producer sealed
    # different output bytes. The negative control must reach cross-OS comparison.
    rows = json.dumps(manifest["files"], ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)
    manifest["package_id"] = hashlib.sha256(rows.encode("utf-8")).hexdigest()
    path.write_text(json.dumps(manifest), encoding="utf-8")


def run_comparator(root, *args):
    return subprocess.run([sys.executable, str(SCRIPT), str(root), *map(str, args)],
                          capture_output=True, text=True, encoding="utf-8", timeout=30)


class PackageComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="hanok-manifest-tests-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "artifacts"
        self.paths = {}
        self.manifest = dict(schema_version=1, status="COMPLETE_NOMINAL_CAD", manufacturing_status="PENDING",
                             files=[dict(path=path, bytes=10, sha256="a" * 64)
                                    for path in ["window.ai", "design_spec.json", *comparison.EXCEPTIONS]])
        for system in comparison.SYSTEMS:
            folder = self.root / (comparison.ARTIFACT_PREFIX + system)
            folder.mkdir(parents=True)
            self.paths[system] = folder / "package_manifest.json"
            write_manifest(self.paths[system], self.manifest)

    def change(self, system, mutate):
        path = self.paths[system]
        manifest = json.loads(path.read_text(encoding="utf-8"))
        mutate(manifest)
        write_manifest(path, manifest)

    def compare(self):
        return comparison.compare(comparison.load_manifests(self.root))

    def test_equal_and_reordered_entries(self):
        self.change("ubuntu-latest", lambda value: value["files"].reverse())
        success, report = self.compare()
        self.assertTrue(success, report)
        self.assertIn("equal=10", report)
        self.assertIn("Unused exceptions", report)
        self.assertEqual(self.compare()[1], report)

    def test_allowed_differences(self):
        for index, system in enumerate(comparison.SYSTEMS):
            def mutate(value):
                for row in value["files"]:
                    if row["path"] in comparison.EXCEPTIONS:
                        variant = min(index, 1) if row["path"] == "window.dxf" else index
                        row.update(bytes=10 + variant, sha256=str(variant) * 64)
            self.change(system, mutate)
        success, report = self.compare()
        self.assertTrue(success, report)
        self.assertIn("expected differences=8", report)
        self.assertNotIn("Unused exceptions", report)

    def test_strict_file_hash_and_size(self):
        for field, value in [("sha256", "b" * 64), ("bytes", 11)]:
            with self.subTest(field=field):
                self.change("ubuntu-latest", lambda data: data["files"][0].update({field: value}))
                success, report = self.compare()
                self.assertFalse(success)
                self.assertIn("UNEXPECTED 'window.ai'", report)
                write_manifest(self.paths["ubuntu-latest"], self.manifest)

    def test_dxf_exception_does_not_hide_macos_windows_mismatch(self):
        self.change("windows-latest", lambda value: next(row for row in value["files"]
                    if row["path"] == "window.dxf").update(sha256="b" * 64))
        success, report = self.compare()
        self.assertFalse(success)
        self.assertIn("macos-latest vs windows-latest: unexpected", report)

    def test_missing_and_extra_files_even_when_exempt(self):
        self.change("ubuntu-latest", lambda value: value["files"].pop())
        success, report = self.compare()
        self.assertFalse(success)
        self.assertIn("'window.dxf': missing from ubuntu-latest", report)
        self.change("ubuntu-latest", lambda value: value["files"].append(
            dict(path="new.png", bytes=1, sha256="b" * 64)))
        success, report = self.compare()
        self.assertFalse(success)
        self.assertIn("'new.png': missing from macos-latest, windows-latest", report)

    def test_missing_extra_and_ambiguous_artifacts(self):
        folder = self.paths["ubuntu-latest"].parent
        renamed = folder.with_name("r3-manifest-unknown")
        folder.rename(renamed)
        with self.assertRaisesRegex(comparison.ComparisonError, "Artifact set mismatch"):
            self.compare()
        renamed.rename(folder)
        self.paths["ubuntu-latest"].unlink()
        with self.assertRaisesRegex(comparison.ComparisonError, "exactly one"):
            self.compare()
        write_manifest(self.paths["ubuntu-latest"], self.manifest)
        (folder / "duplicate").mkdir()
        write_manifest(folder / "duplicate/package_manifest.json", self.manifest)
        with self.assertRaisesRegex(comparison.ComparisonError, "found 2"):
            self.compare()

    def test_invalid_manifest_contract(self):
        mutations = [
            lambda value: value.update(schema_version=2),
            lambda value: value.update(schema_version=True),
            lambda value: value.update(status="FAIL"),
            lambda value: value.update(manufacturing_status="APPROVED"),
            lambda value: value.update(package_id="invalid"),
            lambda value: value.update(unknown="field"),
            lambda value: value.update(files=[]),
            lambda value: value.update(files={}),
            lambda value: value["files"].append(value["files"][0]),
            lambda value: value["files"][0].update(bytes=-1),
            lambda value: value["files"][0].update(bytes=True),
            lambda value: value["files"][0].update(sha256="invalid"),
            lambda value: value["files"][0].pop("bytes"),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(index=index):
                value = copy.deepcopy(self.manifest)
                mutate(value)
                with self.assertRaises(comparison.ComparisonError):
                    comparison.file_entries(value)
        for path in ("../file", "/file", "C:/file", "a\\b", "a//b", "a/./b", "a\nfile", "", None):
            with self.subTest(path=path):
                value = copy.deepcopy(self.manifest)
                value["files"][0]["path"] = path
                with self.assertRaises(comparison.ComparisonError):
                    comparison.file_entries(value)

    def test_malformed_json_and_duplicate_json_keys(self):
        for content in (b"{", b"\xff", b'{"files": [], "files": []}'):
            with self.subTest(content=content):
                self.paths["ubuntu-latest"].write_bytes(content)
                with self.assertRaisesRegex(comparison.ComparisonError, "ubuntu-latest"):
                    self.compare()

    def test_cli_negative_control_and_summary(self):
        summary = Path(self.temp.name) / "summary.md"
        baseline = run_comparator(self.root, "--summary", summary)
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        self.change("ubuntu-latest", lambda value: value["files"][0].update(sha256="b" * 64))
        changed = run_comparator(self.root, "--summary", summary)
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        self.assertIn("UNEXPECTED 'window.ai'", changed.stdout)
        self.assertIn("FAIL:", summary.read_text(encoding="utf-8"))
        self.paths["ubuntu-latest"].unlink()
        missing = run_comparator(self.root, "--summary", summary)
        self.assertEqual(missing.returncode, 1, missing.stdout + missing.stderr)
        self.assertIn("expected exactly one", missing.stdout)


@unittest.skipUnless(os.environ.get("R3_MANIFEST_ARTIFACTS"), "requires downloaded three-OS CI artifacts")
class DownloadedArtifactTests(unittest.TestCase):
    def test_real_artifacts_pass_and_changed_ai_fails(self):
        root = Path(os.environ["R3_MANIFEST_ARTIFACTS"])
        baseline = run_comparator(root)
        self.assertEqual(baseline.returncode, 0, baseline.stdout + baseline.stderr)
        with tempfile.TemporaryDirectory(prefix="hanok-manifest-negative-") as temp:
            copied = Path(temp) / "artifacts"
            shutil.copytree(root, copied)
            path, = (copied / "r3-manifest-ubuntu-latest").rglob("package_manifest.json")
            value = json.loads(path.read_text(encoding="utf-8"))
            row = next(row for row in value["files"] if row["path"] == "window.ai")
            row["sha256"] = ("0" if row["sha256"][0] != "0" else "1") + row["sha256"][1:]
            write_manifest(path, value)
            changed = run_comparator(copied)
            self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
            self.assertIn("UNEXPECTED 'window.ai'", changed.stdout)
        print("Real artifacts: PASS; changed Ubuntu window.ai: rejected with exit code 1.")


if __name__ == "__main__":
    unittest.main()
