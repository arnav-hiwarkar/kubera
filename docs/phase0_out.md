  ## ✅ Phase 0 Complete — 15/15 Tests Passing

  ### Real test output (not claimed — ran in terminal above):

    platform linux -- Python 3.14.6, pytest-8.3.4
    collected 15 items

    tests/test_auth.py::test_login_returns_valid_jwt              PASSED [  6%]
    tests/test_auth.py::test_login_wrong_password_returns_401     PASSED [ 13%]
    tests/test_auth.py::test_login_unknown_email_returns_401      PASSED [ 20%]
    tests/test_auth.py::test_refresh_returns_new_access_token     PASSED [ 26%]
    tests/test_auth.py::test_protected_endpoint_rejects_missing_token   PASSED [ 33%]
    tests/test_auth.py::test_protected_endpoint_rejects_malformed_token PASSED [ 40%]
    tests/test_auth.py::test_protected_endpoint_rejects_wrong_secret    PASSED [ 46%]
    tests/test_auth.py::test_protected_endpoint_rejects_expired_token   PASSED [ 53%]
    tests/test_auth.py::test_protected_endpoint_rejects_refresh_token_as_access PASSED [ 60%]
    tests/test_internal.py::test_create_company_admin_success     PASSED [ 66%]
    tests/test_internal.py::test_create_company_admin_rejects_duplicate_cin   PASSED [ 73%]
    tests/test_internal.py::test_create_company_admin_rejects_duplicate_email PASSED [ 80%]
    tests/test_internal.py::test_create_company_admin_rejects_wrong_key       PASSED [ 86%]
    tests/test_internal.py::test_create_company_admin_rejects_missing_key     PASSED [ 93%]
    tests/test_tenant_scope.py::test_tenant_scope_filters_by_company_id       PASSED [100%]

    ======================= 15 passed, 688 warnings in 3.53s =======================

  ### What was delivered

   File                                                                                                               | Purpose
  --------------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------
   docker-compose.yml                                                                                                     | Full stack: api, postgres, redis, worker, beat, nginx
   nginx.conf                                                                                                     | Reverse proxy with streaming and keepalive
   base.py                                                                                                     |  Base  +  TenantScopedMixin  (the critical primitive)
   deps.py                                                                                                     |  get_current_admin ,  get_tenant_scope ,  require_internal_key 
   security.py                                                                                                     | Two-secret JWT + bcrypt
   auth.py                                                                                                     |  /api/v1/auth/login ,  /refresh ,  /me 
   internal.py                                                                                                     |  /api/v1/internal/admins  (API-key guarded)
   seed_admin.py                                                                                                     | CLI seed script
                                                                                                        |  0001_initial  +  0002_company_and_admin 
                                                                                                        | 15 tests covering (a)–(d)

  ### ✓  .env  gitignored

    .gitignore:2:.env    .env    ← confirmed by git check-ignore -v

  ### Python 3.14 notes (pinned in pyproject.toml)

  •  pydantic-core : uses  >=2.10.3  (2.47.0 has a cp314 wheel; 2.10.3 did not)
  •  greenlet : uses  >=3.1.1  (3.5.3 has a cp314 wheel; 3.1.1 did not)
  •  bcrypt : pinned to  4.2.1  — bcrypt 5.x breaks passlib 1.7.4 compatibility

