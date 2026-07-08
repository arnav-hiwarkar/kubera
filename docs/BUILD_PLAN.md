# Kubera — Build Plan & Phase Specification

**Project:** Kubera — centralized management/compliance platform for mid-to-large Indian private limited companies.
**Stack:** FastAPI (async) + PostgreSQL + SQLAlchemy 2.0 (async) + React frontend + Redis/Celery + Docker Compose, self-hosted on a single VPS in India.
**Build order:** docVault → AuditEase → SecretarialEase → ROC Compliance → Asset Management → Sales Tracking → KRA & Appraisal.

This document is the agreed technical spec, to be handed to an Antigravity agent session as the initial planning Artifact. Each module section below is written to be executable as a standalone task once its dependencies (previous modules) exist.

---

## 1. Architecture Principles

- **Monolith, modular routers.** One FastAPI app, one Postgres database. Routers namespaced per module: `/api/v1/docvault`, `/api/v1/auditease`, `/api/v1/secretarial`, `/api/v1/roc`, `/api/v1/assets`, `/api/v1/sales`, `/api/v1/kra`.
- **Multi-tenant, shared tables.** Every company-owned table carries a `company_id` FK. No schema-per-tenant. A shared `TenantScopedMixin` base model + a query-scoping dependency (injects `company_id` filter from the authenticated principal) prevents cross-tenant leaks. **This is the single highest-risk area — cross-tenant data leakage — and must have dedicated tests per module.**
- **Async everywhere.** SQLAlchemy 2.0 async engine, `asyncpg` driver, async endpoint handlers.
- **Background jobs via Celery + Redis.** Used for: file encryption/decryption on large uploads, PDF/report generation, xlsx export generation, overdue-status recalculation (scheduled), nightly backups.
- **Deployment.** Single VPS (India-hosted). Docker Compose stack: `api` (FastAPI), `worker` (Celery), `beat` (Celery scheduled tasks), `postgres`, `redis`, `nginx` (reverse proxy/TLS termination). No S3 — local disk volume for the vault.

---

## 2. Auth Architecture (v1 scope)

Two entirely separate identity systems. They do not share a users table, login flow, or token issuer.

### 2.1 Company side — v1 minimal
- `Company` table: company profile, one row per client.
- `CompanyAdmin` table: **exactly one admin user per company in v1.** No employee/role management, no invite-a-teammate flow, no permission editor. These are all deferred to a post-v1 "user management panel" phase — the schema should not preclude adding them later (i.e. don't hardcode "one admin" as a DB constraint, just don't build the UI/endpoints for more).
- Onboarding is **internal-only**: Kubera team creates `Company` + `CompanyAdmin` via an internal, auth-protected endpoint or a CLI seed script. No public self-serve signup in v1.
- JWT access + refresh tokens for CompanyAdmin login.

### 2.2 Auditor side — fully separate
- `Auditor` table: independent identity, own signup/login, own JWT issuer scope (tokens tagged `principal_type=auditor`, never valid against company-side endpoints and vice versa).
- **Invite-gated account creation.** An auditor cannot self-register. A `CompanyAdmin` creates an `AuditEngagement` and invites an auditor by email. This generates an `AuditorInvite` (token, expiry, target email, engagement_id).
  - If no `Auditor` account exists for that email: the invite link lets them set a password and creates the account, linked to that engagement.
  - If an `Auditor` account already exists for that email (invited previously by a different company): the invite just adds a new engagement grant to the existing account. One auditor identity can hold grants across many companies (`Auditor` ↔ `AuditEngagement` is many-to-many via the grant).
- **Engagement-scoped access.** `AuditEngagement` = company + period (e.g. "FY 2025-26 Statutory Audit") + status (`invited`, `active`, `closed`). An auditor's access is entirely defined by their active engagement grants — no standing/global access to a company.
- **Full access within an assigned engagement.** Once granted an engagement, the auditor has full access to that engagement's TB, ledgers, and audit-entry workflow (no further per-ledger sub-scoping in v1).

---

## 3. docVault (Phase 1 — build first)

Central document store. Every other module writes into this; it does not have its own storage logic.

### 3.1 Data model
- `Document`: id, company_id, current_version_id, bucket_id (nullable), status, title, doc_type (nullable, links to module-defined types later), tags, created_by, timestamps.
- `DocumentVersion`: id, document_id, storage_path (random UUID filename), original_filename, mime_type, size_bytes, checksum, encrypted_dek (see 3.3), uploaded_by, uploaded_at, version_number.
- `Bucket`: id, company_id, name, created_by. Company-level, shared across all modules (e.g. "Indirect Tax"). Admin can create/delete.
- `DocumentAccessOverride` (optional per-file ACL): document_id, principal (user or role), permission level. Defaults to inherit from module/bucket permission unless a row exists here.
- Status enum (shared base, all documents): `uploaded`, `pending_approval`, `action_required`, `verified`, `submitted`, `overdue`, `archived`. Modules may layer their own workflow states on top but must map down to this enum for the docVault UI.

### 3.2 Storage layout
- Local disk, mounted Docker volume: `/data/vault/{company_id}/{uuid}.enc` — **all files for a company in one flat folder**, filenames fully randomized (UUID + `.enc`), no meaning in the path itself. All human-readable metadata (real filename, type, bucket, status, tags, version) lives only in Postgres.
- Each company's files are isolated to their own `{company_id}` subfolder — no cross-company folder sharing at the filesystem level, matching the DB-level tenant isolation.

### 3.3 Encryption
- Envelope encryption: each `DocumentVersion` gets its own Data Encryption Key (DEK), AES-256-GCM used to encrypt file bytes before writing to disk.
- DEKs are themselves encrypted by a single Key Encryption Key (KEK) held in the server's environment/secrets file (not in the DB). Encrypted DEK stored alongside the version row.
- Decrypt-on-read: file is decrypted into memory (or a short-lived temp stream) only when served to an authorized request; never persisted to disk unencrypted.

### 3.4 Versioning
- Every re-upload creates a new immutable `DocumentVersion` row + new encrypted file on disk. `Document.current_version_id` moves forward. Old versions remain retrievable (compliance/audit-trail requirement).

### 3.5 Endpoints (v1)
- `POST /docvault/buckets`, `DELETE /docvault/buckets/{id}`, `GET /docvault/buckets`
- `POST /docvault/documents` (upload, multipart, optional bucket_id) → creates Document + first Version
- `POST /docvault/documents/{id}/versions` (re-upload)
- `GET /docvault/documents` (filter by bucket, status, tag, doc_type)
- `GET /docvault/documents/{id}` (metadata), `GET /docvault/documents/{id}/download` (decrypt + stream), `GET /docvault/documents/{id}/versions`
- `PATCH /docvault/documents/{id}` (status change, bucket move, tags)
- `DELETE /docvault/documents/{id}` (soft delete → archived, not hard delete, for audit trail)

### 3.6 Backup (infra task, part of this phase's scaffolding)
- Nightly Celery Beat job: `pg_dump` the database + tar the `/data/vault` folder, write to a local backup directory on the same VM. Off-VM shipping (rsync/S3) left as a config value to fill in later — the script should accept a destination target as an env var so it's a one-line change when ready.

---

## 4. AuditEase (Phase 2)

Depends on: docVault (final reports/annual report get stored there), Auditor auth (2.2).

### 4.1 Trial Balance import
- Flexible column-mapping importer: any xlsx/csv, any sheet, user maps arbitrary source columns → target schema: `ledger_code` (optional), `ledger_name`, `opening_balance`, `debit`, `credit`, `closing_balance`.
- On import, validate `opening_balance + debit − credit == closing_balance` per row; mismatches are flagged as warnings (not blocked) and surfaced to the importer.

### 4.2 Ledger group mapping
- Standard Schedule III (Companies Act, 2013) aligned group/sub-group taxonomy shipped as seed data. Each imported ledger is mapped to a group (e.g. Share Capital, Reserves & Surplus, Current Liabilities, Revenue from Operations). This mapping drives automatic PnL/Balance Sheet generation later.

### 4.3 Audit engagements & entries
- `AuditEngagement` (see §2.2): company, period, status, invited auditor(s).
- `AuditEntry`: engagement_id, created_by (auditor), description, status (`proposed`, `approved`, `rejected`), timestamps.
- `AuditEntryLine`: entry_id, ledger_id, side (`debit`/`credit`), amount.
- Supports 1:1 (one debit ledger, one credit ledger), 1:many (one debit, multiple credit lines), many:many (multiple debit lines, multiple credit lines) — modeled generically as a list of lines per entry, no special-casing by type.
- **Validation (app-layer, not a DB constraint):** an entry can only move from `proposed` to submitted-for-approval if `sum(lines where side=debit) == sum(lines where side=credit)`.
- Approval: company admin approves/rejects each proposed entry with an optional comment (single-step for v1; model as a generic approval-chain table so multi-step can be added later without a schema rewrite).

### 4.4 Statement generation
- PnL and Balance Sheet auto-generated as a "system draft" from ledger-group mappings + approved entries (Schedule III format).
- Manual line-item override supported post-generation, with an audit log of what changed and by whom.
- Annual report v1 = PnL + BS + a basic Notes to Accounts placeholder, exported as PDF, stored back into docVault.
- Data model includes a `ReportTemplate` entity (JSON-based, with placeholder tokens like `{{pnl_table}}`, `{{ledger:revenue}}`) now, even though the template *editor* UI is a future phase — so the backend doesn't need rework later.

### 4.5 Endpoints (v1)
- `POST /auditease/trial-balance/import`, `GET /auditease/trial-balance`
- `POST /auditease/ledgers/{id}/map-group`
- `POST /auditease/engagements`, `POST /auditease/engagements/{id}/invite-auditor`
- `POST /auditease/engagements/{id}/entries` (auditor), `PATCH /auditease/entries/{id}/approve|reject` (company admin)
- `POST /auditease/engagements/{id}/generate-statements`, `GET /auditease/engagements/{id}/statements`
- `POST /auditease/engagements/{id}/generate-annual-report` → stores PDF in docVault

---

## 5. SecretarialEase (Phase 3)

Depends on: docVault.

- `DocumentType`: company_id (nullable for system-shipped base types), name, template_file (docVault reference), metadata_schema (JSON — configurable fields per type, e.g. MoM requires meeting_date, attendees, resolutions).
- Base library shipped: Minutes of Meeting, Board Resolution, DIR-12-style internal record, general "Directorial Meeting" type. Companies can create additional custom types (own template + own metadata schema).
- `MeetingRecord`: company_id, doc_type_id, structured metadata (per schema), linked document (uploaded MoM, stored encrypted in docVault, auto-tagged/bucketed by type).
- Flow: create meeting record → download template → (offline) fill it → upload → stored in docVault with proper tags/bucket/title derived from the type + metadata.
- v1 is document-centric only — no scheduling/agenda engine.

---

## 6. ROC Compliance (Phase 4)

Depends on: docVault, same `DocumentType` mechanism as SecretarialEase (shared table, just a different set of seeded types).

- Research and seed standard Indian pvt ltd ROC form types (e.g. AOC-4, MGT-7, ADT-1, DIR-12, DPT-3) as base `DocumentType` rows with templates.
- Each ROC `DocumentType` carries a `due_date_rule` (e.g. "30 days from AGM date", "60 days from AGM date") so the docVault `overdue` status is computed automatically by a scheduled job rather than set manually.
- Same download-template → fill → upload → encrypted storage flow as SecretarialEase.
- Companies can edit/extend templates and create custom ROC document types beyond the seeded base set.

---

## 7. Asset Management (Phase 5)

- `AssetRecord`: company_id, name, cost, purchase_date, category, custom_fields (JSONB for company-defined extra columns), created_by, timestamps.
- Company can define its own extra fields (stored in `custom_fields`) without a schema migration.
- Import: same flexible column-mapper as Trial Balance import (reusable shared import utility — build it generically in Phase 2 so Phase 5 just reuses it).
- Full CRUD (view/add/edit/delete) + xlsx/csv export.
- Depreciation fields (useful life, method) stored but not calculated in v1 — reserved for a future phase.

---

## 8. Sales Tracking (Phase 6)

- `SalesEntry`: company_id, custom_fields (JSONB, same pattern as Assets — date, title, customer, cost, duration are just default custom_fields keys, fully company-editable), created_by (auto-tagged to logged-in user), timestamps.
- Visibility: scoped by manager-hierarchy — reuses the same employee↔manager mapping built for KRA (§9.1), so build that hierarchy table once, shared across Sales and KRA.
- Full CRUD + export, same reusable import/export utilities as Assets/Trial Balance.

---

## 9. KRA & Appraisal (Phase 7 — last)

- `Employee`: company_id, name, self-referencing `manager_id` FK (one direct manager per employee; no matrix reporting in v1).
- `KraPeriod`: company_id, label, start_date, end_date, cycle_type (`yearly`/`quarterly`/`custom`) — company-level setting, same cycle for all employees, configurable FY start month.
- `KraItem`: employee_id, period_id, description, target_type (enum: `numeric`, `percentage`, `boolean`, `rating`), target_value, current_value, status (`draft`, `plan_approved`, `in_progress`, `achievement_approved`).
- Two distinct approval gates, both by the employee's manager:
  1. **Plan approval** — targets locked in at period start.
  2. **Achievement approval** — final self-reported progress reviewed/approved at period end.
- During the period, the employee can freely update `current_value` (self-reported progress) until achievement approval locks it.
- Export: per-employee PDF/xlsx (target vs achieved), and an org-wide export across all employees for a given period (primary HR/appraisal-cycle use case).

---

## 10. Build Sequence Summary

| Phase | Module | Key new infra introduced |
|---|---|---|
| 0 | Scaffolding | Docker Compose (api, worker, beat, postgres, redis, nginx), async SQLAlchemy base, tenant-scoping dependency, JWT auth (CompanyAdmin) |
| 1 | docVault | Envelope encryption, versioning, buckets, backup job |
| 2 | AuditEase | Auditor auth + engagements, flexible column-mapper importer, double-entry validation, report generation, ReportTemplate schema |
| 3 | SecretarialEase | DocumentType + metadata_schema pattern |
| 4 | ROC Compliance | Reuses DocumentType pattern + due_date_rule/overdue automation |
| 5 | Asset Management | Reuses flexible importer, JSONB custom_fields pattern |
| 6 | Sales Tracking | Reuses custom_fields pattern, introduces manager-hierarchy |
| 7 | KRA & Appraisal | Reuses manager-hierarchy, two-gate approval workflow |

Each phase should ship with: Alembic migration(s), pytest coverage for the happy path + a cross-tenant-leak boundary test, and full Swagger/OpenAPI docs (no separate Postman export needed for v1).
