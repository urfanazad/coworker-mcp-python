# Coworker MCP (Python)

A local-first MCP-style AI coworker that safely works on your filesystem using job-based execution, approval gates, and audit logging.

## Project Structure
```
coworker-mcp-python/
├── server/
│   ├── fs_tools.py
│   ├── app.py
│   └── ...
├── extension/
│   ├── background.js
│   ├── manifest.json
│   └── ...
└── ...
```

## Features
- Workspace-scoped filesystem access
- Job-based execution with idempotency
- Plan → approve → execute safety flow
- Soft delete (trash) & restore
- Append-only audit log
- Browser extension UI
- Python backend (FastAPI)
- Protobuf contracts (internal)

## Quick Start

### 1. Backend
```bash
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8765
```

### 2. Browser Extension
1. Open `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked** and select the `extension/` folder.
4. Open the extension **Options** and set your **Allowed roots** (the folders you want the AI to access).

## Safety Guarantees
- No filesystem access outside allowed roots.
- All write actions require approval tokens.
- All file changes are audited in `.coworker_audit.jsonl`.
- Soft delete instead of hard delete.

## Architecture
See `docs/hld.md` for the High-Level Design and CAP choice rationale.

---
MIT License
