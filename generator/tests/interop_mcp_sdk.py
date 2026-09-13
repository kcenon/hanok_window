"""Interoperability check with the official MCP Python SDK. Not part of the unit tests.

The generator does not depend on the SDK. Install it into a separate environment and run this file
from it; the SDK client starts mcp.sh, negotiates the protocol, lists the tools and calls them, and
the SDK itself validates every successful structured result against the tool's outputSchema.

    python3.11 -m venv /tmp/mcp-sdk && /tmp/mcp-sdk/bin/python -m pip install mcp
    /tmp/mcp-sdk/bin/python tests/interop_mcp_sdk.py

Exit code 0 when every step passes. Checked with mcp 2.2.0 (2026-09-13).
"""
import asyncio
from importlib import metadata
import json
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters, stdio_client

ROOT = Path(__file__).resolve().parent.parent
SINGLE = {"type": "single", "hinge_side": "left", "outer_mm": [420, 900], "lattice_per_leaf": [0, 0]}
NAMES = ["describe_generator", "check_design", "build_package", "list_packages", "get_package", "verify_package",
         "get_drawing", "read_package_file"]


def attribute(item, *names):
    """The first attribute that exists: the SDK renamed fields to snake_case in 2.x."""
    for name in names:
        if hasattr(item, name):
            return getattr(item, name)
    raise AttributeError(f"none of {names} on {type(item).__name__}")


def structured(result):
    value = attribute(result, "structured_content", "structuredContent")
    return value if value is not None else json.loads(result.content[0].text)


async def check(output):
    stages = []

    async def on_progress(progress, total=None, message=None, *rest):
        stages.append(progress)

    server = StdioServerParameters(command=str(ROOT / "mcp.sh"), args=["--output", str(output)])
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print("sdk", metadata.version("mcp"), "| protocol", attribute(init, "protocol_version", "protocolVersion"),
                  "| server", attribute(init, "server_info", "serverInfo").version)
            tools = (await session.list_tools()).tools
            assert [t.name for t in tools] == NAMES, [t.name for t in tools]
            assert all(attribute(t, "output_schema", "outputSchema") for t in tools)
            print("tools", len(tools), "all with outputSchema")

            refused = await session.call_tool("check_design", dict(SINGLE, lattice_per_leaf=[30, 0]))
            assert attribute(refused, "is_error", "isError"), "a closed lattice gap must be refused"
            print("check_design refused:", structured(refused)["rule_id"], structured(refused).get("suggestion"))

            built = await session.call_tool("build_package", SINGLE, progress_callback=on_progress)
            assert not attribute(built, "is_error", "isError"), built.content[0].text
            package_id = structured(built)["package_id"]
            print("build_package", package_id[:12], "progress", stages)

            drawing = await session.call_tool("get_drawing", {"package_id": package_id[:8], "drawing": "assembly"})
            kinds = [item.type for item in drawing.content]
            assert kinds == ["text", "image"], kinds
            print("get_drawing", kinds, attribute(drawing.content[1], "mime_type", "mimeType"))

            readme = await session.call_tool("read_package_file", {"package_id": package_id[:8], "path": "README.txt"})
            assert structured(readme)["text"], "README.txt must not be empty"
            print("read_package_file README.txt", structured(readme)["characters"], "characters")
            for name, arguments in (("describe_generator", {}), ("list_packages", {}),
                                    ("get_package", {"package_id": package_id}),
                                    ("verify_package", {"package_id": package_id})):
                result = await session.call_tool(name, arguments)  # the SDK validates each against outputSchema
                assert not attribute(result, "is_error", "isError"), (name, result.content[0].text)
            print("describe_generator, list_packages, get_package, verify_package: valid structured results")


def main():
    with tempfile.TemporaryDirectory(prefix="hanok-mcp-sdk-") as tmp:
        asyncio.run(check(Path(tmp) / "output"))
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
