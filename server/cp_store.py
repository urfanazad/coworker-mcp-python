from __future__ import annotations

import sqlite3
import time
from typing import Optional, Tuple, Any, Dict


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS sessions (
  session_id TEXT PRIMARY KEY,
  token TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS jobs (
  job_id TEXT PRIMARY KEY,
  dedupe_key TEXT NOT NULL,
  type INTEGER NOT NULL,
  status INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL,
  started_at_ms INTEGER,
  finished_at_ms INTEGER,
  error_message TEXT,
  params_json TEXT NOT NULL,
  allowed_roots_json TEXT NOT NULL,

  lease_owner TEXT,
  lease_expires_at_ms INTEGER,

  approval_token TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_dedupe ON jobs(dedupe_key, type);

CREATE TABLE IF NOT EXISTS results (
  job_id TEXT PRIMARY KEY,
  result_bytes BLOB NOT NULL,
  content_type TEXT NOT NULL,
  created_at_ms INTEGER NOT NULL,
  FOREIGN KEY(job_id) REFERENCES jobs(job_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS approvals (
  token TEXT PRIMARY KEY,
  plan_job_id TEXT NOT NULL,
  plan_hash TEXT NOT NULL,
  expires_at_ms INTEGER NOT NULL,
  created_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_approvals_expires ON approvals(expires_at_ms);
"""

# JobStatus mapping (aligned to proto)
QUEUED = 1
RUNNING = 2
SUCCEEDED = 3
FAILED = 4
CANCELED = 5


def now_ms() -> int:
    return int(time.time() * 1000)


class CPStore:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init(self) -> None:
        conn = self._conn()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    # ---------- sessions ----------
    def create_session(self, session_id: str, token: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO sessions(session_id, token, created_at_ms) VALUES(?,?,?)",
                (session_id, token, now_ms()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_session_token(self, session_id: str) -> Optional[str]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT token FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            return None if row is None else str(row["token"])
        finally:
            conn.close()

    # ---------- jobs ----------
    def upsert_job_if_new(
        self,
        job_id: str,
        dedupe_key: str,
        jtype: int,
        params_json: str,
        allowed_roots_json: str,
        approval_token: Optional[str],
    ) -> Tuple[bool, str]:
        """Returns (created_new, existing_or_new_job_id). Enforces idempotency by unique(dedupe_key, type)."""
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT job_id FROM jobs WHERE dedupe_key=? AND type=?",
                (dedupe_key, jtype),
            ).fetchone()
            if row is not None:
                return (False, str(row["job_id"]))

            conn.execute(
                """INSERT INTO jobs(
                       job_id, dedupe_key, type, status, created_at_ms,
                       params_json, allowed_roots_json, approval_token
                   )
                   VALUES(?,?,?,?,?,?,?,?)""",
                (
                    job_id,
                    dedupe_key,
                    jtype,
                    QUEUED,
                    now_ms(),
                    params_json,
                    allowed_roots_json,
                    approval_token,
                ),
            )
            conn.commit()
            return (True, job_id)
        finally:
            conn.close()

    def fetch_next_queued_job(self) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT * FROM jobs WHERE status=? ORDER BY created_at_ms ASC LIMIT 1",
                (QUEUED,),
            ).fetchone()
            return None if row is None else dict(row)
        finally:
            conn.close()

    def claim_job_lease(self, job_id: str, worker_id: str, lease_ms: int = 30_000) -> bool:
        """Lease claim: transition QUEUED->RUNNING, or reclaim RUNNING if lease expired."""
        conn = self._conn()
        try:
            t = now_ms()
            expires = t + lease_ms
            cur = conn.execute(
                """UPDATE jobs
                   SET status=?,
                       started_at_ms=COALESCE(started_at_ms, ?),
                       lease_owner=?,
                       lease_expires_at_ms=?
                   WHERE job_id=?
                     AND (
                        status=?
                        OR (
                           status=?
                           AND lease_expires_at_ms IS NOT NULL
                           AND lease_expires_at_ms < ?
                        )
                     )""",
                (RUNNING, t, worker_id, expires, job_id, QUEUED, RUNNING, t),
            )
            conn.commit()
            return cur.rowcount == 1
        finally:
            conn.close()

    def complete_job(self, job_id: str, ok: bool, error_message: Optional[str] = None) -> None:
        conn = self._conn()
        try:
            status = SUCCEEDED if ok else FAILED
            conn.execute(
                """UPDATE jobs
                   SET status=?,
                       finished_at_ms=?,
                       error_message=?,
                       lease_owner=NULL,
                       lease_expires_at_ms=NULL
                   WHERE job_id=?""",
                (status, now_ms(), error_message, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            return None if row is None else dict(row)
        finally:
            conn.close()

    # ---------- results ----------
    def put_result(self, job_id: str, result_bytes: bytes, content_type: str) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO results(job_id, result_bytes, content_type, created_at_ms) VALUES(?,?,?,?)",
                (job_id, result_bytes, content_type, now_ms()),
            )
            conn.commit()
        finally:
            conn.close()

    def get_result(self, job_id: str) -> Optional[Tuple[bytes, str]]:
        conn = self._conn()
        try:
            row = conn.execute(
                "SELECT result_bytes, content_type FROM results WHERE job_id=?",
                (job_id,),
            ).fetchone()
            if row is None:
                return None
            return (bytes(row["result_bytes"]), str(row["content_type"]))
        finally:
            conn.close()

    # ---------- approvals ----------
    def create_approval(self, token: str, plan_job_id: str, plan_hash: str, ttl_ms: int) -> None:
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO approvals(token, plan_job_id, plan_hash, expires_at_ms, created_at_ms) VALUES(?,?,?,?,?)",
                (token, plan_job_id, plan_hash, now_ms() + ttl_ms, now_ms()),
            )
            conn.commit()
        finally:
            conn.close()

    def validate_approval(self, token: str, plan_job_id: str, plan_hash: str) -> bool:
        conn = self._conn()
        try:
            t = now_ms()
            row = conn.execute(
                """SELECT token FROM approvals
                   WHERE token=? AND plan_job_id=? AND plan_hash=? AND expires_at_ms>?""",
                (token, plan_job_id, plan_hash, t),
            ).fetchone()
            return row is not None
        finally:
            conn.close()

    def purge_expired_approvals(self) -> None:
        conn = self._conn()
        try:
            t = now_ms()
            conn.execute("DELETE FROM approvals WHERE expires_at_ms<=?", (t,))
            conn.commit()
        finally:
            conn.close()
