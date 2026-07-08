# Kubera — Centralized Compliance & Management Platform

Kubera is a centralized compliance and management platform designed for mid-to-large Indian private limited companies. It incorporates strict multi-tenant isolation, secure document archiving (`docVault`), trial balance audits (`AuditEase`), and corporate secretarial management (`SecretarialEase`).

---

## 1. Prerequisites (New Machine Setup)

Before deploying Kubera, ensure the host machine has the following installed:

- **Docker** (v20.10+)
- **Docker Compose** (v2.0+)
- **Python 3.12** (optional, useful for generating secrets locally)

---

## 2. Environment Configuration

1. Copy the example environment template to create your `.env` file:
   ```bash
   cp .env.example .env
   ```

2. **Generate Cryptographic Keys**:
   Kubera requires several high-entropy keys for security (JWT signing, envelope encryption, and internal API routing). Run the following commands to generate keys and paste them into your `.env`:

   - **JWT Secret Keys** (64-byte hex):
     Generate keys for `SECRET_KEY`, `REFRESH_SECRET_KEY`, `AUDITOR_SECRET_KEY`, and `AUDITOR_REFRESH_SECRET_KEY` using:
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(64))"
     ```

   - **Internal API Key** (`INTERNAL_API_KEY`) (32-byte hex):
     This key secures endpoints reserved for administrative scripts and internal onboarding:
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```

   - **docVault Master Key** (`VAULT_KEK`) (32-byte hex):
     This is the Key Encryption Key (KEK) used to encrypt/decrypt document-specific Data Encryption Keys (DEKs) on upload/download:
     ```bash
     python3 -c "import secrets; print(secrets.token_hex(32))"
     ```

Ensure all generated variables are saved in your `.env`.

---

## 3. Deployment

Start the service using Docker Compose:

```bash
# Build and run the containers in the background
docker compose up -d --build
```

This launches:
- `api` (FastAPI backend)
- `postgres` (Main database)
- `redis` (Task broker)
- `worker` / `beat` (Celery background tasks)
- `nginx` (Reverse proxy/routing)

---

## 4. Database Migrations

Run database migrations to initialize/upgrade the Postgres schema:

```bash
docker compose exec api alembic upgrade head
```

---

## 5. Running the Test Suite

Kubera uses a real Postgres database for testing to accurately cover `JSONB` properties and query constraints.

1. Ensure the test catalog exists on the Postgres container:
   ```bash
   docker compose exec postgres createdb -U kubera kubera_test
   ```

2. Run the test suite:
   ```bash
   docker compose exec api pytest -v
   ```

---

## 6. Accessing & Using the System

Once deployed, the FastAPI interactive Swagger docs are accessible at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Onboarding Flow (Interactive Walkthrough):

1. **Create a Company and Company Admin**:
   - Go to Swagger and find the internal onboarding endpoint: `POST /api/v1/internal/companies`.
   - Click **Try it out**.
   - Under headers, supply your generated `X-Internal-Key`.
   - Provide the requested payload (e.g. `company_name`, `cin` [21 characters limit], `admin_email`, `admin_password`).
   - Execute to initialize the company and its primary admin account.

2. **Authenticate as Admin**:
   - Go to `POST /api/v1/auth/login`.
   - Log in using your admin email and password.
   - Copy the returned `access_token`.

3. **Explore Features**:
   - Click the **Authorize** lock button in the upper-right corner of Swagger, paste your token, and click **Authorize**.
   - You can now interact with all client-facing routes:
     - **docVault** (`/api/v1/docvault/*`): Buckets, uploads, versioning, downloads.
     - **AuditEase** (`/api/v1/auditease/*`): Upload trial balances, maps ledger groups, view reports.
     - **SecretarialEase** (`/api/v1/secretarial/*`): Create meeting minutes templates and records.
