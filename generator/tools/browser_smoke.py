"""Exercise real design, build, package, image and download flows in headless Chrome."""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from docs.manual.make_images import Chrome, Page, DESIGN_READY, PACKAGE_READY, find_chrome
from hanok_generator.package import verify
from hanok_generator.web.server import make_server


def build(page, output):
    page.wait(DESIGN_READY)
    page.click("#build")
    page.wait("location.hash.startsWith('#/packages/') && " + PACKAGE_READY, timeout=150)
    package_id = page.js("location.hash.split('/').at(-1)")
    verified = verify(output / "packages" / package_id)
    page.click("#pkg-verify")
    page.wait("document.getElementById('pkg-integrity').classList.contains('st-pass')")
    for suffix in (".zip", "/window.ai", "/window.dxf"):
        response = page.js(f"fetch('/files/{package_id}{suffix}').then(async r => ({{status:r.status, "
                           "bytes:(await r.arrayBuffer()).byteLength}))")
        if response["status"] != 200 or response["bytes"] == 0:
            raise RuntimeError(f"Download failed: {suffix}: {response}")
    page.click("#pkg-thumbs .thumb:nth-of-type(3)")
    page.wait("document.getElementById('viewer').open && document.getElementById('viewer-img').naturalWidth > 0")
    return verified


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chrome")
    parser.add_argument("--output", type=Path, help="optional screenshot and result directory")
    args = parser.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="hanok-browser-") as temp, ExitStack() as cleanup:
        output = Path(temp) / "output"
        server = make_server(output, port=0)
        cleanup.callback(server.close)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        cleanup.callback(thread.join, timeout=15)
        cleanup.callback(server.shutdown)
        chrome = Chrome(find_chrome(args.chrome))
        cleanup.callback(chrome.close)
        origin = f"http://127.0.0.1:{server.port}"
        page = Page(chrome, origin + "/#/design", DESIGN_READY)
        results = {"r3": build(page, output)}
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            page.capture().save(args.output / "r3-viewer.png")
        page = Page(chrome, origin + "/#/design", DESIGN_READY)
        page.type("size-w", "600")
        page.wait("document.getElementById('build').disabled && "
                  "[...document.querySelectorAll('[id^=err-]')].some(e => !e.hidden && e.textContent.trim())")
        page = Page(chrome, origin + "/#/design", DESIGN_READY)
        page.type("preset", "standard_4x8_v1")
        page.click("#basis-artwork")
        page.type("size-w", "420")
        page.type("size-h", "594")
        page.wait("document.querySelector('#panel-elev .mk-art') && " + DESIGN_READY)
        results["artwork_a2"] = build(page, output)
        if args.output:
            page.capture().save(args.output / "artwork-viewer.png")
            (args.output / "results.json").write_text(json.dumps(results, indent=2)+"\n", encoding="utf-8")
        print("PASS: real browser R3 and artwork builds, validation, viewer, downloads and input rejection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
