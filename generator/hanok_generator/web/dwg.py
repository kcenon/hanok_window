"""Optional DWG download, converted on request by the ODA File Converter.

A package_id is the hash of the package files, and this converter writes a different DWG every
time it runs (the same length, a few hundred bytes apart), so a DWG can never be a package file.
It is made when someone asks for it, from the checked bytes of window.dxf, and nothing here
writes into a published package.

Only the standard library: the server process must never import ezdxf, and tests/test_web.py
asserts that after a build. The conversion runs the converter directly instead of going through
ezdxf.addons.odafc, which imports ezdxf and looks for a Windows install path that the winget
package does not use.
"""
from __future__ import annotations

import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile

# The engine writes DXF R2010 (engine/builder.py), so the DWG is the same release: a program that
# opens one opens the other.
VERSION = "ACAD2010"
RELEASE = "AutoCAD 2010"
TIMEOUT = 120
NAME = "ODAFileConverter"
# winget installs 27.1 as "ODAFileConverter 27.1.0"; older builds use a folder without the version.
WINDOWS_ROOTS = (r"C:\Program Files\ODA", r"C:\Program Files (x86)\ODA")
IN_NAME = re.compile(r"(\d+(?:\.\d+)+)")


class DwgError(RuntimeError):
    """A DWG the server cannot produce, carrying the rule id and details the API answers with."""

    def __init__(self, rule_id, message, **details):
        super().__init__(message)
        self.rule_id, self.message, self.details = rule_id, message, details


def numbers(name):
    match = IN_NAME.search(name)
    return tuple(int(part) for part in match.group(1).split(".")) if match else ()


def executable():
    """The converter this machine has, or None. HANOK_ODAFC names one directly."""
    override = os.environ.get("HANOK_ODAFC")
    if override:
        path = Path(override)
        return path if path.is_file() else None
    found = shutil.which(NAME)
    if found:
        return Path(found)
    if platform.system() != "Windows":
        return None
    paths = [p for root in WINDOWS_ROOTS for p in Path(root).glob(f"{NAME}*/{NAME}.exe") if p.is_file()]
    # Newest by the version in the folder name, so an upgrade beside an old install wins.
    return max(paths, key=lambda p: numbers(p.parent.name), default=None)


def version(path=None):
    """The converter version, read from its folder name: the files it writes never name it."""
    path = executable() if path is None else path
    match = IN_NAME.search(path.parent.name) if path is not None else None
    return match.group(1) if match else None


def status():
    """What the package screen and the API say about DWG downloads on this machine."""
    path = executable()
    return dict(available=path is not None, converter=version(path), version=VERSION, release=RELEASE)


def convert(data, suffix):
    """One drawing converted in memory; `suffix` (".dwg" or ".dxf") names the output format."""
    path = executable()
    if path is None:
        raise DwgError("dwg.converter_missing",
                       "이 컴퓨터에 ODA File Converter가 없어 DWG로 바꿀 수 없습니다. 설치한 뒤 다시 여세요.",
                       searched=list(WINDOWS_ROOTS) if platform.system() == "Windows" else [NAME])
    source = ".dxf" if suffix == ".dwg" else ".dwg"
    with tempfile.TemporaryDirectory(prefix="hanok-dwg-") as tmp:
        inbox, outbox = Path(tmp) / "in", Path(tmp) / "out"
        inbox.mkdir()
        outbox.mkdir()
        (inbox / ("window" + source)).write_bytes(data)
        completed = run(path, inbox, outbox, suffix, "window" + source)
        produced = outbox / ("window" + suffix)
        if not produced.is_file():
            raise DwgError("dwg.conversion_failed", "도면을 DWG로 바꾸지 못했습니다.",
                           returncode=completed.returncode,
                           stderr=completed.stderr.decode("utf-8", "replace")[-400:])
        return produced.read_bytes()


def run(path, inbox, outbox, suffix, filter_name):
    """ODAFileConverter <in folder> <out folder> <version> <format> <recurse> <audit> [filter]."""
    command = [str(path), str(inbox), str(outbox), VERSION, suffix[1:].upper(), "0", "0", filter_name]
    options = dict(capture_output=True, timeout=TIMEOUT)
    system, screen = platform.system(), None
    if system == "Windows":
        # A GUI program: without this it shows a console and a window on every download.
        info = subprocess.STARTUPINFO()
        info.dwFlags = subprocess.STARTF_USESHOWWINDOW
        info.wShowWindow = subprocess.SW_HIDE
        options["startupinfo"] = info
    elif system == "Linux" and shutil.which("Xvfb"):
        # It needs a display even in batch mode, and on Linux it exits abnormally even when the
        # conversion worked, so the produced file decides, never the return code.
        display = f":{os.getpid()}"
        screen = subprocess.Popen(["Xvfb", display, "-screen", "0", "800x600x24"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        options["env"] = {**os.environ, "DISPLAY": display}
    try:
        return subprocess.run(command, **options)
    except subprocess.TimeoutExpired as exc:
        raise DwgError("dwg.conversion_failed", f"DWG 변환이 제한 시간 {TIMEOUT}초 안에 끝나지 않았습니다.",
                       timeout=TIMEOUT) from exc
    finally:
        if screen is not None:
            screen.terminate()
            screen.wait()
