# DB Manager API Reference (overview)

> Version: 1.5.x. Base URL: `http(s)://<host>:<port>`.
> Auth: after a successful login the server issues a session (HttpOnly Cookie `dbm_user`
> or header `X-User-Token`); connection context is passed via `X-Session` (named direct
> connection session) or `X-Conn` (Base64 connection JSON, password RSA-encrypted).
> Password fields are uniformly encrypted with the `rsa:` prefix (GET `/api/pubkey` first).

## Conventions

- Success returns JSON; errors return `{"error": "..."}` (sanitized, no stack trace).
- Auth failure: `401 {"require_login": true}`; insufficient permission: `403`;
  forced password-change intercept: `403 {"must_change_pwd": true}`; request body too large: `413`.
- Write-operation paths (`/api/row`, `/api/import`, `/api/alter`, `/api/restore`, `/api/sync`,
  `/api/routines/*`, `/api/schema-sync`, `/api/connections*`, `/api/transaction/*`,
  `/api/gen-data`, `/api/transfer`) require write/admin role and are rejected for `read_only` connections.

## Monitoring & config

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Liveness: `{status, version, uptime_seconds, pid, auth_required, sessions, requests_total, errors_total, python}` (no login) |
| GET | `/api/metrics` | Prometheus text-format metrics (no login) |
| GET | `/api/config` | Global config: `{version, auth_required, auth_user, auth_role, must_change_pwd, register_enabled, saved_connections, api_base, gateway_required, default_conn}` |
| GET | `/api/pubkey` | RSA public key (PEM), for password encryption |
| GET | `/api/gateway/status` | Gateway token status |

## Auth & accounts

| Method | Path | Description |
|---|---|---|
| POST | `/api/login` | `{username, password}` → `{ok, token, user, role, must_change_pwd}`; Set-Cookie `dbm_user` |
| POST | `/api/logout` | Logout (delete session + clear cookie); returns 200 even if not logged in |
| POST | `/api/password` | Change password: `{old_password, new_password}` (new ≥ 6 chars) |
| POST | `/api/register` | Self-registration (only when `DBM_ALLOW_REGISTER=1`, defaults to read-only role) |
| GET | `/api/users` | Account list (admin) |
| POST | `/api/users` | Create/update account: `{username, role, password?}` (admin; non-admin may not grant admin role) |
| POST | `/api/users/delete` | Delete account (admin; cannot delete self) |
| GET | `/api/users/perms?username=x` | Query user connection/table permissions (admin): `{perms, connections}` |
| POST | `/api/users/perms` | Configure permissions (admin, single user / bulk): `{usernames, perms}`; empty perms = clear to unrestricted |
| GET | `/api/sessions` | Online user list (admin): username/role/login time/IP/last active/current action/session count |
| POST | `/api/sessions/kick` | Force kick (admin): `{username}`, deletes all sessions of that user; cannot kick self |
| POST | `/api/conn/tables` | Permission config helper: pull table-name list of a saved connection (admin) |
| POST | `/api/sysdb` | System query (admin): `{sql}` read-only SELECT on the built-in SQLite (allowlist validation, no writes / no multi-statement) |
| GET | `/api/audit?user=&action=&limit=&offset=` | Audit query (admin): filter by user/action, newest first |
| POST | `/api/gateway/login` | Public gateway token verification: `{token}` → Set-Cookie `dbm_gw` |
| POST | `/api/shutdown` | Shut down the service (admin only) |

## Connection management

| Method | Path | Description |
|---|---|---|
| GET | `/api/connections` | Visible connection list (filtered by role) |
| POST | `/api/connections` | Save/update connection (write permission; `visible_to`/`mode` admin only) |
| POST | `/api/connections/delete` | Delete connection |
| POST | `/api/connect` | Open a connection session: `{db_type, server, port, uid, pwd, database?}` → `{session}` |
| POST | `/api/test` | Test connection (requires write; rejects URL/path-form server, anti-SSRF) |

## Data browsing & query

| Method | Path | Description |
|---|---|---|
| GET | `/api/databases` | Database list |
| GET | `/api/tables` | Table/collection/key list (incl. Mongo collections, Redis keys) |
| GET | `/api/objects` | Object tree (db/table/views, etc.) |
| GET | `/api/columns` | Column info: `?s=&t=` |
| GET | `/api/indexes` | Index list |
| GET | `/api/relations` | Foreign-key relations |
| GET | `/api/data` | Paged data: `?s=&t=&page=&size=&sort=&where=` (where is dialect SQL; Mongo passes JSON condition) |
| POST | `/api/sql` | SQL execute: `{sql, limit?, write?, database?}` → `{results: [...]}`; SELECT without LIMIT auto-capped at 500 rows |
| POST | `/api/explain` | EXPLAIN: `{sql, database?}` |
| POST | `/api/row` | Row insert/update: `{s, t, values, transaction?, tx_id?}` (PUT/DELETE same path) |
| POST | `/api/import` | Data import (CSV/TSV/Excel paste) |
| POST | `/api/export/sql` | Query result export (CSV/XLSX) |
| POST | `/api/stats` | Column statistics (count/sum/avg) |
| POST | `/api/gen-data` | Test-data generation |
| POST | `/api/transaction/commit` / `rollback` | Transaction commit/rollback (by tx_id) |

## Schema operations

| Method | Path | Description |
|---|---|---|
| POST | `/api/alter` | Table structure change: `{action, ...}` (create/rename/drop/truncate/clear/copy/maintain/set_ttl… four dialects) |
| GET | `/api/er` | ER diagram data |
| POST | `/api/schema/diff` | Schema diff: `{src, dst, schema, table}` |
| POST | `/api/schema/sync` | Schema sync execution |
| POST | `/api/sync` | Data sync: `{target_conn, ...}` |
| POST | `/api/transfer` | Cross-database transfer |

## Backup & dictionary

| Method | Path | Description |
|---|---|---|
| GET | `/api/backup` | Backup current database (SQL text download; BLOB/date normalized) |
| POST | `/api/restore` | Restore SQL |
| GET | `/api/export/schema` | Data dictionary export |
| GET | `/api/db-users` | DB user & permission view |

## Stored procedures / scheduler

| Method | Path | Description |
|---|---|---|
| GET | `/api/routines` | Stored procedure/function/trigger list |
| GET | `/api/routine/source` | Object source |
| GET | `/api/routine/params` | Parameter list |
| POST | `/api/routine/save` / `drop` / `execute` | Save-rebuild / delete / parameterized execute |
| GET | `/api/tasks` | Scheduled task list |
| POST | `/api/tasks` | Create task: `{name, conn_name, interval_min, action}` |
| POST | `/api/tasks/delete` / `toggle` / `run` | Delete / enable-disable / run now |

## Example: login → connect → query

```bash
# 1. Login (get token, also set cookie)
TOKEN=$(curl -s -X POST $BASE/api/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"****"}' | jq -r .token)

# 2. Open a connection session (SQLite example)
SESS=$(curl -s -X POST $BASE/api/connect -H "X-User-Token: $TOKEN" \
  -d '{"db_type":"sqlite","database":"app.db"}' | jq -r .session)

# 3. Query (with X-Session context)
curl -s "$BASE/api/data?s=&t=emp&page=1&size=10" -H "X-User-Token: $TOKEN" -H "X-Session: $SESS"
```
