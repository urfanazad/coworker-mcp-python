from __future__ import annotations

import asyncio
import json
from .cp_store import CPStore
from .fs_tools import (
    read_file_safe,
    plan_sha256,
    soft_delete,
    restore_from_trash,
    enforce_within_roots,
)
from .extended_tools import (
    search_audit_logs,
    search_google_drive,
    record_and_transcribe,
)

SEARCH_ACTIONS = 13
SEARCH_DRIVE = 14
LISTEN_MEETING = 15


class Worker:
    def __init__(self, store: CPStore, worker_id: str):
        self.store = store
        self.worker_id = worker_id

    async def run_forever(self) -> None:
        while True:
            job = self.store.fetch_next_queued_job()
            if not job:
                await asyncio.sleep(0.25)
                continue

            job_id = job["job_id"]
            if not self.store.claim_job_lease(job_id, self.worker_id):
                await asyncio.sleep(0.1)
                continue

            try:
                params = json.loads(job["params_json"])
                roots = json.loads(job["allowed_roots_json"])
                jtype = int(job["type"])

                if jtype == SCAN_INDEX:
                    root = params.get("root", "")
                    hash_files = params.get("hash_files", "false").lower() == "true"
                    out = scan_index(root, roots, hash_files=hash_files)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == LIST_FILES:
                    root = params.get("root", "")
                    out = list_files(root, roots)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == READ_FILE:
                    path = params.get("path", "")
                    max_bytes = int(params.get("max_bytes", "1000000"))
                    out = read_file_safe(path, roots, max_bytes=max_bytes)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == ORGANIZE_PLAN:
                    root = params.get("root", "")
                    policy = params.get("policy", "by_ext")
                    out = propose_organize_plan(root, roots, policy=policy)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == EXECUTE_PLAN:
                    plan_job_id = params.get("plan_job_id", "")
                    approval_token = (job.get("approval_token") or "").strip()
                    if not plan_job_id:
                        raise RuntimeError("Missing plan_job_id")
                    if not approval_token:
                        raise RuntimeError("Missing approval_token")

                    plan_res = self.store.get_result(plan_job_id)
                    if not plan_res:
                        raise RuntimeError("Missing plan result")
                    plan_json = json.loads(plan_res[0].decode("utf-8"))

                    plan_hash = plan_json.get("plan_hash") or plan_sha256(plan_json)

                    if not self.store.validate_approval(approval_token, plan_job_id, plan_hash):
                        raise RuntimeError("Invalid or expired approval token for this plan")

                    workspace_root = params.get("workspace_root", roots[0] if roots else "")
                    out = execute_plan(plan_json, roots, workspace_root=workspace_root)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == SOFT_DELETE:
                    path = params.get("path", "")
                    workspace_root = params.get("workspace_root", roots[0] if roots else "")
                    out = soft_delete(path, roots, workspace_root=workspace_root)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == RESTORE:
                    trash_item = params.get("trash_item_path", "")
                    restore_to = params.get("restore_to", "")
                    workspace_root = params.get("workspace_root", roots[0] if roots else "")
                    out = restore_from_trash(trash_item, restore_to, roots, workspace_root=workspace_root)
                    self.store.put_result(job_id, json.dumps(out).encode("utf-8"), "application/json")

                elif jtype == BROWSE_WEB:
                    url = params.get("url", "")
                    out = browse_web(url)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == CREATE_EXCEL:
                    path = params.get("path", "")
                    data = json.loads(params.get("data", "[]"))
                    enforce_within_roots(path, roots)
                    out = create_excel(path, data)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == CREATE_WORD:
                    path = params.get("path", "")
                    content = params.get("content", "")
                    enforce_within_roots(path, roots)
                    out = create_word(path, content)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == CREATE_PDF:
                    path = params.get("path", "")
                    content = params.get("content", "")
                    enforce_within_roots(path, roots)
                    out = create_pdf(path, content)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == EXECUTE_PYTHON:
                    code = params.get("code", "")
                    out = execute_python_code(code)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == SEARCH_ACTIONS:
                    query = params.get("query", "")
                    workspace_root = params.get("workspace_root", roots[0] if roots else "")
                    out = search_audit_logs(query, workspace_root)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == SEARCH_DRIVE:
                    query = params.get("query", "")
                    out = search_google_drive(query)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                elif jtype == LISTEN_MEETING:
                    duration = int(params.get("duration", "10"))
                    out = record_and_transcribe(duration=duration)
                    self.store.put_result(job_id, out.encode("utf-8"), "text/plain")

                else:
                    raise RuntimeError(f"Unsupported job type: {jtype}")

                self.store.complete_job(job_id, ok=True)

            except Exception as e:
                self.store.complete_job(job_id, ok=False, error_message=str(e))
