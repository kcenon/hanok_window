#!/bin/sh
# MCP server for LLM clients (Claude, Cursor, VS Code, Gemini CLI, ...): register this file's
# absolute path as the server command. Packages go to output/ next to this script unless
# --output is given (a later --output overrides the one below).
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
    echo "가상환경(.venv)이 없습니다. 이 폴더에서 먼저 설치하세요:" >&2
    echo "  python3.11 -m venv .venv && .venv/bin/python -m pip install -e ." >&2
    exit 1
fi
exec .venv/bin/python -m hanok_generator.llm.mcp --output output "$@"
