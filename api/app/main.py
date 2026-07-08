"""
Kubera FastAPI application entry point.
"""
from fastapi import FastAPI

from app.routers import auth, internal, docvault, auditor_auth, auditease, auditor_auditease, secretarial

app = FastAPI(
    title="Kubera API",
    description=(
        "Centralized management & compliance platform for Indian private limited companies."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(internal.router)
app.include_router(docvault.router)
app.include_router(auditor_auth.router)
app.include_router(auditease.router)
app.include_router(auditor_auditease.router)
app.include_router(secretarial.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
