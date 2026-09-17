"""LLM tools: definitions for every format (with output schemas), canonical requests, tool results and their
schemas, fix suggestions, package file reading, the CLI runner, the MCP stdio server (handshake, version
negotiation, concurrent calls, progress, cancellation, error codes, image content) and process isolation."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, SchemaError, ValidationError

from hanok_generator.engine import validation_rules
from hanok_generator.jobs import run_job
from hanok_generator.llm import FORMATS, Toolbox
from hanok_generator.llm.mcp import PROTOCOL_VERSIONS
from hanok_generator.llm.tools import DRAWINGS, EXAMPLES, MAX_TEXT, canonical_request

ARTWORK = {"type": "double", "lattice_per_leaf": [2, 4], "preset": "standard_4x8_v1",
           "artwork": {"size_mm": [420, 594]}}
from hanok_generator.package import source_files

ROOT = Path(__file__).parent.parent
NAMES = ["describe_generator", "check_design", "build_package", "list_packages", "get_package", "verify_package",
         "get_drawing", "read_package_file"]
PNG = b"\x89PNG\r\n\x1a\n"
# Fresh interpreter: like the web server, a process that serves tools must never load the builder.
ISOLATION = """
import json, sys, tempfile
from hanok_generator.llm import Toolbox
request = json.loads(sys.argv[1])
with tempfile.TemporaryDirectory() as tmp:
    box = Toolbox(tmp)
    errors = [box.call("check_design", request).is_error, box.call("build_package", request).is_error]
print(json.dumps(dict(errors=errors, builder="hanok_generator.engine.builder" in sys.modules,
                      ezdxf="ezdxf" in sys.modules)))
"""


def rpc(ident, method, params=None):
    message = {"jsonrpc": "2.0", "id": ident, "method": method}
    if params is not None:
        message["params"] = params
    return message


def initialize(version):
    return rpc(1, "initialize", {"protocolVersion": version, "capabilities": {},
                                 "clientInfo": {"name": "tests", "version": "1"}})


INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def validate_output(value, schema):
    """Check the schema itself, then retain ValidationError's instance path and constraint diagnostics."""
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(value)


def assert_check_descriptions(case, box, count):
    for fmt in FORMATS:
        with case.subTest(format=fmt):
            definitions = box.definitions(fmt)
            tools = [t["function"] if fmt == "openai" else t for t in definitions]
            build = next(t for t in tools if t["name"] == "build_package")
            case.assertIn(f"runs {count} checks", build["description"])
    described = box.call("describe_generator")
    case.assertFalse(described.is_error, described.data)
    case.assertIn(f"({count} checks)", described.data["makes"])


class OutputSchemaTests(unittest.TestCase):
    def test_declared_constraints_reject_invalid_results(self):
        closed = {"type": "object", "properties": {"value": {"type": "integer"}},
                  "additionalProperties": False}
        nested = {"type": "array", "items": closed}
        cases = (
            ("additionalProperties", closed, [{}, {"value": 1}], [{"extra": 1}, {"value": 1, "extra": 2}]),
            ("enum", {"type": "string", "enum": ["PASS", "FAIL"]}, ["PASS", "FAIL"], ["OTHER"]),
            ("minimum", {"type": "number", "minimum": 0}, [0, 0.5], [-1]),
            ("maximum", {"type": "number", "maximum": 10}, [9.5, 10], [11]),
            ("const", {"const": "PASS"}, ["PASS"], ["FAIL"]),
            # An integer matches both branches; a string matches neither.
            ("oneOf", {"oneOf": [{"type": "number"}, {"type": "integer"}]}, [1.5], [1, "wrong"]),
            ("required", {"type": "object", "required": ["status"]}, [{"status": "PASS"}], [{}]),
            ("type", {"type": "integer"}, [0, 1.0], [True, False, 1.5, "1", None]),
            ("type", {"type": "number"}, [0, 0.5], [True, False, "1"]),
            ("type", {"type": "array", "items": {"type": "string"}}, [[], ["ok"]], [["ok", 1]]),
            ("additionalProperties", nested, [[], [{"value": 1}]], [[{"value": 1, "extra": 2}]]),
            ("type", nested, [[{"value": 1}]], [[{"value": "wrong"}]]),
        )
        for keyword, schema, valid, invalid in cases:
            for value in valid:
                with self.subTest(keyword=keyword, schema=schema, valid=value):
                    validate_output(value, schema)
            for value in invalid:
                with self.subTest(keyword=keyword, schema=schema, invalid=value):
                    with self.assertRaises(ValidationError) as caught:
                        validate_output(value, schema)
                    self.assertEqual(caught.exception.validator, keyword)

    def test_open_optional_and_nullable_properties_remain_valid(self):
        schema = {"type": "object", "properties": {"note": {"type": ["string", "null"]}}}
        for value in ({}, {"note": "ok"}, {"note": None}, {"extra": 1}, {"note": None, "extra": 1}):
            with self.subTest(value=value):
                validate_output(value, schema)
        with self.assertRaises(ValidationError) as caught:
            validate_output({"note": 1}, schema)
        self.assertEqual(caught.exception.json_path, "$.note")
        self.assertEqual(caught.exception.validator, "type")

    def test_invalid_schema_is_rejected_before_result_validation(self):
        for schema in ({"type": "not-a-json-type"}, {"type": "object", "required": "status"}):
            with self.subTest(schema=schema), self.assertRaises(SchemaError):
                validate_output({}, schema)


class MetadataTests(unittest.TestCase):
    def test_check_counts_follow_catalogue_without_packages(self):
        original = validation_rules.RULE_IDS
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            for rules in (original, (*original, "test_extra_validation_rule")):
                with self.subTest(count=len(rules)), patch.object(validation_rules, "RULE_IDS", rules), \
                        patch("hanok_generator.llm.tools.run_job") as worker:
                    box = Toolbox(output)
                    self.assertEqual(box.service.meta()["validation_check_count"], len(rules))
                    assert_check_descriptions(self, box, len(rules))
                    worker.assert_not_called()
                    self.assertFalse(output.exists())


class ToolboxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="hanok-llm-tests-")
        root = Path(cls.temp.name)
        cls.output = root / "output"
        cls.box = Toolbox(cls.output)
        # Floats and spelled-out defaults on purpose: the tool must still build the example's package.
        loose = dict(EXAMPLES["double_r3"], outer_mm=[463.0, 586.0], lattice_per_leaf=[2.0, 4.0],
                     picture={"size_mm": [297, 420]}, stock_mm=[1220, 900, 20])
        with ThreadPoolExecutor(max_workers=2) as pool:
            built = pool.submit(cls.box.call, "build_package", loose)
            direct = pool.submit(run_job, EXAMPLES["double_r3"], root / "direct")
            cls.built, cls.direct = built.result(), direct.result()

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_definitions_in_every_format(self):
        self.assertEqual(set(FORMATS), {"mcp", "openai", "openai-responses", "anthropic"})
        mcp = self.box.definitions("mcp")
        self.assertEqual([t["name"] for t in mcp], NAMES)
        for tool in mcp:
            with self.subTest(tool=tool["name"]):
                self.assertEqual((tool["inputSchema"]["type"], tool["outputSchema"]["type"]), ("object", "object"))
                self.assertEqual(tool["annotations"]["readOnlyHint"], tool["name"] != "build_package")
                # English for every model, and none of the schema constructs some function-calling APIs refuse.
                text = json.dumps(tool, ensure_ascii=False)
                self.assertTrue(text.isascii())
                for keyword in ('"oneOf"', '"anyOf"', '"allOf"', '"prefixItems"', '"if"', '"$ref"'):
                    self.assertNotIn(keyword, text)
        check = mcp[1]
        # The panel is a size basis a model can pick, with every field described.
        panel = check["inputSchema"]["properties"]["artwork"]
        self.assertEqual(set(panel["properties"]), {"size_mm", "thickness_mm", "cover_mm", "fit_mm", "spacer_mm"})
        self.assertEqual(panel["required"], ["size_mm"])
        self.assertIn("cannot be combined with picture", panel["description"])
        self.assertEqual(self.box.definitions("openai")[1], {"type": "function", "function": dict(
            name="check_design", description=check["description"], parameters=check["inputSchema"], strict=False)})
        self.assertEqual(self.box.definitions("openai-responses")[1], dict(
            type="function", name="check_design", description=check["description"],
            parameters=check["inputSchema"], strict=False))
        self.assertEqual(self.box.definitions("anthropic")[1], dict(
            name="check_design", description=check["description"], input_schema=check["inputSchema"]))
        with self.assertRaises(ValueError):
            self.box.definitions("gemini")

    def test_examples_are_the_example_files(self):
        files = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in (ROOT / "examples").glob("*.json")
                 if p.name != "built_packages.json"}
        self.assertEqual(EXAMPLES, files)

    def test_requests_are_written_like_the_web_form(self):
        meta = self.box.service.meta()
        for name, request in EXAMPLES.items():
            with self.subTest(example=name):
                self.assertEqual(canonical_request(request, meta), request)
        spelled = dict(type="single", hinge_side="left", outer_mm=[420.0, 900], lattice_per_leaf=[0, 0],
                       preset="standard_v1", picture=None, stock_mm=[1220.0, 900, 20], schema_version=1)
        self.assertEqual(canonical_request(spelled, meta), EXAMPLES["single_empty"])
        # standard_v1 has no picture by default, so a picture stays, with the margin the form would add.
        kept = canonical_request(dict(EXAMPLES["double_600_800"], picture={"size_mm": [297.0, 420]}), meta)
        self.assertEqual(kept["picture"], {"size_mm": [297, 420], "margin_mm": 10})
        # Mistakes are left for resolve() to name, never repaired silently.
        wrong = canonical_request(dict(EXAMPLES["double_600_800"], hinge_side="left", colour="red"), meta)
        self.assertEqual((wrong["hinge_side"], wrong["colour"]), ("left", "red"))
        # A board is left out only when it is the default of the request's own preset.
        board = dict(type="double", outer_mm=[463, 586], lattice_per_leaf=[2, 4], preset="standard_4x8_v1")
        self.assertEqual(canonical_request(dict(board, stock_mm=[2400.0, 1200, 20]), meta), board)
        for kept in (dict(board, preset="standard_v1", stock_mm=[2400, 1200, 20]), dict(board, stock_mm=[1220, 900, 20])):
            self.assertEqual(canonical_request(kept, meta)["stock_mm"], kept["stock_mm"])
        # A frame-type request is written the same way: the panel size always, and a panel field
        # only when it differs from the default.
        spelled_panel = dict(ARTWORK, artwork=dict(size_mm=[420.0, 594], thickness_mm=3.0, cover_mm=8, fit_mm=1,
                                                   spacer_mm=3), stock_mm=[2400, 1200, 20])
        self.assertEqual(canonical_request(spelled_panel, meta), ARTWORK)
        changed = canonical_request(dict(ARTWORK, artwork=dict(size_mm=[420, 594], cover_mm=12.0)), meta)
        self.assertEqual(changed["artwork"], {"size_mm": [420, 594], "cover_mm": 12})
        # describe_generator names that default board for each preset.
        presets = {p["id"]: p for p in self.box.call("describe_generator").data["presets"]}
        for name, want in (("standard_4x8_v1", [[2400, 1200, 20], 10, 12]), ("standard_v1", [[1220, 900, 20], 20, 12])):
            self.assertEqual([presets[name][k] for k in ("default_stock_mm", "edge_margin_mm", "part_gap_mm")], want)

    def test_check_design_returns_the_design_or_the_rule_to_fix(self):
        r3 = self.box.call("check_design", EXAMPLES["double_r3"])
        self.assertFalse(r3.is_error, r3.data)
        self.assertEqual((r3.data["status"], r3.data["lattice"]["crossings_total"]), ("RESOLVED_NOT_DXF_VALIDATED", 16))
        self.assertIn(self.built.data["package_id"], r3.data["same_design_packages"])
        inner = self.box.call("check_design", EXAMPLES["double_inner_r3"])
        self.assertEqual((inner.data["size"]["basis"], inner.data["size"]["outer_mm"]), ("inner", [463, 586]))
        dense = self.box.call("check_design", dict(EXAMPLES["double_r3"], lattice_per_leaf=[30, 4]))
        self.assertTrue(dense.is_error)
        self.assertEqual((dense.data["rule_id"], dense.data["where"], dense.data["stage"]),
                         ("lattice.positive_gap", "lattice", "geometry"))
        self.assertIn("vertical_per_leaf", dense.data["suggestion"])
        self.assertIn("suggestion gives the largest bar count", dense.data["hint"])
        hinge = self.box.call("check_design", dict(EXAMPLES["double_600_800"], hinge_side="left"))
        self.assertEqual((hinge.is_error, hinge.data["rule_id"]), (True, "input.hinge_side"))
        self.assertIn("double window must not have hinge_side", hinge.data["hint"])

    def test_check_design_reports_the_panel_and_its_rules(self):
        panel = self.box.call("check_design", ARTWORK)
        self.assertFalse(panel.is_error, panel.data)
        self.assertEqual(panel.data["size"]["basis"], "artwork")
        self.assertEqual(panel.data["artwork"],
                         dict(size_mm=[420, 594], sheet=[32, 32, 452, 626], cover_mm=8, fit_mm=1, spacer_mm=3,
                              thickness_mm=3, back_frame_member_mm=31, back_frame_opening_mm=[422, 596]))
        self.assertEqual(panel.data["totals"]["parts"], 28)
        self.assertIsNone(self.box.call("check_design", EXAMPLES["double_r3"]).data["artwork"])
        described = self.box.call("describe_generator").data
        self.assertIn("artwork", described["size_basis"])
        self.assertEqual(described["defaults"]["artwork_mm"],
                         {"thickness_mm": 3, "cover_mm": 8, "fit_mm": 1, "spacer_mm": 3})
        # Each refusal carries the rule, the numbers and a fix a model can act on.
        for change, rule, words in ((dict(size_mm=[420, 594], cover_mm=31), "artwork.back_member_width", "cover"),
                                    (dict(size_mm=[420, 594], thickness_mm=18), "artwork.depth_within_stock", "spacer"),
                                    (dict(size_mm=[420, 594], cover_mm=1), "artwork.cover_hides_edge", "fit")):
            with self.subTest(rule=rule):
                refused = self.box.call("check_design", dict(ARTWORK, artwork=change))
                self.assertTrue(refused.is_error, refused.data)
                self.assertEqual((refused.data["rule_id"], refused.data["where"]), (rule, "artwork"))
                self.assertIn(words, refused.data["hint"])
                self.assertTrue(refused.data["suggestion"]["artwork"], refused.data)
        for extra, rule in ((dict(picture={"size_mm": [297, 420]}), "input.artwork_picture"),
                            (dict(preset="hanok_A3_portrait_R3"), "input.preset_artwork"),
                            (dict(outer_mm=[484, 658]), "input.size_basis")):
            with self.subTest(rule=rule):
                refused = self.box.call("check_design", dict(ARTWORK, **extra))
                self.assertEqual((refused.is_error, refused.data["rule_id"]), (True, rule))
                self.assertTrue(refused.data["hint"])

    def test_a_model_can_follow_a_suggestion(self):
        wide = self.box.call("check_design", dict(EXAMPLES["double_r3"], outer_mm=[600, 586]))
        self.assertEqual(wide.data["rule_id"], "leaf.aspect_ratio")
        bounds = wide.data["suggestion"]["outer_mm"]
        self.assertEqual(set(bounds), {"width_at_most", "height_at_least"})
        narrower = self.box.call("check_design", dict(EXAMPLES["double_r3"], outer_mm=[bounds["width_at_most"], 586]))
        self.assertFalse(narrower.is_error, narrower.data)

    def test_descriptions_match_reports_and_preserve_package_totals(self):
        report = json.loads((Path(self.built.data["folder"]) / "validation_report.json").read_text(encoding="utf-8"))
        count = len(report["checks"])
        self.assertEqual(self.box.service.meta()["validation_check_count"], count)
        assert_check_descriptions(self, self.box, count)
        # A newer engine's advertised count must not overwrite an older package's totals.
        with patch.object(validation_rules, "RULE_IDS", (*validation_rules.RULE_IDS, "test_extra_validation_rule")):
            box = Toolbox(self.output)
            assert_check_descriptions(self, box, count + 1)
            package = box.call("get_package", {"package_id": self.built.data["package_id"]})
            self.assertFalse(package.is_error, package.data)
            self.assertEqual(package.data["checks"], {"passed": report["checks_passed"], "total": count})

    def test_build_matches_the_cli_package(self):
        self.assertFalse(self.built.is_error, self.built.data)
        data = self.built.data
        self.assertEqual(data["package_id"], self.direct["package_id"])
        self.assertEqual(data["request"], EXAMPLES["double_r3"])
        self.assertEqual((data["status"], data["checks"], data["manufacturing_status"]),
                         ("PASS", {"passed": 71, "total": 71}, "PENDING"))
        self.assertEqual((len(data["pending"]), data["drawings"]), (6, list(DRAWINGS)))

    def test_a_build_reports_its_stages(self):
        stages = []
        again = self.box.call("build_package", EXAMPLES["double_r3"],
                              progress=lambda done, total, message: stages.append((done, total, message)))
        self.assertEqual((again.data["package_id"], again.data["already_existed"]), (self.built.data["package_id"], True))
        self.assertEqual([(done, total) for done, total, _ in stages], [(0, 3), (1, 3), (2, 3), (3, 3)])
        self.assertEqual(stages[1][2],
                         "Building in a worker: saving the DXF, drawing the PNGs and running validation checks")

    def test_package_tools_accept_an_id_prefix(self):
        package_id = self.built.data["package_id"]
        listed = self.box.call("list_packages", {"limit": 5})
        self.assertEqual([p["package_id"] for p in listed.data["packages"]], [package_id])
        shown = self.box.call("get_package", {"package_id": package_id[:8]})
        self.assertFalse(shown.is_error, shown.data)
        self.assertEqual((shown.data["package_id"], shown.data["failed_checks"], len(shown.data["files"])),
                         (package_id, [], 37))
        self.assertEqual(self.box.call("verify_package", {"package_id": package_id}).data["status"], "PASS")
        drawing = self.box.call("get_drawing", {"package_id": package_id[:12], "drawing": "assembly"})
        self.assertFalse(drawing.is_error, drawing.data)
        (mime, png), = drawing.images
        self.assertEqual((mime, png[:8]), ("image/png", PNG))
        self.assertLessEqual(drawing.data["width"], 480)
        cases = [("get_package", {"package_id": "0" * 8}, "package.not_found"),
                 ("get_package", {"package_id": "xyz"}, "tool.arguments"),
                 ("list_packages", {"limit": 0}, "tool.arguments"),
                 ("list_packages", {"limit": 3, "sort": "size"}, "tool.arguments"),
                 ("get_drawing", {"package_id": package_id, "drawing": "roof"}, "tool.arguments")]
        for name, arguments, rule in cases:
            with self.subTest(tool=name, arguments=arguments):
                result = self.box.call(name, arguments)
                self.assertEqual((result.is_error, result.data["rule_id"]), (True, rule))
                self.assertTrue(result.data["hint"])

    def test_read_package_file_in_pages(self):
        package_id = self.built.data["package_id"]
        folder = self.output / "packages" / package_id
        readme = self.box.call("read_package_file", {"package_id": package_id[:8], "path": "README.txt"})
        self.assertFalse(readme.is_error, readme.data)
        self.assertEqual((readme.data["text"], readme.data["truncated"], readme.data["next_offset"]),
                         ((folder / "README.txt").read_text(encoding="utf-8"), False, None))
        whole = (folder / "design_spec.json").read_text(encoding="utf-8")
        self.assertGreater(len(whole), MAX_TEXT)
        first = self.box.call("read_package_file", {"package_id": package_id, "path": "design_spec.json"}).data
        rest = self.box.call("read_package_file", {"package_id": package_id, "path": "design_spec.json",
                                                   "offset": first["next_offset"]}).data
        self.assertEqual((first["truncated"], rest["truncated"], first["text"] + rest["text"]), (True, False, whole))
        source = self.box.call("read_package_file", {"package_id": package_id, "path": "source/hanok_generator/model.py"})
        self.assertIn("def resolve", source.data["text"])
        for arguments, rule in (({"path": "03_assembly_reference.png"}, "tool.arguments"),
                                ({"path": "window.dxf"}, "tool.arguments"),
                                ({"path": "notes.txt"}, "package.file_not_found"),
                                ({"path": "README.txt", "offset": -1}, "tool.arguments")):
            with self.subTest(arguments=arguments):
                result = self.box.call("read_package_file", dict(arguments, package_id=package_id))
                self.assertEqual((result.is_error, result.data["rule_id"]), (True, rule))

    def test_results_match_their_output_schemas(self):
        schemas = {tool["name"]: tool["outputSchema"] for tool in self.box.definitions("mcp")}
        package_id = self.built.data["package_id"]
        calls = [("describe_generator", {}, False), ("check_design", EXAMPLES["double_r3"], False),
                 ("check_design", dict(EXAMPLES["double_r3"], lattice_per_leaf=[30, 4]), True),
                 ("list_packages", {}, False), ("get_package", {"package_id": package_id}, False),
                 ("verify_package", {"package_id": package_id}, False),
                 ("get_package", {"package_id": "0" * 8}, True),
                 ("get_drawing", {"package_id": package_id, "drawing": "nesting"}, False),
                 ("read_package_file", {"package_id": package_id, "path": "parts_manifest.csv"}, False)]
        results = [(name, self.box.call(name, arguments), error) for name, arguments, error in calls]
        results.append(("build_package", self.built, False))
        # Independent examples keep an emptied properties map from silently weakening this contract.
        wrong_fields = dict(describe_generator=("makes", 0), check_design=("status", 0),
                            build_package=("status", 0), list_packages=("total", True),
                            get_package=("package_id", 0), verify_package=("files", True),
                            get_drawing=("width", True), read_package_file=("next_offset", "wrong"))
        for name, result, error in results:
            schema = schemas[name]
            with self.subTest(tool=name, error=result.is_error):
                self.assertEqual(result.is_error, error, result.data)
                validate_output(result.data, schema)
            if not result.is_error:
                field, wrong = wrong_fields[name]
                with self.subTest(tool=name, mutation=field):
                    self.assertIn(field, result.data)
                    with self.assertRaises(ValidationError) as caught:
                        validate_output(dict(result.data, **{field: wrong}), schema)
                    self.assertEqual(caught.exception.validator, "type")
                    self.assertEqual(list(caught.exception.path), [field])
            if name in ("check_design", "build_package", "verify_package"):
                with self.subTest(tool=name, error=result.is_error, mutation="missing status"):
                    missing = {key: value for key, value in result.data.items() if key != "status"}
                    with self.assertRaises(ValidationError) as caught:
                        validate_output(missing, schema)
                    self.assertEqual(caught.exception.validator, "required")

    def test_a_failed_build_names_the_failed_checks(self):
        # Passes the pre-check; the saved DXF then shows pockets running into each other (as in the web tests).
        result = self.box.call("build_package", dict(EXAMPLES["double_r3"], lattice_per_leaf=[12, 4]))
        self.assertTrue(result.is_error)
        self.assertEqual(result.data["rule_id"], "geometry.validation")
        self.assertIn("distinct_machining_regions_separated", {c["rule_id"] for c in result.data["validation"]["failed"]})
        self.assertIn("reliefs", result.data["hint"])
        schema = next(t["outputSchema"] for t in self.box.definitions("mcp") if t["name"] == "build_package")
        with self.subTest(tool="build_package", error=result.is_error):
            validate_output(result.data, schema)

    def test_bad_calls_come_back_as_results(self):
        with self.assertRaises(KeyError):
            self.box.call("delete_everything", {})
        cases = [(["not", "an", "object"], "tool.arguments"),
                 (dict(EXAMPLES["double_r3"], outer_mm=[float("nan"), 586]), "input.number"),
                 (dict(EXAMPLES["double_r3"], note="x" * 70000), "input.too_large"),
                 (dict(EXAMPLES["double_r3"], colour="red"), "input.unknown_fields")]
        for arguments, rule in cases:
            with self.subTest(rule=rule):
                self.assertEqual(self.box.call("check_design", arguments).data["rule_id"], rule)

    def test_cli_runs_a_tool_and_saves_its_image(self):
        with tempfile.TemporaryDirectory() as images:
            done = subprocess.run([sys.executable, "-m", "hanok_generator.llm", "call", "get_drawing",
                                   json.dumps({"package_id": self.built.data["package_id"][:8], "drawing": "opening"}),
                                   "--output", str(self.output), "--image-dir", images],
                                  capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=ROOT)
            self.assertEqual(done.returncode, 0, done.stderr)
            reply = json.loads(done.stdout)
            (image,) = reply["images"]
            self.assertEqual((reply["is_error"], image["mime_type"]), (False, "image/png"))
            self.assertEqual(Path(image["path"]).read_bytes()[:8], PNG)

    def test_llm_layer_stays_out_of_packages(self):
        self.assertFalse([name for name, _ in source_files() if name.startswith(("llm/", "web/"))])


class McpServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="hanok-mcp-tests-")
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / "output"

    def session(self, *lines):
        """Send the lines (dicts and lists as JSON), close stdin, and return every message the server wrote;
        each stdout line must be a JSON-RPC message."""
        text = "".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines)
        done = subprocess.run([sys.executable, "-m", "hanok_generator.llm.mcp", "--output", str(self.output)],
                              input=text.encode("utf-8"), capture_output=True, timeout=240, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stderr.decode())
        return [json.loads(line) for line in done.stdout.decode("utf-8").splitlines()]

    def test_handshake_tools_and_errors(self):
        dense = dict(EXAMPLES["double_r3"], lattice_per_leaf=[30, 4])
        replies = self.session(
            initialize("2025-06-18"), INITIALIZED, rpc(2, "tools/list"),
            rpc(3, "tools/call", {"name": "describe_generator", "arguments": {}}),
            rpc(4, "tools/call", {"name": "check_design", "arguments": dense}),
            rpc(5, "ping"), rpc(6, "resources/list"), rpc(7, "tools/call", {"name": "nope", "arguments": {}}),
            "{not json", rpc(8, "tools/call", {"name": "check_design", "arguments": [1]}),
            [rpc(9, "ping"), rpc(10, "ping")])
        self.assertEqual(len(replies), 10)  # no reply to the notification; one list for the batch
        batch = next(r for r in replies if isinstance(r, list))
        self.assertEqual([r["id"] for r in batch], [9, 10])
        by_id = {r["id"]: r for r in replies if isinstance(r, dict)}
        init = by_id[1]["result"]
        self.assertEqual((init["protocolVersion"], init["serverInfo"]["name"]), ("2025-06-18", "hanok-window"))
        self.assertEqual(init["capabilities"], {"tools": {"listChanged": False}})
        self.assertIn("read_package_file", init["instructions"])
        tools = by_id[2]["result"]["tools"]
        self.assertEqual([t["name"] for t in tools], NAMES)
        self.assertTrue(all(t["outputSchema"]["type"] == "object" for t in tools))
        described = by_id[3]["result"]
        self.assertFalse(described["isError"])
        self.assertEqual(json.loads(described["content"][0]["text"]), described["structuredContent"])
        self.assertEqual(described["structuredContent"]["examples"], EXAMPLES)
        checked = by_id[4]["result"]
        self.assertEqual((checked["isError"], checked["structuredContent"]["rule_id"]), (True, "lattice.positive_gap"))
        self.assertEqual(by_id[5]["result"], {})
        self.assertEqual([by_id[k]["error"]["code"] for k in (6, 7, None, 8)], [-32601, -32602, -32700, -32602])

    def test_protocol_versions(self):
        for asked, expected in (("2024-11-05", "2024-11-05"), ("2025-11-25", "2025-11-25"),
                                ("1999-01-01", PROTOCOL_VERSIONS[0])):
            with self.subTest(asked=asked):
                replies = self.session(initialize(asked), INITIALIZED,
                                       rpc(2, "tools/call", {"name": "list_packages", "arguments": {}}))
                self.assertEqual(replies[0]["result"]["protocolVersion"], expected)
                # structuredContent came with 2025-06-18; older clients read the text block.
                self.assertEqual("structuredContent" in replies[1]["result"], expected >= "2025-06-18")

    def test_ping_is_answered_while_a_build_runs(self):
        replies = self.session(initialize("2025-11-25"), INITIALIZED,
                               rpc(2, "tools/call", {"name": "build_package", "arguments": EXAMPLES["single_empty"],
                                                     "_meta": {"progressToken": "build-1"}}),
                               rpc(3, "ping"))
        ids = [r.get("id") for r in replies]
        built = ids.index(2)
        self.assertLess(ids.index(3), built)  # the ping did not wait for the build
        progress = [(i, r["params"]) for i, r in enumerate(replies) if r.get("method") == "notifications/progress"]
        self.assertEqual([p["progress"] for _, p in progress], [0, 1, 2, 3])
        self.assertEqual({p["progressToken"] for _, p in progress}, {"build-1"})
        self.assertLess(progress[-1][0], built)
        self.assertFalse(replies[built]["result"]["isError"], replies[built]["result"]["content"][0]["text"])

    def test_a_cancelled_call_gets_no_reply(self):
        replies = self.session(initialize("2025-11-25"), INITIALIZED,
                               rpc(2, "tools/call", {"name": "build_package", "arguments": EXAMPLES["single_empty"]}),
                               {"jsonrpc": "2.0", "method": "notifications/cancelled",
                                "params": {"requestId": 2, "reason": "user stopped it"}},
                               rpc(3, "ping"))
        self.assertEqual([r.get("id") for r in replies], [1, 3])

    def test_build_look_and_read_over_stdio(self):
        replies = self.session(initialize("2025-11-25"), INITIALIZED,
                               rpc(2, "tools/call", {"name": "build_package", "arguments": EXAMPLES["single_empty"]}))
        built = replies[1]["result"]
        self.assertFalse(built["isError"], built["content"][0]["text"])
        package_id = built["structuredContent"]["package_id"]
        replies = self.session(initialize("2025-11-25"), INITIALIZED, rpc(2, "tools/call", {
            "name": "get_drawing", "arguments": {"package_id": package_id[:8], "drawing": "nesting"}}),
            rpc(3, "tools/call", {"name": "read_package_file",
                                  "arguments": {"package_id": package_id[:8], "path": "parts_manifest.csv"}}))
        by_id = {r["id"]: r["result"] for r in replies}
        content = by_id[2]["content"]
        self.assertEqual([c["type"] for c in content], ["text", "image"])
        self.assertEqual((content[1]["mimeType"], base64.b64decode(content[1]["data"])[:8]), ("image/png", PNG))
        self.assertIn("part_id", by_id[3]["structuredContent"]["text"])


class ProcessTests(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, "-m", "hanok_generator.llm", *args], input=stdin,
                              capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=ROOT)

    def test_tools_never_load_the_builder(self):
        done = subprocess.run([sys.executable, "-c", ISOLATION, json.dumps(EXAMPLES["single_empty"])],
                              capture_output=True, text=True, encoding="utf-8", timeout=240, cwd=ROOT)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), dict(errors=[False, False], builder=False, ezdxf=False))

    def test_cli_exports_definitions_and_calls_tools(self):
        exported = self.run_cli("tools", "--format", "anthropic")
        self.assertEqual(exported.returncode, 0, exported.stderr)
        self.assertEqual([t["name"] for t in json.loads(exported.stdout)], NAMES)
        with tempfile.TemporaryDirectory() as tmp:
            dense = json.dumps(dict(EXAMPLES["double_r3"], lattice_per_leaf=[30, 4]))
            refused = self.run_cli("call", "check_design", "-", "--output", tmp, stdin=dense)
            self.assertEqual(refused.returncode, 1, refused.stderr)
            reply = json.loads(refused.stdout)
            self.assertEqual((reply["tool"], reply["is_error"], reply["result"]["rule_id"]),
                             ("check_design", True, "lattice.positive_gap"))
            listed = self.run_cli("call", "list_packages", "--output", tmp)
            self.assertEqual((listed.returncode, json.loads(listed.stdout)["result"]["total"]), (0, 0))
            self.assertEqual(self.run_cli("call", "nope", "--output", tmp).returncode, 2)
            self.assertEqual(self.run_cli("call", "check_design", "{bad", "--output", tmp).returncode, 2)


if __name__ == "__main__":
    unittest.main()
