"""Previously exempt files must satisfy actual geometry, report and pixel comparisons."""
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from hanok_generator.jobs import run_job
from hanok_generator.package import PNG_FILES, digest, package_files, write_json
from hanok_generator.model import canonical
from tools import compare_package_contents as contents


def inventory(folder):
    manifest = json.loads((folder / "package_manifest.json").read_text(encoding="utf-8"))
    rows = [dict(path=n, bytes=p.stat().st_size, sha256=digest(p)) for n, p in package_files(folder)]
    manifest.update(files=rows, package_id=hashlib.sha256(canonical(rows).encode()).hexdigest())
    write_json(folder / "package_manifest.json", manifest)


class PackageContentsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hanok-content-tests-")
        cls.root = Path(cls.temp.name)
        with patch.dict(os.environ, HANOK_FONT=str(contents.FONT)):
            request = json.loads((Path(__file__).parents[1] / "examples/double_r3.json").read_text(encoding="utf-8"))
            cls.original = Path(run_job(request, cls.root / "build")["package"])

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(temp.cleanup)
        self.artifacts = Path(temp.name)
        for system in contents.SYSTEMS:
            folder = self.artifacts / (contents.ARTIFACT_PREFIX + system)
            shutil.copytree(self.original, folder)
            env = json.loads((folder / "environment.json").read_text(encoding="utf-8"))
            env["platform"] = contents.PLATFORMS[system]
            write_json(folder / "environment.json", env)
            inventory(folder)
        self.ubuntu = self.artifacts / (contents.ARTIFACT_PREFIX + "ubuntu-latest")

    def test_actual_contents_pass(self):
        self.assertTrue(contents.check(self.artifacts).startswith("PASS:"))

    def test_every_png_pixel_change_is_rejected_after_resealing(self):
        for name in PNG_FILES:
            with self.subTest(name=name):
                path = self.ubuntu / name
                original = path.read_bytes()
                with Image.open(path) as source:
                    image = source.convert("RGB")
                image.putpixel((0, 0), (255, 0, 255))
                image.save(path)
                inventory(self.ubuntu)
                with self.assertRaisesRegex(contents.ComparisonError, "pixels differ"):
                    contents.check(self.artifacts)
                path.write_bytes(original)
                inventory(self.ubuntu)

    def test_dxf_float_difference_is_bounded(self):
        path = self.ubuntu / "window.dxf"
        original = path.read_text(encoding="utf-8")
        lines = original.splitlines()
        index = next(i+1 for i in range(0, len(lines)-1, 2) if lines[i].strip() == "10")
        for delta, allowed in ((1e-9, True), (0.01, False)):
            changed = list(lines)
            changed[index] = repr(float(lines[index]) + delta)
            path.write_bytes(("\n".join(changed)+"\n").encode("utf-8"))
            report_path = self.ubuntu / "validation_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["sha256"] = digest(path)
            write_json(report_path, report)
            inventory(self.ubuntu)
            if allowed:
                contents.check(self.artifacts)
            else:
                with self.assertRaisesRegex(contents.ComparisonError, "DXF tag"):
                    contents.check(self.artifacts)

    def test_report_differences_are_bounded_and_keys_preserved(self):
        path = self.ubuntu / "validation_report.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for field, value in (("minimum_part_gap_mm", original["minimum_part_gap_mm"] + 0.01),
                             ("parts_total", original["parts_total"] + 1)):
            report = copy.deepcopy(original)
            report[field] = value
            write_json(path, report)
            inventory(self.ubuntu)
            with self.assertRaises(contents.ComparisonError):
                contents.check(self.artifacts)
        report = copy.deepcopy(original)
        report.pop("checks")
        write_json(path, report)
        inventory(self.ubuntu)
        with self.assertRaises((contents.ComparisonError, ValueError)):
            contents.check(self.artifacts)

    def test_font_source_and_library_records_cannot_drift(self):
        path = self.ubuntu / "environment.json"
        original = json.loads(path.read_text(encoding="utf-8"))
        for kind in ("font", "source", "library"):
            env = copy.deepcopy(original)
            if kind == "font":
                env["fonts"]["regular"]["sha256"] = "0" * 64
            elif kind == "source":
                env["source_sha256"]["package.py"] = "0" * 64
            else:
                env["libraries"]["Pillow"] = "0.0.0"
            write_json(path, env)
            report_path = self.ubuntu / "validation_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["render_environment"] = {key: env[key] for key in ("fonts", "libraries")}
            write_json(report_path, report)
            inventory(self.ubuntu)
            with self.assertRaises(contents.ComparisonError):
                contents.check(self.artifacts)

    def test_unhashed_payload_change_is_rejected(self):
        (self.ubuntu / PNG_FILES[0]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            contents.check(self.artifacts)


@unittest.skipUnless(os.environ.get("R3_CONTENT_ARTIFACTS"), "requires downloaded CI package contents")
class ActualContentsTests(unittest.TestCase):
    def test_real_artifacts_reject_a_changed_png_after_resealing(self):
        root = Path(os.environ["R3_CONTENT_ARTIFACTS"])
        contents.check(root)
        with tempfile.TemporaryDirectory(prefix="hanok-content-artifacts-") as temporary:
            copied = Path(temporary) / "artifacts"
            shutil.copytree(root, copied)
            manifest, = (copied / (contents.ARTIFACT_PREFIX + "ubuntu-latest")).rglob("package_manifest.json")
            folder = manifest.parent
            path = folder / PNG_FILES[0]
            with Image.open(path) as original:
                image = original.convert("RGB")
            value = image.getpixel((0, 0))
            image.putpixel((0, 0), tuple(255-component for component in value))
            image.save(path)
            inventory(folder)
            with self.assertRaisesRegex(contents.ComparisonError, "pixels differ"):
                contents.check(copied)
        print("Real artifacts: PASS; resealed Ubuntu PNG pixel change: rejected.")


if __name__ == "__main__":
    unittest.main()
