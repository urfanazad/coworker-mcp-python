from __future__ import annotations

import os
import json
import time
import base64
import hashlib
from typing import List, Dict, Any


class FSAccessError(Exception):
    pass


def _real(path: str) -> str:
    return os.path.realpath(path)


def enforce_within_roots(path: str, roots: List[str]) -> str:
    rp = _real(path)
    rroots = [_real(r) for r in roots]
    if not any(rp == rr or rp.startswith(rr + os.sep) for rr in rroots):
        raise FSAccessError(f"Path is outside allowed roots: {path}")
    return rp


def sha256_file(path: str, max_bytes: int = 25_000_000) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        total = 0
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
            total += len(chunk)
            if total > max_bytes:
                break
    return h.hexdigest()


def write_audit_event(roots: List[str], workspace_root: str, event: Dict[str, Any]) -> None:
    """Append-only JSONL audit file: <workspace_root>/.coworker_audit.jsonl"""
    workspace_root = enforce_within_roots(workspace_root, roots)
    audit_path = os.path.join(workspace_root, ".coworker_audit.jsonl")
    enforce_within_roots(audit_path, roots)

    e = dict(event)
    e["ts_unix_ms"] = int(time.time() * 1000)

    with open(audit_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(e, sort_keys=True) + "\n")


def list_files(root: str, roots: List[str], max_items: int = 500) -> Dict[str, Any]:
    root = enforce_within_roots(root, roots)
    items = []
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            p = os.path.join(dirpath, name)
            try:
                st = os.stat(p)
                items.append(
                    {
                        "path": p,
                        "is_dir": os.path.isdir(p),
                        "size": st.st_size,
                        "mtime": int(st.st_mtime),
                    }
                )
            except Exception:
                continue
            if len(items) >= max_items:
                return {"truncated": True, "items": items}
    return {"truncated": False, "items": items}


def scan_index(root: str, roots: List[str], hash_files: bool = False, max_items: int = 2000) -> Dict[str, Any]:
    root = enforce_within_roots(root, roots)
    indexed = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            try:
                st = os.stat(p)
                rec = {
                    "path": p,
                    "size": st.st_size,
                    "mtime": int(st.st_mtime),
                    "ext": os.path.splitext(fn)[1].lower(),
                }
                if hash_files:
                    rec["sha256"] = sha256_file(p)
                indexed.append(rec)
            except Exception:
                continue
            if len(indexed) >= max_items:
                return {"truncated": True, "files": indexed}
    return {"truncated": False, "files": indexed}


def plan_sha256(plan: Dict[str, Any]) -> str:
    b = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(b).hexdigest()


def propose_organize_plan(root: str, roots: List[str], policy: str = "by_ext") -> Dict[str, Any]:
    """Dry-run move plan: list of {from,to}."""
    root = enforce_within_roots(root, roots)
    plan = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            src = os.path.join(dirpath, fn)
            ext = os.path.splitext(fn)[1].lower().lstrip(".") or "no_ext"
            dest_dir = os.path.join(root, ext) if policy == "by_ext" else os.path.join(root, "misc")
            dest = os.path.join(dest_dir, fn)
            if _real(src) != _real(dest):
                plan.append({"from": src, "to": dest})

    plan_obj = {"policy": policy, "count": len(plan), "moves": plan}
    plan_obj["plan_hash"] = plan_sha256(plan_obj)
    return plan_obj


def execute_plan(plan: Dict[str, Any], roots: List[str], workspace_root: str) -> Dict[str, Any]:
    """Applies move plan idempotently (won't overwrite existing dst) and audits each applied move."""
    workspace_root = enforce_within_roots(workspace_root, roots)

    applied, skipped, errors = 0, 0, []
    for m in plan.get("moves", []):
        src = m["from"]
        dst = m["to"]
        try:
            enforce_within_roots(src, roots)
            enforce_within_roots(dst, roots)

            if not os.path.exists(src):
                skipped += 1
                continue

            os.makedirs(os.path.dirname(dst), exist_ok=True)

            if os.path.exists(dst):
                skipped += 1
                continue

            os.rename(src, dst)
            applied += 1

            write_audit_event(roots, workspace_root, {"action": "move", "from": src, "to": dst})
        except Exception as e:
            errors.append({"from": src, "to": dst, "error": str(e)})

    return {"applied": applied, "skipped": skipped, "errors": errors}


def read_file_safe(path: str, roots: List[str], max_bytes: int = 1_000_000) -> Dict[str, Any]:
    path = enforce_within_roots(path, roots)

    if os.path.isdir(path):
        raise FSAccessError("Path is a directory, not a file")

    size = os.path.getsize(path)
    to_read = min(size, max_bytes)

    with open(path, "rb") as f:
        data = f.read(to_read)

    return {
        "path": path,
        "size": size,
        "read_bytes": len(data),
        "truncated": size > max_bytes,
        "data_base64": base64.b64encode(data).decode("ascii"),
    }


def soft_delete(path: str, roots: List[str], workspace_root: str) -> Dict[str, Any]:
    """Moves file into <workspace_root>/.trash/ with unique suffix. No hard delete."""
    path = enforce_within_roots(path, roots)
    workspace_root = enforce_within_roots(workspace_root, roots)

    if not os.path.exists(path):
        return {"deleted": False, "reason": "not_found", "path": path}

    trash_dir = os.path.join(workspace_root, ".trash")
    os.makedirs(trash_dir, exist_ok=True)

    base = os.path.basename(path)
    unique = f"{base}.{int(time.time()*1000)}"
    dst = os.path.join(trash_dir, unique)

    enforce_within_roots(dst, roots)
    os.rename(path, dst)

    write_audit_event(roots, workspace_root, {"action": "soft_delete", "from": path, "to": dst})

    return {"deleted": True, "from": path, "to": dst}


def restore_from_trash(trash_item_path: str, restore_to: str, roots: List[str], workspace_root: str) -> Dict[str, Any]:
    trash_item_path = enforce_within_roots(trash_item_path, roots)
    restore_to = enforce_within_roots(restore_to, roots)
    workspace_root = enforce_within_roots(workspace_root, roots)

    if not os.path.exists(trash_item_path):
        return {"restored": False, "reason": "not_found", "trash_item": trash_item_path}

    os.makedirs(os.path.dirname(restore_to), exist_ok=True)
    if os.path.exists(restore_to):
        return {"restored": False, "reason": "destination_exists", "restore_to": restore_to}

    os.rename(trash_item_path, restore_to)

    write_audit_event(roots, workspace_root, {"action": "restore", "from": trash_item_path, "to": restore_to})

    return {"restored": True, "from": trash_item_path, "to": restore_to}
