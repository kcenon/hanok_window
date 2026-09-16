"""Every text read, write and text-mode subprocess in the package and the tests names its encoding."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

HERE = Path(__file__).parent
ROOTS = (HERE.parent / "hanok_generator", HERE.parent / "tools", HERE)


def _mode(call, position):
    keywords = {k.arg: k.value for k in call.keywords}
    node = keywords.get("mode", call.args[position] if len(call.args) > position else None)
    if node is None:
        return "r"
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def unnamed_encodings(path):
    """Yield (line, call) for text I/O that falls back to the locale encoding."""
    for call in ast.walk(ast.parse(path.read_text(encoding="utf-8"), str(path))):
        if not isinstance(call, ast.Call) or any(k.arg == "encoding" for k in call.keywords):
            continue
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr in ("read_text", "write_text"):
            yield call.lineno, func.attr + "()"
        elif isinstance(func, ast.Name) and func.id == "open":
            if "b" not in (_mode(call, 1) or "b"):
                yield call.lineno, "open()"
        # Path.open(mode): a string mode or no argument. Image.open(path) and friends take a path first.
        elif isinstance(func, ast.Attribute) and func.attr == "open" and (
                not call.args or isinstance(call.args[0], ast.Constant)):
            if "b" not in (_mode(call, 0) or "b"):
                yield call.lineno, ".open()"
        elif any(k.arg in ("text", "universal_newlines") and isinstance(k.value, ast.Constant) and k.value.value is True
                 for k in call.keywords):
            yield call.lineno, "text=True"


class EncodingTests(unittest.TestCase):
    def test_text_io_names_its_encoding(self):
        found = [f"{path.relative_to(HERE.parent).as_posix()}:{line} {what}"
                 for root in ROOTS for path in sorted(root.rglob("*.py")) for line, what in unnamed_encodings(path)]
        self.assertEqual(found, [], "\n".join(found))


if __name__ == "__main__":
    unittest.main()
