# Contributing

Thanks for your interest in DB Manager! Issues, bug fixes, and features are all welcome.

## Quick start

```bash
# Backend (Python 3.10+)
python -m pip install -r requirements.txt
python app.py                          # http://127.0.0.1:8770

# Frontend (Vue3 + TS, default entry / serves dist)
cd frontend
npm install
npm run dev                            # Vite dev server (5173, proxies /api to 8770)
npm run test                           # unit tests
npm run typecheck                      # type check
npm run build                          # build dist (served by backend automatically)
```

## Testing conventions (important)

- **Backend**: three unit-test suites + full HTTP smoke + security e2e under `tests/`; run
  them all locally after changes:
  ```bash
  python tests/smoke_test.py
  python tests/test_ops.py
  python tests/test_task_sched.py
  python tests/e2e_http_smoke.py
  ```
- **Note**: if the local `users.json` admin still uses the default password, set
  `export DBM_DEFAULT_PWD=<random>` before running the security e2e (otherwise the forced
  password change returns 403 and blocks the test requests).
- **Frontend**: `npm run test` (vitest; core logic: injection protection / formatting).
- CI (`.github/workflows/ci.yml`) runs everything on the PR: Py 3.10–3.12 × Ubuntu/Windows,
  static checks, unit tests, security e2e, dependency vulnerability scan, front-end
  test/type/build. **The PR must be all green.**

## Commit conventions

- Follow semantic versioning; commit messages in Chinese, one-line summary + key details
  (refer to historical commit style).
- For security fixes, mark the affected endpoints and verification method in the message.

## Architecture overview (read before changing code)

```
app.py           entry (server/SSL/startup flow)
handler.py       HTTP layer: auth gateway (_host/_gateway/_auth/_must_change/_require_write), static, audit
routes/          domain routes (connection/query/schema/files/routines/monitor/admin)
services/        data-operations layer (core/metadata/export/nosql/routines/tools/ddl/sync/backup/sql/data)
metrics.py       process metrics (Prometheus, zero-dependency, avoids routes reverse-importing handler)
auth.py          account system (PBKDF2/RBAC/LDAP/rate-limit/forced-password-change)
crypto.py        password crypto (AES-GCM at rest / RSA in transit / DPAPI)
store.py         connection config persistence (encrypted at rest)
frontend/src/    Vue3 + TS + Pinia + CodeMirror 6 (stores/ holds state and core logic, all unit-tested)
```

### Rules for adding route modules (lessons learned)

1. A new route module **must implement both `handle_get` and `handle_post`** (the dispatcher
   iterates modules; missing one causes AttributeError → 500), and register it in
   `routes/__init__.py`'s `ROUTE_MODS`.
2. Do not `import handler` inside routes (circular import) — call shared capabilities via
   `handler._xxx()` wrapper methods; put independent logic like metrics in `metrics.py`.
3. If a new API is a write operation: add its path to `handler.WRITE_PATHS` (role + read-only
   connection double gate).
4. If a read-only endpoint needs to be login-exempt (liveness / metrics), add it to the
   `_auth_blocked` / `_must_change_blocked` exemption list with a reason.

## Issue templates

- **Bug**: version, runtime environment (OS/Python/database type), reproduction steps,
  expected vs actual, log snippets (sanitized).
- **Feature suggestion**: use case, expected behavior, acceptable minimal implementation.
