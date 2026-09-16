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

from hanok_generator.jobs import run_job
from hanok_generator.llm import FORMATS, Toolbox
from hanok_generator.llm.mcp import PROTOCOL_VERSIONS
from hanok_generator.llm.tools import DRAWINGS, EXAMPLES, MAX_TEXT, canonical_request
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


def conforms(value, schema):
    """A small JSON Schema check for the keywords the output schemas use: type, properties, required, items."""
    kinds = schema.get("type")
    if kinds is not None:
        simple = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
        allowed = kinds if isinstance(kinds, list) else [kinds]
        if not any(type(value) is int if kind == "integer" else type(value) in (int, float) if kind == "number"
                   else type(value) is simple[kind] for kind in allowed):
            return False
    if isinstance(value, dict):
        return all(key in value for key in schema.get("required", [])) and \
            all(conforms(value[key], sub) for key, sub in schema.get("properties", {}).items() if key in value)
    if isinstance(value, list) and "items" in schema:
        return all(conforms(item, schema["items"]) for item in value)
    return True


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

    def test_a_model_can_follow_a_suggestion(self):
        wide = self.box.call("check_design", dict(EXAMPLES["double_r3"], outer_mm=[600, 586]))
        self.assertEqual(wide.data["rule_id"], "leaf.aspect_ratio")
        bounds = wide.data["suggestion"]["outer_mm"]
        self.assertEqual(set(bounds), {"width_at_most", "height_at_least"})
        narrower = self.box.call("check_design", dict(EXAMPLES["double_r3"], outer_mm=[bounds["width_at_most"], 586]))
        self.assertFalse(narrower.is_error, narrower.data)

    def test_build_matches_the_cli_package(self):
        self.assertFalse(self.built.is_error, self.built.data)
        data = self.built.data
        self.assertEqual(data["package_id"], self.direct["package_id"])
        self.assertEqual(data["request"], EXAMPLES["double_r3"])
        self.assertEqual((data["status"], data["checks"], data["manufacturing_status"]),
                         ("PASS", {"passed": 70, "total": 70}, "PENDING"))
        self.assertEqual((len(data["pending"]), data["drawings"]), (6, list(DRAWINGS)))

    def test_a_build_reports_its_stages(self):
        stages = []
        again = self.box.call("build_package", EXAMPLES["double_r3"],
                              progress=lambda done, total, message: stages.append((done, total)))
        self.assertEqual((again.data["package_id"], again.data["already_existed"]), (self.built.data["package_id"], True))
        self.assertEqual(stages, [(0, 3), (1, 3), (2, 3), (3, 3)])

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
        package_id = self.built.data["package_id"]
        calls = [("describe_generator", {}), ("check_design", EXAMPLES["double_r3"]),
                 ("check_design", dict(EXAMPLES["double_r3"], lattice_per_leaf=[30, 4])),
                 ("list_packages", {}), ("get_package", {"package_id": package_id}),
                 ("verify_package", {"package_id": package_id}), ("get_package", {"package_id": "0" * 8}),
                 ("get_drawing", {"package_id": package_id, "drawing": "nesting"}),
                 ("read_package_file", {"package_id": package_id, "path": "parts_manifest.csv"})]
        results = [(name, self.box.call(name, arguments)) for name, arguments in calls]
        results.append(("build_package", self.built))
        for name, result in results:
            with self.subTest(tool=name, error=result.is_error):
                self.assertTrue(conforms(result.data, self.box.tools[name].output), result.data)

    def test_a_failed_build_names_the_failed_checks(self):
        # Passes the pre-check; the saved DXF then shows pockets running into each other (as in the web tests).
        result = self.box.call("build_package", dict(EXAMPLES["double_r3"], lattice_per_leaf=[12, 4]))
        self.assertTrue(result.is_error)
        self.assertEqual(result.data["rule_id"], "geometry.validation")
        self.assertIn("distinct_machining_regions_separated", {c["rule_id"] for c in result.data["validation"]["failed"]})
        self.assertIn("reliefs", result.data["hint"])
        self.assertTrue(conforms(result.data, self.box.tools["build_package"].output))

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
