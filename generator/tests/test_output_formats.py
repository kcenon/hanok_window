"""Export registration, real build phases, rejection and publication boundaries."""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import ezdxf

from hanok_generator import jobs, package
from hanok_generator.engine import builder, output_formats, validation_rules
from hanok_generator.model import canonical


REQUEST = json.loads((Path(__file__).parents[1] / "examples/double_r3.json").read_text(encoding="utf-8"))


@contextmanager
def worker_registration(code):
    """Change only a real worker's registration, without adding a production test hook."""
    run = subprocess.run

    def start(command, **kwargs):
        if command[1:3] == ["-m", "hanok_generator.worker"]:
            bootstrap = ("from dataclasses import replace\n"
                         "from hanok_generator.engine import output_formats as formats\n" + code +
                         "\nfrom hanok_generator.worker import main\nraise SystemExit(main())\n")
            command = [command[0], "-c", bootstrap, *command[3:]]
        return run(command, **kwargs)

    with patch.object(jobs.subprocess, "run", side_effect=start):
        yield


class OutputFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hanok-exports-")
        cls.root = Path(cls.temp.name)
        cls.original = cls.root / "original"
        cls.result = jobs.run_job(REQUEST, cls.original)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name) / "output"
        shutil.copytree(self.original, self.output)
        self.p = self.output / "packages" / self.result["package_id"]
        self.cfg = builder.configure(json.loads((self.p / "design_parameters.json").read_text(encoding="utf-8")), self.p)
        self.before = self.snapshot()
        self.latest = (self.output / "latest.json").read_bytes()

    def snapshot(self):
        return {p.relative_to(self.p).as_posix(): p.read_bytes() for p in self.p.rglob("*") if p.is_file()}

    def assert_preserved(self):
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual((self.output / "latest.json").read_bytes(), self.latest)
        self.assertEqual(package.verify(self.p)["package_id"], self.result["package_id"])
        self.assertEqual(list((self.output / ".staging").iterdir()), [])
        self.assertEqual(list((self.output / "packages").iterdir()), [self.p])

    def test_metadata_is_ordered_unique_and_lightweight(self):
        self.assertEqual(output_formats.filenames(), ("window.ai",))
        self.assertEqual(output_formats.rule_ids(), ("ai_export_matches_saved_dxf",))
        self.assertIn("window.ai", package.required_files())
        code = """import json, sys
from hanok_generator import package
from hanok_generator.engine import output_formats, validation_rules
from hanok_generator.web.server import make_server
from hanok_generator.llm import tools
print(json.dumps(dict(cad=[name for name in ('ezdxf', 'hanok_generator.engine.builder',
    'hanok_generator.engine.ai_export') if name in sys.modules],
    files=output_formats.filenames(), rules=len(validation_rules.RULE_IDS))))
"""
        result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                                encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), dict(cad=[], files=["window.ai"], rules=71))

    def test_export_written_once_and_measured_against_both_documents(self):
        # Direct builds share this interpreter's hash seed. The public worker uses
        # seed 0; DXF class order can differ between those two environments.
        builder.build(self.cfg)
        direct_before = self.snapshot()
        writes, reads, phases = [], [], []
        ai = output_formats.AI
        validate = builder.validate

        def write(cfg, doc, path):
            writes.append((doc, path))
            ai.write(cfg, doc, path)

        def verify(doc, path):
            reads.append((doc, path))
            self.assertEqual(path.read_bytes(), self.before["window.ai"])
            return ai.verify(doc, path)

        def validate_phase(cfg, doc, phase, *args, **kwargs):
            result = validate(cfg, doc, phase, *args, **kwargs)
            phases.append(result)
            return result

        with patch.object(output_formats, "FORMATS", (replace(ai, write=write, verify=verify),)), \
                patch.object(builder, "validate", side_effect=validate_phase):
            doc, report, _ = builder.build(self.cfg)
        self.assertEqual(len(writes), 1)
        self.assertEqual(len(reads), 2)
        self.assertIs(writes[0][0], reads[0][0])
        self.assertIs(reads[1][0], doc)
        self.assertIsNot(reads[0][0], reads[1][0])
        self.assertEqual([p for _, p in reads], [writes[0][1]] * 2)
        self.assertNotEqual(writes[0][1], self.cfg.AI)
        self.assertFalse(writes[0][1].exists())
        self.assertEqual([p["phase"] for p in phases], ["IN_MEMORY_BEFORE_SAVE", "READ_BACK_FROM_SAVED_DXF"])
        for phase in phases:
            self.assertEqual(tuple(c["rule_id"] for c in phase["checks"]), validation_rules.RULE_IDS)
            self.assertEqual(phase["checks_passed"], 71)
        self.assertEqual(report["checks"], json.loads(direct_before["validation_report.json"])["checks"])
        for name in ("window.dxf", "window.ai", "design_spec.json", *package.CSV_FILES):
            self.assertEqual((self.p / name).read_bytes(), direct_before[name], name)

    def test_legacy_and_generic_validation_paths_and_optional_spec(self):
        doc = ezdxf.readfile(self.cfg.DXF)
        alternate = Path(self.directory.name) / "alternate.ai"
        alternate.write_bytes(self.cfg.AI.read_bytes())
        self.cfg.AI.unlink()
        calls = [
            lambda: builder.validate(self.cfg, doc, "STANDALONE", self.cfg.SPEC, alternate),
            lambda: builder.validate(self.cfg, doc, "STANDALONE", ai_path=alternate),
            lambda: builder.validate(self.cfg, doc, "STANDALONE", export_paths={"window.ai": alternate}),
            lambda: builder.validate(replace(self.cfg, AI=alternate), doc, "STANDALONE"),
        ]
        for call in calls:
            self.assertEqual(call()["checks_passed"], 71)
        no_spec = replace(self.cfg, AI=alternate, SPEC=self.p / "absent.json")
        report = builder.validate(no_spec, doc, "STANDALONE")
        self.assertEqual(tuple(c["rule_id"] for c in report["checks"]),
                         tuple(r for r in validation_rules.RULE_IDS if r != "design_spec_on_disk_matches_parameters"))
        self.assertEqual(builder.validate(no_spec, doc, "STANDALONE", self.cfg.SPEC)["checks_passed"], 71)

    def test_build_preserves_design_ai_path_override(self):
        alternate = Path(self.directory.name) / "alternate.ai"
        builder.build(replace(self.cfg, AI=alternate))
        self.assertEqual(alternate.read_bytes(), self.before["window.ai"])
        self.assertEqual(self.cfg.AI.read_bytes(), self.before["window.ai"])

    def test_failed_writers_and_verifiers_clean_all_candidates(self):
        ai = output_formats.AI

        def partial(cfg, doc, path):
            path.write_bytes(b"partial")
            raise OSError("export write failed")

        def invalid(cfg, doc, path):
            path.write_bytes(b"invalid")

        def missing(cfg, doc, path):
            pass

        def broken(doc, path):
            raise OSError("export read failed")

        for fmt, error in [(replace(ai, write=partial), OSError),
                           (replace(ai, write=invalid), builder.ValidationError),
                           (replace(ai, write=missing), builder.ValidationError),
                           (replace(ai, verify=broken), OSError)]:
            with self.subTest(writer=fmt.write.__name__, verifier=fmt.verify.__name__), \
                    patch.object(output_formats, "FORMATS", (fmt,)):
                with self.assertRaises(error) as caught:
                    builder.build(self.cfg)
                if error is builder.ValidationError:
                    self.assertEqual(caught.exception.report["failed_checks"], [ai.rule_id])
                    self.assertEqual(caught.exception.report["phase"], "IN_MEMORY_BEFORE_SAVE")
            self.assert_preserved()

    def test_saved_export_rejection_preserves_previous_files(self):
        ai, documents = output_formats.AI, []

        def reject_saved(doc, path):
            documents.append(doc)
            ok, measured = ai.verify(doc, path)
            return ok and len(documents) == 1, measured

        with patch.object(output_formats, "FORMATS", (replace(ai, verify=reject_saved),)):
            with self.assertRaises(builder.ValidationError) as caught:
                builder.build(self.cfg)
        self.assertEqual(caught.exception.report["phase"], "READ_BACK_FROM_SAVED_DXF")
        self.assertEqual(caught.exception.report["failed_checks"], [ai.rule_id])
        self.assertEqual(len(documents), 2)
        self.assertIsNot(documents[0], documents[1])
        self.assert_preserved()

    def test_later_writer_failure_cleans_earlier_candidates(self):
        paths = []

        def partial(cfg, doc, path):
            self.assertEqual((cfg.OUT / "_validated_candidate_window.ai").read_bytes(), self.before["window.ai"])
            paths.append(path)
            path.write_bytes(b"partial second export")
            raise OSError("second writer failed")

        probe = output_formats.OutputFormat("probe.txt", partial, None, "probe_units", "saved_probe")
        with patch.object(output_formats, "FORMATS", (*output_formats.FORMATS, probe)):
            with self.assertRaises(OSError):
                builder.build(self.cfg)
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())
        self.assert_preserved()

    def test_saved_dxf_rejection_and_read_error_clean_candidates(self):
        readfile = ezdxf.readfile

        def changed(path):
            doc = readfile(path)
            doc.ezdxf_metadata()["HANOK_REVISION"] = "wrong revision"
            return doc

        with patch.object(builder.ezdxf, "readfile", side_effect=changed):
            with self.assertRaises(builder.ValidationError) as caught:
                builder.build(self.cfg)
        self.assertEqual(caught.exception.report["phase"], "READ_BACK_FROM_SAVED_DXF")
        self.assertEqual(caught.exception.report["failed_checks"], ["revision_recorded_matches_parameters"])
        self.assert_preserved()
        with patch.object(builder.ezdxf, "readfile", side_effect=OSError("read failed")):
            with self.assertRaises(OSError):
                builder.build(self.cfg)
        self.assert_preserved()

    def test_export_failures_do_not_publish_or_move_latest(self):
        cases = [
            ("def write(cfg, doc, path):\n path.write_bytes(b'partial')\n raise OSError('write failed')\n"
             "formats.FORMATS = (replace(formats.AI, write=write),)", "build.failed"),
            ("formats.FORMATS = (replace(formats.AI, write=lambda cfg, doc, path: None),)", "geometry.validation"),
            ("calls = []\ndef verify(doc, path):\n calls.append(doc)\n ok, measured = formats.AI.verify(doc, path)\n"
             " return ok and len(calls) == 1, measured\n"
             "formats.FORMATS = (replace(formats.AI, verify=verify),)", "geometry.validation"),
        ]
        for code, rule in cases:
            with self.subTest(rule=rule, code=code), worker_registration(code):
                with self.assertRaises(jobs.JobError) as caught:
                    jobs.run_job(REQUEST, self.output)
                self.assertEqual(caught.exception.result["rule_id"], rule)
            self.assert_preserved()

    def test_one_extra_registration_reaches_the_entire_pipeline(self):
        # An actual child worker imports the catalogue after this registration.
        code = """def write(cfg, doc, path):
 path.write_bytes(str(doc.units).encode('ascii'))
def verify(doc, path):
 return path.read_bytes() == str(doc.units).encode('ascii'), {'units': doc.units}
formats.FORMATS += (formats.OutputFormat('probe.txt', write, verify, 'probe_units', 'saved_probe'),)
from hanok_generator.engine import validation_rules
if len(validation_rules.RULE_IDS) != 72: raise RuntimeError('catalogue missed export')
"""
        with worker_registration(code):
            result = jobs.run_job(REQUEST, self.output)
        p = Path(result["package"])
        self.assertEqual(result["checks"], 72)
        self.assertEqual((p / "probe.txt").read_bytes(), b"4")
        report = json.loads((p / "validation_report.json").read_text(encoding="utf-8"))
        rules = list(validation_rules.RULE_IDS)
        rules.insert(rules.index(output_formats.AI.rule_id) + 1, "probe_units")
        self.assertEqual([c["rule_id"] for c in report["checks"]], rules)
        self.assertEqual(report["pre_save_status"], "PASS_NOMINAL_DXF_GEOMETRY")
        self.assertTrue(report["saved_dxf_reread"])
        self.assertIn("window.dxf, window.ai, probe.txt, PNG", (p / "README.txt").read_text(encoding="utf-8"))
        self.assertEqual(package.verify(p)["package_id"], result["package_id"])
        self.assertFalse(list(p.glob("_validated_candidate*")))

        # The same metadata drives both sealing and read-only verification requirements.
        probe = output_formats.OutputFormat("probe.txt", None, None, "probe_units", "saved_probe")
        with patch.object(output_formats, "FORMATS", (*output_formats.FORMATS, probe)):
            self.assertIn("probe.txt", package.required_files())
            self.assertEqual(package.seal(p)["package_id"], result["package_id"])
            (p / "probe.txt").unlink()
            with self.assertRaisesRegex(package.PackageError, "Missing required artifacts.*probe.txt"):
                package.seal(p)
            # Even a self-consistent manifest cannot omit a newly required export.
            manifest = json.loads((p / "package_manifest.json").read_text(encoding="utf-8"))
            manifest["files"] = [r for r in manifest["files"] if r["path"] != "probe.txt"]
            manifest["package_id"] = hashlib.sha256(canonical(manifest["files"]).encode()).hexdigest()
            package.write_json(p / "package_manifest.json", manifest)
            before = (p / "package_manifest.json").read_bytes()
            with self.assertRaises(package.PackageError):
                package.verify(p)
            self.assertEqual((p / "package_manifest.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
