"""Web interface: CLI parity, error mapping, request limits, builds, package files, isolation,
and the background server behind web.sh."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import http.client
import io
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile

from hanok_generator import __version__, cli, web
from hanok_generator.jobs import run_job
from hanok_generator.package import digest, source_files
from hanok_generator.web import dwg
from hanok_generator.web.server import Handler, make_server

if os.name == "posix":  # web.control imports fcntl; only BackgroundServerTests use it, and they skip elsewhere
    from hanok_generator.web.control import Record

HERE = Path(__file__).parent
STATIC = Path(web.__file__).parent / "static"
NODE_RUNNER = """
import { compose, formFromRequest, stockAfterPresetChange } from "./app.js";
let input = "";
for await (const chunk of process.stdin) input += chunk;
const { meta, requests, forms, switches } = JSON.parse(input);
process.stdout.write(JSON.stringify({
  requests: requests.map((r) => compose(formFromRequest(r, meta), meta)),
  forms: forms.map((f) => compose(f, meta)),
  switches: switches.map(([form, preset]) => stockAfterPresetChange(form, preset, meta)),
}));
"""
EXAMPLE_FILES = {p.stem: p for p in sorted((HERE.parent / "examples").glob("*.json")) if p.name != "built_packages.json"}
EXAMPLES = {name: json.loads(p.read_text(encoding="utf-8")) for name, p in EXAMPLE_FILES.items()}
R3 = EXAMPLES["double_r3"]
# Runs in a fresh interpreter: only a job's worker process (hash seed 0, time
# limit) may import the builder, never the server process.
ISOLATION = """
import http.client, json, sys, tempfile, threading, time
from hanok_generator.web.server import make_server

def call(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=120)
    conn.request(method, path, body, {"Content-Type": "application/json"} if body else {})
    response = conn.getresponse()
    return response.status, json.loads(response.read())

with tempfile.TemporaryDirectory() as tmp:
    server = make_server(tmp + "/output", port=0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    preview = call(server.port, "POST", "/api/preview", sys.argv[1])[0]
    build = call(server.port, "POST", "/api/builds", sys.argv[1])[1]["build_id"]
    while (state := call(server.port, "GET", "/api/builds/" + build)[1]["state"]) in ("queued", "running"):
        time.sleep(0.2)
    package = call(server.port, "GET", "/api/builds/" + build)[1]["result"]["package_id"]
    # A DWG download must not pull ezdxf into the server process either.
    connection = http.client.HTTPConnection("127.0.0.1", server.port, timeout=120)
    connection.request("GET", "/files/" + package + "/window.dwg")
    answer = connection.getresponse()
    answer.read()
    dwg = answer.status
    connection.close()
    server.shutdown()
    server.close()
print(json.dumps(dict(preview=preview, build=state, dwg=dwg,
                      builder="hanok_generator.engine.builder" in sys.modules,
                      ezdxf="ezdxf" in sys.modules)))
"""


def request(kind="double", bars=(2, 4), side=None, **changes):
    value = dict(type=kind, outer_mm=[463, 586], lattice_per_leaf=list(bars))
    if side:
        value["hinge_side"] = side
    value.update(changes)
    return value


def artwork(bars=(2, 4), **panel):
    """A frame-type request: the A2 panel of #15 on a 4 x 8 board, with panel fields changed."""
    return dict(type="double", lattice_per_leaf=list(bars), preset="standard_4x8_v1",
                artwork=dict({"size_mm": [420, 594]}, **panel))


ARTWORK = artwork()
# Suggested panel bounds name the field of artwork they change; the sides are width/height.
ARTWORK_BOUNDS = {"cover_at_most": "cover_mm", "cover_at_least": "cover_mm", "fit_at_most": "fit_mm",
                  "thickness_at_most": "thickness_mm", "spacer_at_most": "spacer_mm"}


def serve(server):
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class WebApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Rejected requests are expected here; keep their access log out of the report.
        cls.quiet = patch.object(Handler, "log_request")
        cls.quiet.start()
        cls.temp = tempfile.TemporaryDirectory(prefix="hanok-web-tests-")
        cls.root = Path(cls.temp.name)
        cls.output = cls.root / "output"
        cls.server = serve(make_server(cls.output, port=0))
        # The five examples, once through the web queue and once straight through run_job.
        submitted = {name: cls.call("POST", "/api/builds", data)[2]["build_id"] for name, data in EXAMPLES.items()}
        with ThreadPoolExecutor(max_workers=2) as pool:
            cls.direct = dict(zip(EXAMPLES, pool.map(lambda data: run_job(data, cls.root / "direct"), EXAMPLES.values())))
        cls.built = {name: cls.wait(build_id) for name, build_id in submitted.items()}

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.close()
        cls.temp.cleanup()
        cls.quiet.stop()

    @classmethod
    def call(cls, method, path, body=None, *, raw=None, headers=None, decode=True, server=None):
        """One request with explicit headers; returns (status, response, parsed JSON or raw bytes)."""
        server = server or cls.server
        sent = {"Host": f"127.0.0.1:{server.port}"}
        if body is not None:
            raw = json.dumps(body).encode()
        if raw is not None:
            sent["Content-Type"] = "application/json"
        sent.update(headers or {})
        conn = http.client.HTTPConnection("127.0.0.1", server.port, timeout=120)
        try:
            conn.request(method, path, body=raw, headers=sent)
            response = conn.getresponse()
            data = response.read()
        finally:
            conn.close()
        is_json = decode and (response.getheader("Content-Type") or "").startswith("application/json")
        return response.status, response, json.loads(data) if is_json else data

    @classmethod
    def wait(cls, build_id, server=None, timeout=240):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = cls.call("GET", f"/api/builds/{build_id}", server=server)[2]
            if record["state"] not in ("queued", "running"):
                return record
            time.sleep(0.2)
        raise AssertionError(f"build {build_id} did not finish in {timeout} s")

    def test_meta_describes_presets_from_the_model(self):
        status, _, meta = self.call("GET", "/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(meta["engine_version"], __version__)
        presets = {p["id"]: p for p in meta["presets"]}
        self.assertEqual(presets["hanok_A3_portrait_R3"]["types"], ["double"])
        self.assertEqual(presets["standard_v1"]["types"], ["double", "single"])
        self.assertEqual(presets["hanok_A3_portrait_R3"]["picture"], {"size_mm": [297, 420], "margin_mm": 10})
        self.assertIsNone(presets["standard_v1"]["picture"])
        self.assertEqual(presets["hanok_A3_portrait_R3"]["min_leaf_ratio"], 2.6)
        # Each preset carries its default board, edge margin and part gap; only the 4 x 8 one differs.
        self.assertEqual(presets["standard_4x8_v1"], dict(id="standard_4x8_v1", types=["double", "single"], picture=None,
                                                          min_leaf_ratio=0, stock_mm=[2400, 1200, 20],
                                                          edge_margin_mm=10, part_gap_mm=12))
        for name in ("standard_v1", "hanok_A3_portrait_R3"):
            self.assertEqual([presets[name][k] for k in ("stock_mm", "edge_margin_mm", "part_gap_mm")],
                             [[1220, 900, 20], 20, 12])
        self.assertEqual((meta["default_preset"], meta["stock_mm"], meta["frame_member_mm"]), ("standard_v1", [1220, 900, 20], 40))
        self.assertEqual(meta["example"], R3)
        self.assertEqual((meta["limits"]["size_mm"], meta["limits"]["lattice"]), ([1, 3000], [0, 32]))
        # The panel defaults and ranges come from the schema, so the form can fill and check them.
        self.assertEqual(meta["artwork_defaults"], {"thickness_mm": 3, "cover_mm": 8, "fit_mm": 1, "spacer_mm": 3})
        self.assertEqual(meta["limits"]["artwork_mm"], [1, 3000])
        self.assertEqual(meta["limits"]["artwork_fields"],
                         {"thickness_mm": [0.1, 60], "cover_mm": [0.1, 500], "fit_mm": [0, 50], "spacer_mm": [0, 60]})

    def test_preview_matches_cli_resolve(self):
        for name, path in EXAMPLE_FILES.items():
            with self.subTest(example=name):
                status, _, body = self.call("POST", "/api/preview", EXAMPLES[name])
                self.assertEqual(status, 200, body)
                with contextlib.redirect_stdout(io.StringIO()) as out:
                    self.assertEqual(cli.main(["resolve", "--input", str(path)]), 0)
                expected = json.loads(out.getvalue())
                self.assertEqual(body["status"], expected["status"])
                self.assertEqual(body["revision"], expected["parameters"]["revision"])
                self.assertEqual(body["request"], expected["request"])
                self.assertEqual(body["derived"], expected["derived"])
                parts = expected["derived"]["totals"]["parts"]
                self.assertEqual((len(body["assembly"]["parts"]), len(body["nesting"]["parts"])), (parts, parts))
                self.assertEqual(body["size"]["outer_mm"], expected["derived"]["overall_width_height"])
                self.assertEqual(body["size"]["inner_mm"], expected["derived"]["frame_inner"])
        status, _, body = self.call("POST", "/api/preview", R3)
        rects = {p["id"]: p["rect"] for p in body["assembly"]["parts"]}
        nest = {p["id"]: p["rect"] for p in body["nesting"]["parts"]}
        self.assertEqual((rects["F01-1"], nest["F01-1"]), ([0, 0, 40, 586], [20, 20, 606, 60]))
        self.assertEqual(body["assembly"]["picture"]["sheet"], [83, 83, 380, 503])
        self.assertEqual([leaf["hinge_stile"] for leaf in body["assembly"]["leaves"]], ["S01-1", "S01-4"])
        self.assertEqual((body["nesting"]["used_mm"], body["nesting"]["usable_mm"]), ([1091, 284], [1180, 860]))
        # The 4 x 8 preset lays the same parts out on its own board, 10 mm from the edge.
        status, _, body = self.call("POST", "/api/preview", request(preset="standard_4x8_v1"))
        n = body["nesting"]
        self.assertEqual((status, n["stock_mm"], n["margin_mm"], n["usable_mm"], n["used_mm"], n["parts"][0]["rect"]),
                         (200, [2400, 1200, 20], 10, [2380, 1180], [2353, 168], [10, 10, 596, 50]))

    def test_preview_draws_the_artwork_panel_and_its_back_frame(self):
        # A frame-type request resolves like any other; the page needs the panel rectangle and
        # the back frame the engine already lays out, so it can draw what sits behind the frame.
        status, _, body = self.call("POST", "/api/preview", ARTWORK)
        self.assertEqual(status, 200, body)
        self.assertEqual(body["size"], dict(basis="artwork", requested_mm=[420, 594], outer_mm=[484, 658],
                                            inner_mm=[404, 578], frame_member_mm=40))
        parts = body["assembly"]["parts"]
        back = [p for p in parts if p["id"][0] == "B"]
        self.assertEqual(len(parts), 28)
        self.assertEqual([(p["id"], p["kind"], p["family"], p["group"]) for p in back],
                         [("B01-1", "B01", "BACK_FRAME", "FIXED"), ("B01-2", "B01", "BACK_FRAME", "FIXED"),
                          ("B02-1", "B02", "BACK_FRAME", "FIXED"), ("B02-2", "B02", "BACK_FRAME", "FIXED")])
        self.assertEqual(body["assembly"]["artwork"],
                         dict(size_mm=[420, 594], sheet=[32, 32, 452, 626], cover_mm=8, fit_mm=1, spacer_mm=3,
                              thickness_mm=3, back_frame_member_mm=31, back_frame_opening_mm=[422, 596]))
        self.assertIsNone(body["assembly"]["picture"])
        self.assertIn("BACK_FRAME", {p["family"] for p in body["nesting"]["parts"]})
        # Every other design says so plainly, so the page never draws a panel that is not there.
        self.assertIsNone(self.call("POST", "/api/preview", R3)[2]["assembly"]["artwork"])

    def test_rule_errors_name_the_input_to_fix(self):
        cases = [
            ("input.range", "size", request(outer_mm=[0, 586]), "outer_mm[0]"),
            ("input.range", "size", dict(type="double", inner_mm=[2990, 506], lattice_per_leaf=[2, 4]), "outer_mm"),
            ("input.number", "lattice", request(bars=(1.5, 4)), "lattice_per_leaf[0]"),
            ("input.preset_type", "preset", request("single", side="left", preset="hanok_A3_portrait_R3"), None),
            ("input.stock_thickness", "stock", request(stock_mm=[1220, 900, 4]), None),
            ("opening.positive_size", "size", request(outer_mm=[100, 586]), None),
            ("lattice.positive_gap", "lattice", request(outer_mm=[300, 300], bars=(5, 4)), None),
            ("leaf.aspect_ratio", "size", dict(R3, outer_mm=[600, 586]), None),
            ("hardware.reference_spacing", "size", request(outer_mm=[463, 200]), None),
            ("picture.fits_width", "picture", request(picture=dict(size_mm=[500, 500])), None),
            ("nesting.part_fits_stock", "stock", request(outer_mm=[900, 1500]), None),
            ("nesting.board_width", "stock", request(stock_mm=[1220, 150, 20]), None),
            ("nesting.part_fits_stock", "stock", request(outer_mm=[2000, 2381], bars=(4, 10), preset="standard_4x8_v1"), None),
            # A frame-type request: the panel group holds every value these rules name.
            ("artwork.cover_hides_edge", "artwork", artwork(cover_mm=1), None),
            ("artwork.back_member_width", "artwork", artwork(cover_mm=31), None),
            ("artwork.depth_within_stock", "artwork", artwork(thickness_mm=18), None),
            ("input.artwork", "artwork", artwork(typo=1), None),
            ("input.preset_artwork", "preset", dict(ARTWORK, preset="hanok_A3_portrait_R3"), None),
            ("input.artwork_picture", "picture", dict(ARTWORK, picture=dict(size_mm=[297, 420])), None),
            ("input.size_basis", "size", dict(ARTWORK, outer_mm=[484, 658]), None),
        ]
        for rule, group, data, field in cases:
            with self.subTest(rule=rule, data=str(data)):
                status, _, body = self.call("POST", "/api/preview", data)
                self.assertEqual((status, body["status"], body["rule_id"], body["where"]), (422, "FAIL", rule, group))
                if field:
                    self.assertEqual(body["details"]["field"], field)
        # A closed lattice gap comes with the largest count the engine accepts, and the
        # size is still resolved so the page can switch between outer and inner.
        status, _, body = self.call("POST", "/api/preview", request(outer_mm=[300, 300], bars=(5, 4)))
        self.assertAlmostEqual(body["details"]["horizontal"], -0.75)
        self.assertEqual((body["suggestion"]["vertical_per_leaf"], body["size"]["inner_mm"]), (4, [220, 220]))
        self.assertIn("width_at_least", body["suggestion"]["outer_mm"])
        # A layout failure keeps the front view so the page can still draw it.
        status, _, body = self.call("POST", "/api/preview", request(stock_mm=[1220, 150, 20]))
        self.assertEqual((body["stage"], len(body["assembly"]["parts"])), ("nesting", 24))
        # On the 4 x 8 board a part may be 2380 mm long: 2400 less the two 10 mm margins.
        body = self.call("POST", "/api/preview", request(outer_mm=[2000, 2381], bars=(4, 10), preset="standard_4x8_v1"))[2]
        self.assertEqual((body["details"]["usable"], body["suggestion"]),
                         ([2380, 1180], {"stock_mm": {"length_at_least": 2401}, "outer_mm": {"height_at_most": 2380}}))

    def test_suggestions_clear_the_rule_they_answer(self):
        meta = self.call("GET", "/api/meta")[2]
        boards = {p["id"]: p["stock_mm"] for p in meta["presets"]}  # a request without stock_mm has its preset's board

        def each_change(data, suggestion):
            """(what changed, request) for every suggested value, each applied to its own copy."""
            for key, value in suggestion.items():
                if key in ("vertical_per_leaf", "horizontal_per_leaf"):
                    changed = json.loads(json.dumps(data))
                    changed["lattice_per_leaf"][key == "horizontal_per_leaf"] = value
                    yield key, changed
                    continue
                for bound, amount in value.items():
                    changed = json.loads(json.dumps(data))
                    if key in ("outer_mm", "inner_mm"):
                        changed[key][bound.startswith("height")] = amount
                    elif key == "artwork" and bound in ARTWORK_BOUNDS:
                        changed["artwork"][ARTWORK_BOUNDS[bound]] = amount
                    elif key == "artwork":
                        changed["artwork"]["size_mm"][bound.startswith("height")] = amount
                    elif key == "picture" and bound == "margin_at_most":
                        changed["picture"]["margin_mm"] = amount
                    elif key == "picture":
                        changed["picture"]["size_mm"][bound.startswith("height")] = amount
                    else:
                        board = list(boards[data.get("preset", meta["default_preset"])])
                        changed.setdefault("stock_mm", board)[{"length": 0, "width": 1, "thickness": 2}[bound.split("_")[0]]] = amount
                    yield f"{key}.{bound}", changed

        cases = [
            ("opening.positive_size", request(outer_mm=[100, 586])),
            ("lattice.positive_gap", request(outer_mm=[300, 300], bars=(5, 4))),
            ("leaf.aspect_ratio", dict(R3, outer_mm=[600, 586])),
            ("leaf.aspect_ratio", dict(type="double", inner_mm=[520, 506], lattice_per_leaf=[2, 4],
                                       preset="hanok_A3_portrait_R3")),
            ("hardware.reference_spacing", request(outer_mm=[463, 200])),
            ("picture.fits_width", request(picture=dict(size_mm=[500, 500]))),
            ("nesting.part_fits_stock", request(outer_mm=[900, 1500])),
            ("nesting.part_fits_stock", request(outer_mm=[2000, 2381], bars=(4, 10), preset="standard_4x8_v1")),
            ("nesting.board_width", request(stock_mm=[1220, 150, 20])),
            # The frame-type rules, and a size rule answered in the panel field. The size search
            # has to move the panel with the frame, or artwork.covers_inner masks every trial and
            # the suggested size does not clear the rule.
            ("artwork.cover_hides_edge", artwork(cover_mm=1)),
            ("artwork.back_member_width", artwork(cover_mm=31)),
            ("artwork.depth_within_stock", artwork(thickness_mm=18)),
            ("lattice.positive_gap", artwork(bars=(6, 4), size_mm=[200, 300])),
        ]
        # Every suggested value, applied on its own, makes the engine stop reporting that rule.
        for rule, data in cases:
            with self.subTest(rule=rule, data=str(data)):
                body = self.call("POST", "/api/preview", data)[2]
                self.assertEqual(body["rule_id"], rule)
                changes = list(each_change(data, body["suggestion"]))
                self.assertTrue(changes, body)
                for what, changed in changes:
                    status, _, again = self.call("POST", "/api/preview", changed)
                    self.assertTrue(status == 200 or again["rule_id"] != rule, (what, changed, again.get("details")))
        # An inner-size request gets inner sizes back.
        self.assertEqual(set(self.call("POST", "/api/preview", cases[3][1])[2]["suggestion"]), {"inner_mm"})
        # A frame-type request is answered in artwork: panel fields for the panel rules, and the
        # panel size for a rule about the window.
        depth = self.call("POST", "/api/preview", artwork(thickness_mm=18))[2]["suggestion"]
        self.assertEqual(depth, {"artwork": {"thickness_at_most": 17, "spacer_at_most": 2},
                                 "stock_mm": {"thickness_at_least": 21}})
        self.assertEqual(self.call("POST", "/api/preview", artwork(cover_mm=31))[2]["suggestion"],
                         {"artwork": {"cover_at_most": 29}})
        bars = self.call("POST", "/api/preview", artwork(bars=(6, 4), size_mm=[200, 300]))[2]["suggestion"]
        self.assertEqual((set(bars), set(bars["artwork"])), ({"vertical_per_leaf", "artwork"}, {"width_at_least"}))

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_page_words_the_suggested_values(self):
        runner = """
import { describeError } from "./messages.js";
let input = "";
for await (const chunk of process.stdin) input += chunk;
process.stdout.write(JSON.stringify(JSON.parse(input).map((body) => describeError(body).text)));
"""
        bodies = [self.call("POST", "/api/preview", data)[2] for data in (
            dict(R3, outer_mm=[600, 586]), request(outer_mm=[463, 200]), request(stock_mm=[1220, 150, 20]),
            artwork(cover_mm=31), artwork(thickness_mm=18))]
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copy(STATIC / "messages.js", tmp)
            Path(tmp, "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
            Path(tmp, "run.js").write_text(runner, encoding="utf-8")
            p = subprocess.run(["node", "run.js"], cwd=tmp, input=json.dumps(bodies), capture_output=True,
                               text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        aspect, hinge, board, member, depth = json.loads(p.stdout)
        size = bodies[0]["suggestion"]["outer_mm"]
        self.assertIn(f"외경 가로를 {size['width_at_most']} mm 이하로 줄이거나 외경 세로를 "
                      f"{size['height_at_least']} mm 이상으로 늘리세요.", aspect)
        self.assertIn(f"외경 세로를 {bodies[1]['suggestion']['outer_mm']['height_at_least']} mm 이상으로 늘리세요.", hinge)
        self.assertIn(f"원판 폭을 {bodies[2]['suggestion']['stock_mm']['width_at_least']} mm 이상으로 늘리거나 "
                      "창살을 줄이세요.", board)
        # The panel rules are worded from the same suggestion, in the panel's own words.
        self.assertIn("덮는 폭을 29 mm 이하로 줄이세요.", member)
        self.assertIn("화판 두께를 17 mm 이하로 줄이거나 스페이서를 2 mm 이하로 줄이거나 "
                      "원판 두께를 21 mm 이상으로 늘리세요.", depth)

    def test_request_limits_and_same_origin(self):
        port = self.server.port
        cases = [
            (421, "http.host", "GET", "/api/meta", None, None, {"Host": f"evil.example:{port}"}),
            (421, "http.host", "GET", "/api/meta", None, None, {"Host": "127.0.0.1:1"}),
            (403, "http.origin", "POST", "/api/preview", R3, None, {"Origin": "http://evil.example"}),
            (403, "http.origin", "POST", "/api/preview", R3, None, {"Origin": "null"}),
            (415, "http.content_type", "POST", "/api/preview", None, json.dumps(R3).encode(), {"Content-Type": "text/plain"}),
            (413, "input.too_large", "POST", "/api/preview", None, b'{"pad":"' + b"a" * 70 * 1024 + b'"}', None),
            (400, "input.number", "POST", "/api/preview", None,
             b'{"type":"double","outer_mm":[NaN,586],"lattice_per_leaf":[2,4]}', None),
            (400, "input.json", "POST", "/api/preview", None, b'{"type":', None),
            (404, "http.not_found", "GET", "/../../etc/passwd", None, None, None),
            (404, "http.not_found", "GET", "/files/" + "0" * 64 + "/../../etc/passwd", None, None, None),
            (404, "http.not_found", "GET", "/api/packages/not-a-package-id", None, None, None),
            (405, "http.method", "PUT", "/api/preview", None, b"{}", None),
        ]
        for status, rule, method, path, body, raw, headers in cases:
            with self.subTest(status=status, path=path, headers=headers):
                got, response, reply = self.call(method, path, body, raw=raw, headers=headers)
                self.assertEqual((got, reply["rule_id"]), (status, rule))
                self.assertIn("frame-ancestors 'none'", response.getheader("Content-Security-Policy"))
                self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
                self.assertIsNone(response.getheader("Access-Control-Allow-Origin"))
        for host in (f"localhost:{port}", f"[::1]:{port}", f"LOCALHOST:{port}"):
            self.assertEqual(self.call("GET", "/api/meta", headers={"Host": host})[0], 200)
        self.assertEqual(self.call("POST", "/api/preview", R3, headers={"Origin": f"http://127.0.0.1:{port}"})[0], 200)

    def test_server_process_never_imports_the_builder(self):
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        p = subprocess.run([sys.executable, "-c", ISOLATION, json.dumps(R3)], cwd=HERE.parent, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=300)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), dict(preview=200, build="passed", builder=False, ezdxf=False,
                                                    dwg=200 if dwg.executable() else 501))

    def test_web_builds_match_run_job(self):
        for name, data in EXAMPLES.items():
            with self.subTest(example=name):
                record = self.built[name]
                self.assertEqual(record["state"], "passed", record["error"])
                self.assertEqual(record["request"], data)
                self.assertEqual(record["result"]["package_id"], self.direct[name]["package_id"])
                self.assertEqual(record["result"]["checks"], 70)

    def test_package_files_zip_and_history(self):
        r3 = self.built["double_r3"]["result"]["package_id"]
        listing = self.call("GET", "/api/packages")[2]
        ids = {b["result"]["package_id"] for b in self.built.values()}
        self.assertEqual({p["package_id"] for p in listing["packages"]}, ids)
        self.assertIn(listing["latest"], ids)
        self.assertEqual(self.call("POST", "/api/preview", R3)[2]["same_revision"], [r3])
        status, _, detail = self.call("GET", f"/api/packages/{r3}")
        self.assertEqual(status, 200)
        self.assertEqual((detail["type"], detail["preset"], detail["size"]["outer_mm"], detail["lattice_per_leaf"]),
                         ("double", "hanok_A3_portrait_R3", [463, 586], [2, 4]))
        self.assertEqual((detail["checks"], len(detail["validation"]["checks"]), len(detail["validation"]["pending"])),
                         ({"passed": 70, "total": 70}, 70, 6))
        self.assertEqual((detail["request"], detail["file_count"], len(detail["files"])), (R3, 34, 34))
        for row in detail["files"]:
            status, response, data = self.call("GET", f"/files/{r3}/{row['path']}", decode=False)
            self.assertEqual((status, hashlib.sha256(data).hexdigest()), (200, row["sha256"]), row["path"])
            inline = row["path"].endswith(".png")
            self.assertTrue(response.getheader("Content-Disposition").startswith("inline" if inline else "attachment"))
            self.assertIn("immutable", response.getheader("Cache-Control"))
        status, response, data = self.call("GET", f"/files/{r3}.zip", decode=False)
        top = f"hanok_double_outer_463x586_2x4_{r3[:8]}"
        self.assertEqual((status, response.getheader("Content-Disposition")), (200, f'attachment; filename="{top}.zip"'))
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            paths = [row["path"] for row in detail["files"]] + ["package_manifest.json"]
            self.assertEqual(sorted(archive.namelist()), sorted(f"{top}/{p}" for p in paths))
            for row in detail["files"]:
                self.assertEqual(hashlib.sha256(archive.read(f"{top}/{row['path']}")).hexdigest(), row["sha256"])
        self.assertEqual(self.call("GET", f"/api/packages/{r3}/verify")[2], dict(status="PASS", package_id=r3, files=34))
        # Drawing sizes come from the PNG headers; thumbnails are 480 px wide copies.
        png = self.call("GET", f"/files/{r3}/03_assembly_reference.png", decode=False)[2]
        self.assertEqual(detail["drawings"]["03_assembly_reference.png"], list(struct.unpack(">II", png[16:24])))
        status, response, thumb = self.call("GET", f"/thumbs/{r3}/03_assembly_reference.png", decode=False)
        self.assertEqual((status, response.getheader("Content-Type"), struct.unpack(">I", thumb[16:20])[0]), (200, "image/png", 480))
        for path in (f"/files/{r3}/not-in-manifest.txt", f"/files/{r3}/../latest.json", f"/files/{r3}/source/../window.dxf",
                     f"/files/{r3}/%2e%2e/latest.json", f"/api/packages/{'0' * 64}", f"/files/{'0' * 64}.zip",
                     f"/api/builds/{'0' * 32}", f"/thumbs/{r3}/window.dxf", f"/thumbs/{r3}/source.png"):
            with self.subTest(path=path):
                self.assertEqual(self.call("GET", path)[0], 404)

    def test_dwg_is_converted_on_request_and_is_not_a_package_file(self):
        r3 = self.built["double_r3"]["result"]["package_id"]
        detail = self.call("GET", f"/api/packages/{r3}")[2]
        info = detail["dwg"]
        self.assertEqual((info["version"], info["release"]), ("ACAD2010", "AutoCAD 2010"))
        self.assertEqual(info["available"], dwg.executable() is not None)
        # The converter writes different bytes every run, so a DWG is never one of the 34 files.
        self.assertNotIn("window.dwg", [row["path"] for row in detail["files"]])
        status, response, data = self.call("GET", f"/files/{r3}/window.dwg", decode=False)
        if not info["available"]:
            self.assertEqual((status, json.loads(data)["rule_id"]), (501, "dwg.converter_missing"))
            return
        top = f"hanok_double_outer_463x586_2x4_{r3[:8]}"
        self.assertEqual((status, response.getheader("Content-Type")), (200, "image/vnd.dwg"))
        self.assertEqual(response.getheader("Content-Disposition"), f'attachment; filename="{top}.dwg"')
        self.assertEqual(response.getheader("Cache-Control"), "no-store")
        self.assertEqual(data[:6], b"AC1024")  # the DWG release the engine's DXF uses
        self.assertEqual(self.call("GET", f"/files/{'0' * 64}/window.dwg")[0], 404)

    def test_changed_package_file_is_refused(self):
        r3 = self.built["double_r3"]["result"]["package_id"]
        root = self.root / "tampered"
        shutil.copytree(self.output / "packages" / r3, root / "packages" / r3)
        with (root / "packages" / r3 / "README.txt").open("a", encoding="utf-8") as f:
            f.write("changed")
        server = serve(make_server(root, port=0))
        try:
            self.assertEqual(self.call("GET", f"/files/{r3}/window.dxf", decode=False, server=server)[0], 200)
            for path in (f"/files/{r3}/README.txt", f"/files/{r3}.zip"):
                status, _, body = self.call("GET", path, server=server)
                self.assertEqual((status, body["rule_id"]), (409, "package.integrity"))
            result = self.call("GET", f"/api/packages/{r3}/verify", server=server)[2]
            self.assertEqual((result["status"], result["rule_id"]), ("FAIL", "package.integrity"))
        finally:
            server.shutdown()
            server.close()

    def test_failed_build_reports_the_failed_checks(self):
        status, _, record = self.call("POST", "/api/builds", request(bars=(12, 4)))
        self.assertEqual(status, 202)
        record = self.wait(record["build_id"])
        error = record["error"]
        self.assertEqual((record["state"], error["rule_id"], error["where"]), ("failed", "geometry.validation", "result"))
        validation = error["validation"]
        self.assertEqual(validation["failed_checks"], ["distinct_machining_regions_separated"])
        self.assertEqual(validation["passed"], validation["total"] - 1)
        self.assertEqual(validation["failed"][0]["measured"]["closest_pair"]["part_id"], "S02-1")
        self.assertTrue((self.output / error["failure_report"]).is_file())
        # A rule the preview already rejects is refused before anything is queued.
        status, _, body = self.call("POST", "/api/builds", request(outer_mm=[300, 300], bars=(5, 4)))
        self.assertEqual((status, body["rule_id"], body["where"]), (422, "lattice.positive_gap", "lattice"))

    def test_queue_limit_and_waiting_position(self):
        release, started = threading.Event(), threading.Event()

        def runner(data, output, *, timeout):
            started.set()
            release.wait(60)
            return dict(status="PASS", package_id="0" * 64, checks=67, parts=24, pockets=104, dogbones=48,
                        manufacturing_status="PENDING")
        server = serve(make_server(self.root / "stub", port=0, workers=1, waiting=1, runner=runner))
        try:
            first = self.call("POST", "/api/builds", R3, server=server)
            self.assertTrue(started.wait(30))
            second = self.call("POST", "/api/builds", R3, server=server)
            third = self.call("POST", "/api/builds", R3, server=server)
            self.assertEqual([first[0], second[0], third[0]], [202, 202, 429])
            self.assertEqual((third[2]["rule_id"], third[1].getheader("Retry-After")), ("build.queue_full", "5"))
            waiting = self.call("GET", f"/api/builds/{second[2]['build_id']}", server=server)[2]
            self.assertEqual((waiting["state"], waiting["position"]), ("queued", 1))
            release.set()
            for reply in (first, second):
                self.assertEqual(self.wait(reply[2]["build_id"], server=server)["state"], "passed")
        finally:
            release.set()
            server.shutdown()
            server.close()

    def test_source_bundle_excludes_the_web_layer(self):
        # Packages copy these files into source/, and the package_id covers them.
        names = {name for name, _ in source_files()}
        self.assertFalse({name for name in names if name.startswith("web/")})
        recorded = json.loads((HERE / "results.json").read_text(encoding="utf-8"))["source_sha256"]
        self.assertEqual({name: digest(path) for name, path in source_files()}, recorded)

    def test_static_pages_are_served(self):
        for path, kind in (("/", "text/html"), ("/app.css", "text/css"), ("/app.js", "text/javascript"),
                           ("/preview.js", "text/javascript"), ("/packages.js", "text/javascript"),
                           ("/messages.js", "text/javascript")):
            with self.subTest(path=path):
                status, response, _ = self.call("GET", path, decode=False)
                self.assertEqual((status, response.getheader("Content-Type").split(";")[0]), (200, kind))
                self.assertEqual(response.getheader("Cache-Control"), "no-cache")
        page = self.call("GET", "/", decode=False)[2].decode("utf-8")
        self.assertIn('<script type="module" src="/app.js"></script>', page)
        # Local first: no script, style or font is fetched from another host.
        self.assertNotRegex(page + (STATIC / "app.css").read_text(encoding="utf-8"), r"https?://")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_form_composes_the_example_requests(self):
        # The page builds requests in app.js. They must keep the hand-written example shape
        # (optional keys only when not default, integers stay integers), or the same design
        # would get a different package_id from the web than from the CLI.
        meta = self.call("GET", "/api/meta")[2]
        requests = [*EXAMPLES.values(), dict(R3, picture=None),
                    request(outer_mm=[600, 800], picture=dict(size_mm=[297, 420], margin_mm=10), stock_mm=[1220, 900, 18]),
                    dict(type="single", hinge_side="right", inner_mm=[340.3, 820.7], lattice_per_leaf=[2, 6]),
                    request(preset="standard_4x8_v1"), request(preset="standard_4x8_v1", stock_mm=[1220, 900, 20]),
                    # A frame-type request: the panel size alone, and every panel field changed.
                    ARTWORK, artwork(thickness_mm=10, cover_mm=12, fit_mm=2, spacer_mm=5),
                    dict(type="single", hinge_side="left", lattice_per_leaf=[2, 6], artwork=dict(size_mm=[297, 420]))]
        typed = dict(type="double", hinge="left", basis="outer", size=["463.0", " 586 "], lattice=["2", "4"],
                     preset="hanok_A3_portrait_R3", picture=dict(on=True, w="297", h="420", margin="10"),
                     artwork=dict(t="3", c="8", f="1", s="3"), stock=["2400", "1200", "20"])
        # The panel group is typed the same way: default fields are left out of the request.
        panel = dict(typed, basis="artwork", size=["420", "594"], preset="standard_4x8_v1",
                     picture=dict(on=False, w="297", h="420", margin="10"))
        # A picture the form still holds from an earlier design never reaches a frame-type
        # request: artwork and picture together are refused (input.artwork_picture).
        panel_picture = dict(panel, picture=dict(on=True, w="297", h="420", margin="10"))
        # Changing the preset: the R3 example's untouched board becomes the 4 x 8 board, an edited board
        # stays, and the 4 x 8 board goes back to 1220 x 900 x 20 under standard_v1.
        switches = [(typed, "standard_4x8_v1"), (dict(typed, stock=["1500", "900", "20"]), "standard_4x8_v1"),
                    (dict(typed, preset="standard_4x8_v1", stock=["2400", "1200", "20"]), "standard_v1")]
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("app.js", "preview.js", "packages.js", "messages.js"):
                shutil.copy(STATIC / name, tmp)
            Path(tmp, "package.json").write_text('{"type": "module"}\n', encoding="utf-8")
            Path(tmp, "run.js").write_text(NODE_RUNNER, encoding="utf-8")
            p = subprocess.run(["node", "run.js"], cwd=tmp,
                               input=json.dumps(dict(meta=meta, requests=requests, forms=[typed, panel, panel_picture],
                                                     switches=switches)),
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(p.returncode, 0, p.stderr)
        out = json.loads(p.stdout)
        exact = lambda value: json.dumps(value, sort_keys=True)  # 463 and 463.0 differ here
        self.assertEqual([exact(v) for v in out["requests"]], [exact(v) for v in requests])
        self.assertEqual(exact(out["forms"][0]), exact(dict(R3, stock_mm=[2400, 1200, 20])))
        self.assertEqual(exact(out["forms"][1]), exact(ARTWORK))
        self.assertEqual(exact(out["forms"][2]), exact(ARTWORK))
        self.assertEqual(out["switches"], [["2400", "1200", "20"], ["1500", "900", "20"], ["1220", "900", "20"]])


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def status_of(port, path="/api/meta"):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        conn.request("GET", path)
        return conn.getresponse().status
    finally:
        conn.close()


@unittest.skipUnless(os.name == "posix", "the background server needs POSIX sessions and file locks")
class BackgroundServerTests(unittest.TestCase):
    """web.sh start|stop|restart|status|log, which run python -m hanok_generator.web.control."""

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="hanok-web-control-")
        self.addCleanup(temp.cleanup)
        self.output = Path(temp.name)
        self.record = Record(self.output)
        self.port = free_port()
        self.addCleanup(self.kill_leftover)

    def kill_leftover(self):
        record = self.record.running()
        if record and record.get("pid"):
            os.kill(record["pid"], signal.SIGKILL)
            self.wait_stopped()

    def wait_stopped(self, timeout=10):
        deadline = time.monotonic() + timeout
        while self.record.running() is not None:
            self.assertLess(time.monotonic(), deadline, "the server still holds its lock")
            time.sleep(0.05)

    def control(self, *args, env=None):
        return subprocess.run([sys.executable, "-m", "hanok_generator.web.control", *args, "--output", str(self.output)],
                              cwd=HERE.parent, env=env, capture_output=True, text=True, encoding="utf-8", timeout=240)

    def recorded_pid(self):
        return json.loads(self.record.path.read_text(encoding="utf-8"))["pid"]

    def test_start_restart_and_stop(self):
        home, port = f"http://127.0.0.1:{self.port}/", ("--port", str(self.port))
        status = self.control("status", *port)
        self.assertEqual((status.returncode, status.stdout), (3, "꺼져 있습니다.\n"))
        # Once the server answers, start opens it; BROWSER stands in for the default browser.
        started = self.control("start", *port, env=dict(os.environ, BROWSER="/bin/echo OPENED %s"))
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertIn(f"켜졌습니다: {home}", started.stdout)
        self.assertIn(f"OPENED {home}", started.stdout)
        first = self.recorded_pid()
        self.assertEqual(status_of(self.port), 200)
        again = self.control("start", *port, "--no-open")
        self.assertEqual(again.stdout, f"이미 켜져 있습니다: {home} (pid {first})\n")
        status = self.control("status", *port)
        self.assertEqual((status.returncode, status.stdout), (0, f"켜져 있습니다: {home} (pid {first})\n"))
        restarted = self.control("restart", "--no-open")  # without --port: the port it runs on
        self.assertEqual(restarted.returncode, 0, restarted.stderr)
        self.assertNotEqual(self.recorded_pid(), first)
        self.assertEqual(status_of(self.port), 200)
        self.assertIn(f"한옥 창호 생성기  {home}", self.control("log").stdout)
        stopped = self.control("stop", *port)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertTrue(stopped.stdout.endswith("껐습니다.\n"), stopped.stdout)
        # SIGTERM took the Ctrl+C path: the server announced its shutdown before it exited.
        self.assertIn("종료합니다.", self.record.log.read_text(encoding="utf-8"))
        with self.assertRaises(ConnectionRefusedError):
            status_of(self.port)
        self.assertEqual(self.control("status", *port).returncode, 3)

    def test_a_record_left_by_a_dead_server_is_never_signalled(self):
        port = ("--port", str(self.port))
        started = self.control("start", *port, "--no-open")
        self.assertEqual(started.returncode, 0, started.stderr)
        pid = self.recorded_pid()
        os.kill(pid, signal.SIGKILL)  # a crash: no shutdown, and the record stays behind
        self.wait_stopped()
        status = self.control("status", *port)
        self.assertEqual(status.returncode, 3)
        self.assertIn(f"지난번 서버(pid {pid})는 ./web.sh stop 없이 끝났습니다", status.stdout)
        # After a reboot the recorded pid may belong to any process; stop must leave it alone.
        with subprocess.Popen(["sleep", "60"]) as other:
            try:
                self.record.path.write_text(json.dumps(dict(pid=other.pid, port=self.port)), encoding="utf-8")
                stopped = self.control("stop", *port)
                self.assertEqual((stopped.returncode, stopped.stdout), (0, "꺼져 있습니다.\n"))
                self.assertIsNone(other.poll())
                self.assertEqual(self.record.path.read_text(encoding="utf-8"), "")
            finally:
                other.kill()

    def test_start_leaves_the_port_to_a_server_already_there(self):
        other = serve(make_server(self.output / "other", port=0))
        try:
            refused = self.control("start", "--port", str(other.port), "--no-open")
        finally:
            other.shutdown()
            other.close()
        self.assertEqual(refused.returncode, 1)
        self.assertIn(f"127.0.0.1:{other.port}에서 이미 다른 서버가 응답합니다", refused.stderr)
        self.assertFalse(self.record.path.exists())

    def test_a_failed_start_shows_the_server_log(self):
        with socket.socket() as busy:  # holds the port without answering HTTP
            busy.bind(("127.0.0.1", 0))
            busy.listen()
            port = busy.getsockname()[1]
            failed = self.control("start", "--port", str(port), "--no-open")
        self.assertEqual(failed.returncode, 1)
        self.assertIn(f"127.0.0.1:{port} 포트를 열 수 없습니다", failed.stderr)
        status = self.control("status", "--port", str(port))
        self.assertEqual((status.returncode, status.stdout), (3, "꺼져 있습니다.\n"))

    @unittest.skipUnless((HERE.parent / ".venv" / "bin" / "python").exists(), "web.sh runs .venv/bin/python")
    def test_web_sh_and_the_finder_files(self):
        root = HERE.parent
        for name in ("web.sh", "web-start.command", "web-stop.command"):
            self.assertTrue(os.access(root / name, os.X_OK), f"{name} is not executable")

        def run(name, *args):  # Finder runs a .command from the home folder, not from generator/
            return subprocess.run([str(root / name), *args, "--output", str(self.output)], cwd=self.output,
                                  capture_output=True, text=True, encoding="utf-8", timeout=240)

        started = run("web-start.command", "--port", str(self.port), "--no-open")
        self.assertEqual(started.returncode, 0, started.stderr)
        self.assertEqual(status_of(self.port), 200)
        stopped = run("web-stop.command")
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        self.assertTrue(stopped.stdout.endswith("껐습니다.\n"), stopped.stdout)
        usage = subprocess.run([str(root / "web.sh")], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(usage.returncode, 0, usage.stderr)
        self.assertIn("start", usage.stdout)


if __name__ == "__main__":
    unittest.main()
