from __future__ import annotations

import asyncio
import json
from .cp_store import CPStore
from .fs_tools import (
    scan_index,
    list_files,
    propose_organize_plan,
    execute_plan,
    read_file_safe,
    plan_sha256,
    soft_delete,
    restore_from_trash,
)

# JobType values (aligned with proto)
SCAN_INDEX = 1
LIST_FILES = 2
READ_FILE = 3
ORGANIZE_PLAN = 4
EXECUTE_PLAN = 5
SOFT_DELETE = 6
RESTORE = 7


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

                else:
                    raise RuntimeError(f"Unsupported job type: {jtype}")

                self.store.complete_job(job_id, ok=True)

            except Exception as e:
                self.store.complete_job(job_id, ok=False, error_message=str(e))
