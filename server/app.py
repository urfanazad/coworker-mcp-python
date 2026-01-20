from __future__ import annotations

import json
import uuid
import secrets
import hashlib
import base64
from typing import Optional, Dict, List

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .cp_store import CPStore, QUEUED, SUCCEEDED
from .security import mint_token, require_token
from .worker import Worker

app = FastAPI(title="Coworker MCP (Python)")
store = CPStore(db_path="coworker_cp.sqlite3")

# For dev convenience allow all; restrict in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HandshakeResponse(BaseModel):
    session_id: str
    token: str


class SubmitJobBody(BaseModel):
    dedupe_key: str
    type: int
    allowed_roots: List[str]
    params: Dict[str, str] = {}
    approval_token: Optional[str] = None


class ApprovePlanBody(BaseModel):
    plan_job_id: str
    ttl_seconds: int = 120


@app.on_event("startup")
async def startup() -> None:
    import asyncio

    for i in range(2):
        w = Worker(store, worker_id=f"w{i+1}")
        asyncio.create_task(w.run_forever())


@app.post("/handshake", response_model=HandshakeResponse)
def handshake() -> HandshakeResponse:
    session_id = str(uuid.uuid4())
    token = mint_token()
    store.create_session(session_id, token)
    return HandshakeResponse(session_id=session_id, token=token)


@app.get("/tools")
def tools(
    x_coworker_session: Optional[str] = Header(default=None),
    x_coworker_token: Optional[str] = Header(default=None),
):
    require_token(store, x_coworker_session, x_coworker_token)
    return {
        "tools": [
            {"name": "scan_index", "type": 1, "params": ["root", "hash_files"]},
            {"name": "list_files", "type": 2, "params": ["root"]},
            {"name": "read_file", "type": 3, "params": ["path", "max_bytes"]},
            {"name": "organize_plan", "type": 4, "params": ["root", "policy"]},
            {
                "name": "execute_plan",
                "type": 5,
                "params": ["plan_job_id", "workspace_root"],
                "requires_approval": True,
            },
            {
                "name": "soft_delete",
                "type": 6,
                "params": ["path", "workspace_root"],
                "requires_approval": True,
            },
            {
                "name": "restore",
                "type": 7,
                "params": ["trash_item_path", "restore_to", "workspace_root"],
                "requires_approval": True,
            },
            {"name": "browse_web", "type": 8, "params": ["url"]},
            {"name": "create_excel", "type": 9, "params": ["path", "data"]},
            {"name": "create_word", "type": 10, "params": ["path", "content"]},
            {"name": "create_pdf", "type": 11, "params": ["path", "content"]},
            {"name": "execute_python", "type": 12, "params": ["code"]},
            {"name": "search_past_actions", "type": 13, "params": ["query", "workspace_root"]},
            {"name": "search_google_drive", "type": 14, "params": ["query"]},
            {"name": "listen_meeting", "type": 15, "params": ["duration"]},
        ]
    }


@app.post("/approve")
def approve_plan(
    body: ApprovePlanBody,
    x_coworker_session: Optional[str] = Header(default=None),
    x_coworker_token: Optional[str] = Header(default=None),
):
    require_token(store, x_coworker_session, x_coworker_token)
    store.purge_expired_approvals()

    plan_job = store.get_job(body.plan_job_id)
    if not plan_job:
        raise HTTPException(status_code=404, detail="Plan job not found")
    if int(plan_job["status"]) != SUCCEEDED:
        raise HTTPException(status_code=400, detail="Plan job is not in SUCCEEDED state")

    plan_res = store.get_result(body.plan_job_id)
    if not plan_res:
        raise HTTPException(status_code=404, detail="Plan result not found")

    plan_json = json.loads(plan_res[0].decode("utf-8"))
    plan_hash = plan_json.get("plan_hash")
    if not plan_hash:
        plan_hash = hashlib.sha256(
            json.dumps(plan_json, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    token = secrets.token_urlsafe(32)
    ttl = max(10, min(int(body.ttl_seconds), 3600))
    store.create_approval(token, body.plan_job_id, plan_hash, ttl_ms=ttl * 1000)

    return {
        "approval_token": token,
        "plan_job_id": body.plan_job_id,
        "plan_hash": plan_hash,
        "ttl_seconds": ttl,
    }


@app.post("/jobs")
def submit_job(
    body: SubmitJobBody,
    x_coworker_session: Optional[str] = Header(default=None),
    x_coworker_token: Optional[str] = Header(default=None),
):
    require_token(store, x_coworker_session, x_coworker_token)

    # Require approval token for write jobs
    if body.type in (5, 6, 7) and not body.approval_token:
        raise HTTPException(status_code=400, detail="approval_token is required for write jobs")

    job_id = str(uuid.uuid4())
    params_json = json.dumps(body.params)
    roots_json = json.dumps(body.allowed_roots)

    created, final_job_id = store.upsert_job_if_new(
        job_id=job_id,
        dedupe_key=body.dedupe_key,
        jtype=body.type,
        params_json=params_json,
        allowed_roots_json=roots_json,
        approval_token=body.approval_token,
    )

    return {"created_new": created, "job_id": final_job_id, "status": QUEUED}


@app.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    x_coworker_session: Optional[str] = Header(default=None),
    x_coworker_token: Optional[str] = Header(default=None),
):
    require_token(store, x_coworker_session, x_coworker_token)
    job = store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.get("/jobs/{job_id}/result")
def get_job_result(
    job_id: str,
    x_coworker_session: Optional[str] = Header(default=None),
    x_coworker_token: Optional[str] = Header(default=None),
):
    require_token(store, x_coworker_session, x_coworker_token)
    res = store.get_result(job_id)
    if not res:
        raise HTTPException(status_code=404, detail="Result not found")
    data, content_type = res
    return {"content_type": content_type, "bytes_base64": base64.b64encode(data).decode("ascii")}
