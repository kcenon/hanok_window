"""Tool definitions for any LLM API and a one-shot tool runner: `hanok-window-llm tools|call`."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from .tools import FORMATS, Toolbox


def reject_constant(value):
    raise ValueError(f"{value} is not allowed")


def save_images(outcome, name, folder):
    """Write a tool's PNG images to files and describe them; the JSON output stays small."""
    folder.mkdir(parents=True, exist_ok=True)
    stem = "-".join(str(outcome.data[k])[:12] for k in ("package_id", "drawing") if k in outcome.data) or name
    saved = []
    for index, (mime, data) in enumerate(outcome.images):
        path = folder / f"{stem}{'-' + str(index) if index else ''}.png"
        path.write_bytes(data)
        saved.append(dict(mime_type=mime, path=str(path.resolve()), bytes=len(data)))
    return saved


def main(argv=None):
    parser = argparse.ArgumentParser(prog="hanok-window-llm",
                                     description="LLM에 넘길 도구 정의를 출력하거나, 모델이 요청한 도구 하나를 실행합니다.")
    commands = parser.add_subparsers(dest="command", required=True)
    tools = commands.add_parser("tools", help="도구 정의 JSON을 출력합니다")
    tools.add_argument("--format", choices=list(FORMATS), default="mcp",
                       help="mcp, openai(Chat Completions·Ollama·vLLM 등 OpenAI 호환), openai-responses, anthropic")
    call = commands.add_parser("call", help="도구 하나를 실행하고 결과 JSON을 출력합니다")
    call.add_argument("name", help="도구 이름 (tools로 목록 확인)")
    call.add_argument("arguments", nargs="?", default="{}", help="JSON 인자. '-'이면 표준 입력에서 읽습니다 (기본 {})")
    call.add_argument("--output", type=Path, default=Path("output"), help="패키지 폴더 (기본 ./output)")
    call.add_argument("--image-dir", type=Path, help="도면 이미지를 저장할 폴더 (기본: 임시 폴더)")
    args = parser.parse_args(argv)

    if args.command == "tools":
        print(json.dumps(Toolbox(Path("output")).definitions(args.format), ensure_ascii=False, indent=2))
        return 0
    box = Toolbox(args.output)
    if args.name not in box.tools:
        print(json.dumps(dict(status="FAIL", rule_id="tool.unknown", message=f"Unknown tool: {args.name}",
                              tools=list(box.tools)), ensure_ascii=False), file=sys.stderr)
        return 2
    text = sys.stdin.read() if args.arguments == "-" else args.arguments
    try:
        arguments = json.loads(text, parse_constant=reject_constant)
    except ValueError as exc:
        print(json.dumps(dict(status="FAIL", rule_id="tool.arguments", message=f"Invalid JSON arguments: {exc}"),
                         ensure_ascii=False), file=sys.stderr)
        return 2
    outcome = box.call(args.name, arguments)
    images = save_images(outcome, args.name, args.image_dir or Path(tempfile.gettempdir()) / "hanok-window-llm") \
        if outcome.images else []
    print(json.dumps(dict(tool=args.name, is_error=outcome.is_error, result=outcome.data, images=images),
                     ensure_ascii=False, indent=2))
    return 1 if outcome.is_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
