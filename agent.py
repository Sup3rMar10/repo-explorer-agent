"""A tiny codebase-explorer agent: chat with Claude about any local folder.

Usage: python agent.py [path-to-project]
"""
import json
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-5-5"
ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
MAX_STEPS = 15  # safety cap on tool-use turns per question

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment

SYSTEM = (
    f"You are a codebase explorer. The project lives at {ROOT}. "
    "Use your tools to inspect files before answering, and cite file paths in your answers."
)

TOOLS = [
    {
        "name": "list_files",
        "description": "List files in the project, optionally under a subdirectory.",
        "input_schema": {
            "type": "object",
            "properties": {"subdir": {"type": "string", "description": "Relative path, default '.'"}},
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from the project (first 10,000 characters).",
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "Relative file path"}},
            "required": ["path"],
        },
    },
    {
        "name": "search_text",
        "description": "Find lines containing a string across project files.",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


def safe(rel: str) -> Path:
    """Resolve a relative path and refuse anything outside the project root."""
    path = (ROOT / rel).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("path escapes project root")
    return path


def project_files(base: Path):
    return [p for p in base.rglob("*") if p.is_file() and ".git" not in p.parts]


def run_tool(name: str, args: dict) -> str:
    if name == "list_files":
        files = project_files(safe(args.get("subdir", ".")))
        return "\n".join(str(p.relative_to(ROOT)) for p in files[:200]) or "(empty)"
    if name == "read_file":
        return safe(args["path"]).read_text(errors="replace")[:10_000]
    if name == "search_text":
        hits = []
        for p in project_files(ROOT):
            try:
                for n, line in enumerate(p.read_text().splitlines(), 1):
                    if args["query"].lower() in line.lower():
                        hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
            except (UnicodeDecodeError, OSError):
                continue
        return "\n".join(hits[:50]) or "no matches"
    raise ValueError(f"unknown tool {name}")


def answer(messages: list) -> str:
    """The agent loop: call the model, run any requested tools, repeat until it stops."""
    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM,
            tools=TOOLS,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})
        if response.stop_reason != "tool_use":
            return "".join(b.text for b in response.content if b.type == "text")

        results = []
        for block in response.content:
            if block.type == "tool_use":
                try:
                    out, is_error = run_tool(block.name, block.input), False
                except Exception as exc:  # report failures to the model so it can recover
                    out, is_error = f"error: {exc}", True
                print(f"  [tool] {block.name}({json.dumps(block.input)})")
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": out, "is_error": is_error}
                )
        messages.append({"role": "user", "content": results})
    return "Stopped: step limit reached."


if __name__ == "__main__":
    history: list = []  # kept across questions, so follow-ups have context
    print(f"Exploring {ROOT} (Ctrl+C to quit)")
    while True:
        question = input("\nyou> ").strip()
        if question:
            history.append({"role": "user", "content": question})
            print("\n" + answer(history))
