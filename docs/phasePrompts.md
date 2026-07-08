# Kubera — Antigravity Phase Prompts

One prompt per phase. Use them **in order, one at a time, in a fresh conversation per phase**, only after the previous phase is reviewed, tested, and committed to git. Each prompt assumes `docs/BUILD_PLAN.md` (the full spec) sits in your project root — adjust the path if yours differs.

Before every phase prompt, also paste a one-line status note about what already exists (a template is included at the top of each prompt below — fill in the bracketed part once earlier phases are done).

---

## Phase 0 — Scaffolding

```
@docs/BUILD_PLAN.md

This is a fresh project. Build Phase 0 only, per §2 and §10 of the plan:

1. Docker Compose stack: api (FastAPI, async), postgres, redis,
   celery worker, celery beat, nginx as reverse proxy.
2. Async SQLAlchemy 2.0 + asyncpg, Alembic set up and working
   (an initial empty migration should apply cleanly).
3. The TenantScopedMixin base model and a company_id-scoping
   dependency/middleware, exactly as described in §2 — this is the
   most important primitive in the whole project, get it right here
   since every later module depends on it.
4. CompanyAdmin table + JWT access/refresh auth per §2.1. Internal-only
   account creation (a protected internal endpoint or CLI seed script) —
   no public signup.
5. A .env-based secrets setup, confirmed in .gitignore.

Before writing any code, give me the Task List and Implementation Plan
for review. Stop there and wait for my approval.

Testing requirement: pytest coverage for
  (a) the seed/creation of a CompanyAdmin,
  (b) login issuing a valid JWT,
  (c) a protected endpoint rejecting an invalid/missing token,
  (d) a basic proof that the tenant-scoping dependency actually filters
      by company_id (even with a dummy protected table for this test).
Run the suite yourself via terminal and paste the real pass/fail output
into the Walkthrough — don't just claim it passes.

Do not commit secrets. Confirm .env is gitignored before finishing.
```

---

## Phase 1 — docVault

```
@docs/BUILD_PLAN.md

Status: Phase 0 (scaffolding, auth, tenant-scoping) is done and
committed — see [describe location, e.g. "app/core/"].

Now build Phase 1, docVault, per §3 of the plan:

1. Models: Document, DocumentVersion, Bucket, DocumentAccessOverride,
   the shared status enum.
2. Storage: local disk volume at /data/vault/{company_id}/{uuid}.enc,
   randomized filenames, all real metadata in Postgres only.
3. Envelope encryption: per-version DEK (AES-256-GCM), DEK encrypted
   by a single KEK read from environment (never stored in DB, never
   logged, never printed to terminal output).
4. Versioning: re-upload creates a new immutable version, current
   pointer moves forward, old versions stay retrievable.
5. All endpoints listed in §3.5.
6. The nightly backup Celery Beat job per §3.6 (pg_dump + tar the
   vault folder to a local backup dir; destination path as an env var
   for later off-VM shipping).

Give me the Task List and Implementation Plan first. Wait for approval
before writing code.

Testing requirement: pytest coverage for upload, re-upload (version
increment), download (decrypt correctly, byte-for-byte match with
original), status/bucket updates, and — most important — a
cross-tenant isolation test: Company A's token must never be able to
list, fetch metadata for, or download Company B's documents or
buckets, even by guessing an ID. Run the tests via terminal and paste
real output into the Walkthrough.

Never print decrypted file bytes, the KEK, or any encrypted DEK to
terminal/logs during development or testing.
```

---

## Phase 2 — AuditEase

```
@docs/BUILD_PLAN.md

Status: Phase 0 and Phase 1 (docVault) are done and committed — see
[location]. Reuse docVault for storing generated reports; do not
duplicate storage/encryption logic.

Now build Phase 2, AuditEase, per §4:

1. The flexible column-mapper import utility (any xlsx/csv, any sheet,
   arbitrary column → target field mapping) — build this as a reusable
   shared utility, not AuditEase-specific, since Phase 5 (Assets) and
   Phase 6 (Sales) will reuse it verbatim.
2. Trial balance import using that utility, mapping to ledger_code
   (optional), ledger_name, opening_balance, debit, credit,
   closing_balance, with the opening+debit-credit=closing validation
   as a soft warning (not blocking).
3. Schedule III ledger-group taxonomy as seed data, and ledger-to-group
   mapping.
4. The separate Auditor auth system per §2.2: invite-gated account
   creation, AuditEngagement (company + period + status), full access
   within an assigned engagement, many-to-many Auditor↔engagement
   grants across companies. Auditor JWTs must be structurally
   incompatible with CompanyAdmin JWTs (different principal_type,
   verified on every protected route).
5. AuditEntry + AuditEntryLine supporting 1:1, 1:many, many:many,
   with the app-layer (not DB constraint) validation that
   sum(debit lines) == sum(credit lines) before an entry can be
   submitted for approval. Single-step approval by CompanyAdmin.
6. PnL/Balance Sheet auto-generation from ledger groups + approved
   entries, with manual override + change log. The ReportTemplate
   JSON schema (placeholder tokens) even though no editor UI exists
   yet. Annual report export as PDF, stored into docVault.
7. All endpoints in §4.5.

Give me the Task List and Implementation Plan first. Wait for approval.

Testing requirement: pytest coverage for TB import + validation
warnings, ledger-group mapping, the auditor invite flow (new email
creates account; existing email adds a new engagement grant to the
same account), engagement-scoped access (an auditor with no grant for
Company B must be rejected on all Company B endpoints), the
debit=credit submission validation (reject unbalanced entries), and
statement generation producing correct totals from a known fixture
trial balance. Run the suite via terminal, paste real output into the
Walkthrough.
```

---

## Phase 3 — SecretarialEase

```
@docs/BUILD_PLAN.md

Status: Phases 0–2 are done and committed — see [location]. Reuse
docVault for storage and the existing auth/tenant-scoping.

Now build Phase 3, SecretarialEase, per §5:

1. DocumentType model (company_id nullable for system-shipped types,
   template_file reference into docVault, metadata_schema as JSON for
   per-type structured fields). Build this generically — Phase 4 (ROC)
   will reuse the same table with a different seed set, do not build a
   SecretarialEase-specific version.
2. Seed base types: Minutes of Meeting, Board Resolution, a general
   Directorial Meeting type — each with a template file and a sensible
   metadata schema (e.g. MoM: meeting_date, attendees, resolutions).
3. MeetingRecord model tying a doc_type + structured metadata +
   uploaded document (stored encrypted in docVault, auto-tagged/
   bucketed based on the type).
4. Companies can create their own custom document types on top of the
   seeded ones (own template, own metadata_schema).
5. Endpoints: create/list/edit document types, create a meeting record,
   download template, upload the filled document (creates the docVault
   document + links it to the meeting record).

Give me the Task List and Implementation Plan first. Wait for approval.

Testing requirement: pytest coverage for seeded type presence, custom
type creation, meeting record creation with metadata validated against
its type's schema, and the upload-then-linked-in-docVault flow
end-to-end (including that it lands in the right bucket/tags). Run the
suite via terminal, paste real output into the Walkthrough.
```

---

## Phase 4 — ROC Compliance

```
@docs/BUILD_PLAN.md

Status: Phases 0–3 are done and committed — see [location]. Reuse the
DocumentType/MeetingRecord-style pattern from SecretarialEase; do not
rebuild it.

Now build Phase 4, ROC Compliance, per §6:

1. Research and seed standard Indian private limited company ROC form
   types (e.g. AOC-4, MGT-7, ADT-1, DIR-12, DPT-3) as DocumentType rows
   with templates.
2. Add a due_date_rule field to DocumentType (e.g. "30 days from AGM
   date", "60 days from AGM date") and a scheduled job (Celery Beat)
   that computes and flags a linked document as "overdue" in docVault
   automatically based on this rule and a recorded reference date
   (e.g. AGM date) — don't require manual overdue-marking.
3. Same download-template → fill → upload → encrypted docVault storage
   flow as SecretarialEase. Companies can edit templates and add custom
   ROC document types beyond the seeded base set.

Give me the Task List and Implementation Plan first. Wait for approval.

Testing requirement: pytest coverage for seeded ROC types existing,
custom ROC type creation, and — most importantly — the overdue
computation job: given a fixture reference date and due_date_rule,
confirm the status flips to overdue at the right time and not before.
Run the suite via terminal, paste real output into the Walkthrough.
```

---

## Phase 5 — Asset Management

```
@docs/BUILD_PLAN.md

Status: Phases 0–4 are done and committed — see [location]. Reuse the
flexible column-mapper import utility built in Phase 2 verbatim — do
not write a new importer.

Now build Phase 5, Asset Management, per §7:

1. AssetRecord model: company_id, name, cost, purchase_date, category,
   custom_fields as JSONB for company-defined extra columns, created_by,
   timestamps. Depreciation fields (useful_life, method) present but
   unused/uncalculated for now.
2. Import via the shared column-mapper utility (any xlsx/csv → these
   fields + arbitrary custom_fields).
3. Full CRUD endpoints (create/view/edit/delete an asset) plus xlsx/csv
   export of the full asset list including custom_fields.

Give me the Task List and Implementation Plan first. Wait for approval.

Testing requirement: pytest coverage for import via the shared mapper
(including custom_fields import), full CRUD, export producing a
correctly formatted xlsx with dynamic columns, and cross-tenant
isolation (Company A cannot see/edit/export Company B's assets). Run
the suite via terminal, paste real output into the Walkthrough.
```

---

## Phase 6 — Sales Tracking

```
@docs/BUILD_PLAN.md

Status: Phases 0–5 are done and committed — see [location]. Reuse the
custom_fields JSONB pattern from Assets and the shared column-mapper
import utility. This phase also introduces the employee↔manager
hierarchy that Phase 7 (KRA) will reuse — build it here as a
standalone, reusable Employee model, not something Sales-specific.

Now build Phase 6, Sales Tracking, per §8:

1. Employee model: company_id, name, self-referencing manager_id FK
   (one direct manager per employee).
2. SalesEntry model: company_id, custom_fields JSONB (date, title,
   customer, cost, duration as default keys, fully company-editable),
   created_by auto-tagged to the logged-in user, timestamps.
3. Visibility rule: a manager can see their direct reports' entries
   (via the Employee hierarchy), in addition to their own.
4. Full CRUD + import/export reusing the shared utilities from
   Phase 2/5.

Give me the Task List and Implementation Plan first. Wait for approval.

Testing requirement: pytest coverage for CRUD, import/export, the
created_by auto-tagging, and the manager-visibility rule (a manager
sees their reports' entries; an unrelated employee does not see them).
Run the suite via terminal, paste real output into the Walkthrough.
```

---

## Phase 7 — KRA & Appraisal

```
@docs/BUILD_PLAN.md

Status: Phases 0–6 are done and committed — see [location]. Reuse the
Employee/manager hierarchy built in Phase 6 — do not create a second
employee table.

Now build Phase 7, KRA & Appraisal, per §9. This is the last phase:

1. KraPeriod model: company_id, label, start_date, end_date, cycle_type
   (yearly/quarterly/custom), company-level (same cycle for all
   employees), configurable FY start month.
2. KraItem model: employee_id, period_id, description, target_type
   (numeric/percentage/boolean/rating), target_value, current_value,
   status (draft/plan_approved/in_progress/achievement_approved).
3. Two distinct manager approval gates: plan approval (locks targets
   at period start) and achievement approval (locks final
   self-reported progress at period end). Between the two, the
   employee can freely update current_value.
4. Export: per-employee target-vs-achieved (PDF/xlsx), and an org-wide
   export across all employees for a given period.

Give me the Task List and Implementation Plan first. Wait for approval.

Testing requirement: pytest coverage for period creation, KRA item
creation against each target_type, the two-gate approval flow (cannot
skip plan approval to reach achievement approval; current_value edits
rejected after achievement approval locks it), per-employee export, and
org-wide export. Run the suite via terminal, paste real output into the
Walkthrough.
```

---

## After every phase, regardless of which one

1. Read the Task List + Implementation Plan like a real review — comment directly on the artifact if something's off (wrong assumption, missed a validation rule, reused the wrong pattern) and send it back before approving code generation.
2. Once code + tests exist, actually re-read the pasted pytest output in the Walkthrough — confirm the count of passed tests roughly matches what you asked for (e.g. "why did I only get 3 tests when I asked for 5 scenarios").
3. Spin up the stack yourself once (`docker compose up`) and hit two or three endpoints manually via curl/Postman/the Swagger UI — don't rely purely on the agent's own claims.
4. `git commit` with a clear message (e.g. `phase-1: docvault module`) before starting the next phase's conversation.
5. Start the next phase in a **new** conversation, not a continuation — keeps context clean and avoids the agent trying to "helpfully" touch earlier files it doesn't need to.
