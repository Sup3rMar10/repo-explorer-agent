# Repo Explorer Agent

A minimal AI agent in a single Python file. Point it at a folder and ask questions about the code in a chat. It explores the files with tools before it answers.

```
you> where is the retry logic and how does it work?
  [tool] search_text({"query": "retry"})
  [tool] read_file({"path": "client/http.py"})

The retry logic is in client/http.py ...
```

## How it works

The agent loop is written out by hand rather than hidden in a framework:

1. Send the conversation and the tool definitions to Claude.
2. If Claude asks to use a tool, run it and send the result back.
3. Repeat until Claude answers in plain text, or the step cap is hit.

| Tool | Purpose |
|---|---|
| `list_files` | See the project layout |
| `read_file` | Read a file |
| `search_text` | Grep across the project |

## Run

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...
python agent.py path/to/project
```

## Design notes

- Tools are read-only and sandboxed to the project root.
- Tool errors go back to the model as `is_error` results, so it can recover instead of crashing.
- Chat history persists across questions, so follow-ups work.
- Built on the Anthropic Python SDK with `claude-opus-5-5` and adaptive thinking.
