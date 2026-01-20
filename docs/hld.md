# High-Level Design (HLD) — Coworker MCP (Python)

**Version:** 1.0  
**Status:** Draft (implementation-aligned)

---

## 1. Purpose
This document describes the high-level design for **Coworker MCP**, a local-first AI coworker that safely operates on a user’s filesystem using job-based execution, approval gates, and audit logging. The design is **CAP-aware** and uses **Protocol Buffers (Protobuf)** as the authoritative internal contract.

---

## 2. Goals
- Provide **workspace-scoped** filesystem automation.
- Ensure **safety and correctness** via plans, approvals, and audit logs.
- Use **job orchestration** with idempotency and leases.
- Remain **local-first**, with a clean path to multi-node deployment.

## 3. Non-Goals
- Full multi-node deployment in v1.
- Running code inside the browser extension.
- Hard delete of user files (soft delete only).

---

## 4. CAP Design Rationale

### 4.1 CAP Assumptions
- **Partition tolerance** is assumed (process crashes, restarts, I/O failures).
- The system explicitly chooses **Consistency over Availability** for mutations.

### 4.2 CP (Consistency-First) Components
The following are strongly consistent and transactionally enforced:
- Job lifecycle state
- Idempotency (dedupe keys)
- Worker leases
- Approval tokens
- Execution results
- Audit references

**Rationale:** Incorrect or duplicated file mutations are unacceptable.

### 4.3 AP (Availability-First) Components (Optional/Future)
- Read-only status polling
- Cached search or index data

**Rationale:** Stale reads are acceptable for observation, not for mutation.

---

## 5. System Context

```mermaid
flowchart LR
  User((User)) --> Ext[Browser Extension UI]
  Ext -->|HTTP/JSON + Token| API[Local Coworker API]
  API --> CP[(CP Store
SQLite WAL)]
  API --> Worker[Worker Pool]
  Worker --> FS[(Local File System)]
  Worker --> Audit[Audit Log
JSONL]
```

---

## 6. Logical Architecture

```mermaid
flowchart TB
  subgraph Client
    Ext[Extension Popup]
    BG[Extension Service Worker]
    Ext --> BG
  end

  subgraph Server[Local Coworker Server]
    API[FastAPI Gateway]
    Auth[Session & Token Guard]
    Jobs[Job API]
    Approve[Approval API]
    Results[Results API]
    Worker[Workers]
    Tools[Filesystem Tools]
    Proto[Protobuf Schemas]
  end

  subgraph Storage
    CP[(SQLite WAL)]
    Audit[Audit JSONL]
  end

  subgraph OS
    FS[(Filesystem)]
  end

  BG --> API
  API --> Auth
  API --> Jobs
  API --> Approve
  API --> Results

  Jobs --> CP
  Approve --> CP
  Results --> CP

  Worker --> CP
  Worker --> Tools
  Tools --> FS
  Tools --> Audit

  Proto -. contracts .- API
  Proto -. contracts .- Worker
```

---

## 7. Key Flows

### 7.1 Handshake
```mermaid
sequenceDiagram
  participant E as Extension
  participant A as API
  participant S as CP Store

  E->>A: POST /handshake
  A->>S: Create session + token
  A-->>E: session_id, token
```

### 7.2 Plan → Approve → Execute
```mermaid
sequenceDiagram
  participant E as Extension
  participant A as API
  participant S as CP Store
  participant W as Worker
  participant F as File System
  participant L as Audit Log

  E->>A: Submit ORGANIZE_PLAN job
  A->>S: Insert job (QUEUED)

  W->>S: Claim lease
  W->>W: Generate plan + plan_hash
  W->>S: Store plan result

  E->>A: POST /approve
  A->>S: Validate plan + mint approval token

  E->>A: Submit EXECUTE_PLAN job
  A->>S: Insert job (QUEUED)

  W->>S: Validate approval token
  W->>F: Apply filesystem changes
  W->>L: Append audit entries
  W->>S: Store execution result
```

---

## 8. Deployment View (Local)

```mermaid
flowchart LR
  Browser --> Extension
  Extension -->|localhost| API
  API --> SQLite
  API --> Workers
  Workers --> Filesystem
  Workers --> AuditLog
```

---

## 9. Data Model (CP Store)

```mermaid
erDiagram
  SESSIONS {
    text session_id PK
    text token
    int created_at_ms
  }

  JOBS {
    text job_id PK
    text dedupe_key
    int type
    int status
    int created_at_ms
    int started_at_ms
    int finished_at_ms
    text params_json
    text allowed_roots_json
    text lease_owner
    int lease_expires_at_ms
    text approval_token
  }

  RESULTS {
    text job_id PK
    blob result_bytes
    text content_type
  }

  APPROVALS {
    text token PK
    text plan_job_id
    text plan_hash
    int expires_at_ms
  }

  JOBS ||--|| RESULTS : produces
```

---

## 10. Security Model

### 10.1 Workspace Enforcement
- All paths are realpath-validated.
- No traversal or symlink escape outside allowed roots.

### 10.2 Localhost Protection
- Every request requires a session token.
- Tokens are issued via explicit handshake.

### 10.3 Safe Mutation
- All write actions require approval tokens.
- Approval tokens bind to a specific plan hash and TTL.

### 10.4 Auditability
- Append-only JSONL audit file inside workspace.
- Every mutation is traceable and reversible.

---

## 11. Reliability Guarantees
- Idempotent job submission via dedupe keys.
- Lease-based worker execution prevents duplication.
- Failed workers can be safely retried after lease expiry.

---

## 12. Extensibility
- Replace SQLite with etcd/CockroachDB for multi-node CP.
- Add AP caches for search and indexing.
- Expose gRPC alongside HTTP without breaking contracts.

---

## 13. Summary
This design prioritizes **correctness, safety, and trust**. By combining CAP-aware state management with Protobuf-defined contracts, Coworker MCP avoids silent failure modes and provides a solid foundation for trustworthy AI-assisted filesystem operations.
