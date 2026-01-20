# Coworker MCP (Python)

Local-first filesystem coworker with:
- workspace-scoped access
- job orchestration (idempotency + leases)
- plan → approve → execute safety gate
- soft delete (trash) + restore
- append-only audit log
- browser extension UI

## Quick start

### 1) Backend

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn server.app:app --host 127.0.0.1 --port 8765
```

### 2) Browser extension

1. Open `chrome://extensions`
2. Enable **Developer mode**
3. **Load unpacked** → select `extension/`
4. Open extension **Options** and set **Allowed roots** (one per line)

## Docs
- HLD: `docs/hld.md`

## Notes
- The backend writes `coworker_cp.sqlite3` in the working directory. Add it to `.gitignore` (already included).
