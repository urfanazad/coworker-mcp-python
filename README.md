# coworker-mcp-python
 A local-first MCP-style AI coworker that safely works on your filesystem using job-based execution, approval gates, and audit logging.

coworker-mcp-python/
├── README.md
├── LICENSE
├── .gitignore
├── requirements.txt
│
├── proto/
│   └── coworker.proto
│
├── server/
│   ├── __init__.py
│   ├── app.py
│   ├── worker.py
│   ├── fs_tools.py
│   ├── cp_store.py
│   ├── security.py
│
├── extension/
│   ├── manifest.json
│   ├── background.js
│   ├── popup.html
│   ├── popup.js
│   ├── options.html
│   └── options.js
│
└── docs/
    ├── architecture.md
    └── security.md


This structure follows real-world open-source expectations:

Clear separation of protocols, backend, frontend

Documentation isolated in /docs

Extension is standalone

# Coworker MCP (Python)

A local-first MCP-style AI coworker that safely works on your filesystem using
job-based execution, approval gates, and audit logging.

## Features

- Workspace-scoped filesystem access
- Job-based execution with idempotency
- Plan → approve → execute safety flow
- Soft delete (trash) & restore
- Append-only audit log
- Browser extension UI
- Python backend (FastAPI)
- Protobuf contracts (internal)

## Architecture

- **Control Plane (CP):**
  - Job state
  - Approval tokens
  - Audit logs
- **Worker Plane:**
  - File scanning
  - Organise plans
  - Execution
- **UI Plane:**
  - Browser extension
  - Localhost API

See `docs/architecture.md` for details.

## Installation

### 1. Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8765


2. Browser Extension

Open chrome://extensions

Enable Developer mode

Click Load unpacked

Select the extension/ folder

3. Configure Allowed Roots

Open the extension options page and add allowed directories (one per line).

Safety Guarantees

No filesystem access outside allowed roots

All write actions require approval tokens

All file changes are audited

Soft delete instead of hard delete


---

# 📄 docs/architecture.md

```markdown
# Architecture Overview

## Components

### API Gateway (FastAPI)
- Tool discovery
- Job submission
- Approval issuance
- Result retrieval

### CP Store (SQLite)
- Job lifecycle state
- Deduplication
- Approval tokens
- Audit metadata

### Worker
- Lease-based job execution
- Idempotent handlers
- Workspace enforcement

### Browser Extension
- UI + dispatcher
- Token-based authentication
- No direct filesystem access

## CAP Design

- **Consistency:** Job state, approvals, audit logs
- **Availability:** Reads, search, status queries
- **Partition tolerance:** Explicit retry + lease expiry

Single-node by default; multi-node compatible.

# Security Model

## Workspace Boundaries
- All paths are realpath-validated
- No symlink escape
- Explicit allowlist only

## Approval Flow
1. Plan generated
2. Plan hash computed
3. Approval token minted (short TTL)
4. Execution bound to exact plan hash

## Audit Logging
- JSONL append-only
- Stored inside workspace
- Human-readable
- Tamper-evident by ordering

## Browser Protection
- Localhost API guarded by session token
- Random websites cannot call backend

__pycache__/
*.pyc
*.sqlite3
.venv/
.env
node_modules/

MIT License

Copyright (c) 2026

Permission is hereby granted, free of charge, to any person obtaining a copy...

