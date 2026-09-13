"""LLM tools: definitions for every format, canonical requests, tool results, the CLI runner, the MCP stdio
server (handshake, version negotiation, tool calls, error codes, image content) and process isolation."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from hanok_generator.jobs import run_job
from hanok_generator.llm import FORMATS, Toolbox
from hanok_generator.llm.mcp import PROTOCOL_VERSIONS
from hanok_generator.llm.tools import DRAWINGS, EXAMPLES, canonical_request
from hanok_generator.package import source_files

ROOT = Path(__file__).parent.parent
NAMES = ["describe_generator", "check_design", "build_package", "list_packages", "get_package", "verify_package",
         "get_drawing"]
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
                self.assertEqual(tool["inputSchema"]["type"], "object")
                self.assertEqual(tool["annotations"]["readOnlyHint"], tool["name"] != "build_package")
                # English for every model, and none of the schema constructs some function-calling APIs refuse.
                text = json.dumps(tool, ensure_ascii=False)
                self.assertTrue(text.isascii())
                for keyword in ('"oneOf"', '"anyOf"', '"allOf"', '"prefixItems"', '"if"', '"$ref"'):
                    self.assertNotIn(keyword, text)
        check = mcp[1]
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
        self.assertIn("fewer bars", dense.data["hint"])
        hinge = self.box.call("check_design", dict(EXAMPLES["double_600_800"], hinge_side="left"))
        self.assertEqual((hinge.is_error, hinge.data["rule_id"]), (True, "input.hinge_side"))
        self.assertIn("double window must not have hinge_side", hinge.data["hint"])

    def test_build_matches_the_cli_package(self):
        self.assertFalse(self.built.is_error, self.built.data)
        data = self.built.data
        self.assertEqual(data["package_id"], self.direct["package_id"])
        self.assertEqual(data["request"], EXAMPLES["double_r3"])
        self.assertEqual((data["status"], data["checks"], data["manufacturing_status"]),
                         ("PASS", {"passed": 67, "total": 67}, "PENDING"))
        self.assertEqual((len(data["pending"]), data["drawings"]), (6, list(DRAWINGS)))

    def test_package_tools_accept_an_id_prefix(self):
        package_id = self.built.data["package_id"]
        listed = self.box.call("list_packages", {"limit": 5})
        self.assertEqual([p["package_id"] for p in listed.data["packages"]], [package_id])
        shown = self.box.call("get_package", {"package_id": package_id[:8]})
        self.assertFalse(shown.is_error, shown.data)
        self.assertEqual((shown.data["package_id"], shown.data["failed_checks"], len(shown.data["files"])),
                         (package_id, [], 34))
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

    def test_a_failed_build_names_the_failed_checks(self):
        # Passes the pre-check; the saved DXF then shows pockets running into each other (as in the web tests).
        result = self.box.call("build_package", dict(EXAMPLES["double_r3"], lattice_per_leaf=[12, 4]))
        self.assertTrue(result.is_error)
        self.assertEqual(result.data["rule_id"], "geometry.validation")
        self.assertIn("distinct_machining_regions_separated", {c["rule_id"] for c in result.data["validation"]["failed"]})
        self.assertIn("reliefs", result.data["hint"])

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
                                  capture_output=True, text=True, timeout=120, cwd=ROOT)
            self.assertEqual(done.returncode, 0, done.stderr)
            reply = json.loads(done.stdout)
            (image,) = reply["images"]
            self.assertEqual((reply["is_error"], image["mime_type"]), (False, "image/png"))
            self.assertEqual(Path(image["path"]).read_bytes()[:8], PNG)

    def test_llm_layer_stays_out_of_packages(self):
        self.assertFalse([name for name, _ in source_files() if name.startswith("llm/")])


class McpServerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="hanok-mcp-tests-")
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name) / "output"

    def session(self, *lines):
        """Send the lines (dicts and lists as JSON), close stdin, and return every reply; each stdout line must
        be a JSON-RPC message."""
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
        self.assertEqual([r["id"] for r in replies[-1]], [9, 10])
        by_id = {r["id"]: r for r in replies[:-1]}
        init = by_id[1]["result"]
        self.assertEqual((init["protocolVersion"], init["serverInfo"]["name"]), ("2025-06-18", "hanok-window"))
        self.assertEqual(init["capabilities"], {"tools": {"listChanged": False}})
        self.assertIn("check_design", init["instructions"])
        self.assertEqual([t["name"] for t in by_id[2]["result"]["tools"]], NAMES)
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

    def test_build_and_look_at_a_drawing(self):
        replies = self.session(initialize("2025-11-25"), INITIALIZED,
                               rpc(2, "tools/call", {"name": "build_package", "arguments": EXAMPLES["single_empty"]}))
        built = replies[1]["result"]
        self.assertFalse(built["isError"], built["content"][0]["text"])
        package_id = built["structuredContent"]["package_id"]
        replies = self.session(initialize("2025-11-25"), INITIALIZED, rpc(2, "tools/call", {
            "name": "get_drawing", "arguments": {"package_id": package_id[:8], "drawing": "nesting"}}))
        content = replies[1]["result"]["content"]
        self.assertEqual([c["type"] for c in content], ["text", "image"])
        self.assertEqual((content[1]["mimeType"], base64.b64decode(content[1]["data"])[:8]), ("image/png", PNG))


class ProcessTests(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run([sys.executable, "-m", "hanok_generator.llm", *args], input=stdin,
                              capture_output=True, text=True, timeout=120, cwd=ROOT)

    def test_tools_never_load_the_builder(self):
        done = subprocess.run([sys.executable, "-c", ISOLATION, json.dumps(EXAMPLES["single_empty"])],
                              capture_output=True, text=True, timeout=240, cwd=ROOT)
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
