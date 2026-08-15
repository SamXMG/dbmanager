# DB Manager

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/SamXMG/dbmanager/actions/workflows/ci.yml/badge.svg)](https://github.com/SamXMG/dbmanager/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/Docs-Site-blue)](https://samxmg.github.io/dbmanager/en/)

**English** · [简体中文](README.md) · [Documentation](https://samxmg.github.io/dbmanager/en/)

A self-hosted, web-based multi-database admin tool (SQLite / MySQL / PostgreSQL /
SQL Server / Oracle / MongoDB / Redis, plus OceanBase / TiDB / KingbaseES via
protocol compatibility). One Python process, browser UI, security-first defaults:
accounts & RBAC, LDAP/AD, connection ACL, audit log, encrypted storage.

<!-- Replace with a real screenshot before release: a shot of the main UI (object tree + data grid), placed at docs/screenshot.png -->

## Features

- **Multi-database**: 10 database types under one UI; dialect-aware metadata / DDL / EXPLAIN / import-export
- **Data browsing**: paginated grid (sort / filter / select-all / cell edit / right-click menu / remembered column widths), virtual scrolling for large tables,
  streaming "load all", bulk Excel paste-insert, CSV/XLSX import-export
- **SQL workbench**: CodeMirror 6 editor (keyword highlighting / table & column autocomplete), multiple result tabs,
  history / favorites, formatting, EXPLAIN, write-mode (transaction wrapping + danger confirmation)
- **Object management**: table designer (columns / indexes / foreign keys / triggers / SQL preview), stored procedure / function / trigger editors,
  ER diagram, schema diff & sync, data-level sync
- **Tools**: query builder, test-data generator, backup & restore, scheduled tasks (timed backup), data dictionary export,
  DB user & privilege view
- **Security**: AES-GCM at rest + Windows DPAPI machine binding + RSA-OAEP transport encryption;
  PBKDF2-SHA256 (120k rounds) account hashing; roles read / write / admin; login rate limiting (5 fails = 5-min lock);
  LDAP/AD integration; connection-visibility ACL; production databases forced read-only; audit log (action / user / IP)
- **Permissions & online management**: admins can configure per-user read/write permissions and table-level allow/deny lists per connection (bulk supported);
  an online-users panel shows login time / IP / current action / session count in real time, with one-click force-logout (with confirmation)
- **Server config (admin)**: the top-bar "Server Config" reads/writes `dbmanager.conf` directly (listen address / port / HTTPS / registration / LDAP, etc.),
  masks sensitive fields, and applies on restart — no manual file editing needed
- **System query**: run read-only SQL against the built-in SQLite (admin): system users / permissions / connections / audit log / scheduled tasks, directly queryable
- **Deployment**: one-command start, IPv4/IPv6 dual stack, optional HTTPS (self-signed cert), Docker image,
  Windows one-click install script

## Quick Start

```bash
# 1. Install dependencies (Python 3.10+)
python -m pip install -r requirements.txt
# Reproducible deploy (pinned exact versions incl. transitive deps):
python -m pip install -r requirements.lock

# 2. Start (default http://127.0.0.1:8770, auto-opens browser)
python app.py

# Or double-click scripts/setup_new_pc.bat (installs deps and starts)
```

### LAN access (let other machines connect)

By default it listens on localhost only (a safety design). To open it to the LAN:

```bash
# 1 Change config: edit dbmanager.conf, set host under [server] to 0.0.0.0
# 2 Start: python app.py (on Windows you can also double-click scripts/start_lan.bat)
```

Two more steps:
1. **Allow port 8770 through the firewall** (run once, as admin in PowerShell or CMD):
   `netsh advfirewall firewall add rule name="DB Manager 8770" dir=in action=allow protocol=TCP localport=8770`
2. On other machines, open `http://<this-machine-LAN-IP>:8770` (find your IP with `ipconfig`)

> Warning: once the LAN is open, anyone on the same subnet can reach it. Change the default password right after logging in.
> For production, strongly enable `ssl=1` (HTTPS, see config table below).

> **Security warning**: on first launch `ensure_default()` **automatically creates** the default admin `admin / admin123` (admin role, stored in `dbmanager.db`) — i.e. a default deployment is "auth on + public weak password". LAN/public deployments **must change the default password immediately after login**, otherwise anyone on the intranet can log in and take over (and, via the account-management API, escalate further). Override the first-boot password with the `default_pwd` config (or env `DBM_DEFAULT_PWD`) — only takes effect on first DB creation. Single-machine no-auth mode only applies when the DB has no users AND `auth_enabled=1` (`DBM_AUTH=1`) is not set.

## Docker Deployment

```bash
docker build -t dbmanager .
docker run -p 8770:8770 -v dbmanager_data:/app/data dbmanager
```

## Configuration (dbmanager.conf file)

Daily config lives at the project root **`dbmanager.conf`** (UTF-8 INI; template: `dbmanager.conf.example`; restart to apply).

> Precedence: **environment variable > config file > built-in default**. Env vars are reserved for CI/Docker/temporary overrides;
> daily use needs none. Leave sensitive fields (gateway token / default password / LDAP password) blank so the system manages them.

| Key (`[server]`) | Purpose | Default |
|------|------|------|
| `host` | Listen address: `127.0.0.1` = localhost only (safe default); **`0.0.0.0` = open to LAN/public** | `127.0.0.1` |
| `port` | Listen port | `8770` |
| `db_file` | Program data file location (e.g. data disk / shared dir) | `data/dbmanager.db` (data/ dir) |
| `dev` | `1` = dev mode (skip login, verbose errors) | off |
| `log` | `1` = console one line per request (debug) | off |
| `no_open` / `no_kill` | Don't auto-open browser / don't auto-take port | off |
| `ssl` / `ssl_cert` / `ssl_key` | `ssl=1` enables HTTPS (self-signed auto-generated); or supply your own cert | off |
| `gateway_token` | Public gateway token (blank = auto-generated and saved to `.dbm_gateway`) | auto |
| `default_conn` | Default connection (JSON string, skip manual connect) | none |

| Key (`[auth]`) | Purpose | Default |
|------|------|------|
| `default_pwd` | First-time default admin password (only on first create; plaintext on disk, leave blank) | `admin123` |
| `allow_register` | `0` = disable self-registration (default on: members register then await admin approval) | on |
| `auth_enabled` | `1` = force account system (even with no users in DB) | off |
| `ldap_url` / `ldap_base` | Enable LDAP/AD auth (optional dep ldap3) | off |
| `ldap_binddn` / `ldap_bindpw` | Optional bind query account | none |
| `ldap_attr` | LDAP login attribute | `sAMAccountName` |

## Project Structure

```
app.py          Entry point (server / SSL / startup flow)
handler.py      HTTP layer: all API routes, session/gateway auth, audit, request log
ops.py          Data-access layer: metadata / CRUD / SQL console / import-export / sync / EXPLAIN
dbcore.py       Engine manager (URL build / cache / timeout / connection test)
auth.py         Account system (login / RBAC / LDAP / rate limiting)
crypto.py       Password crypto (AES-GCM at rest / RSA in transit / DPAPI)
store.py        Connection-config persistence
config.py       Config & shared state (reads dbmanager.conf; precedence env > config > default)
task_sched.py   Scheduled tasks (timed backup; tasks stored in SQLite)
logging_conf.py Structured logging (console + logs/dbmanager.log rotation)
frontend/       Vue3 frontend (Vite + TS + Pinia + CodeMirror 6; single entry; build output frontend/dist)
docs/           Design docs / migration gap list
tests/          Unit tests + e2e scripts
logs/           Audit log (audit.log) + runtime log (dbmanager.log)
```

## Development

```bash
# Backend tests
python tests/smoke_test.py        # smoke
python tests/test_ops.py          # ops-layer unit tests
python tests/test_auth_ldap.py    # auth/LDAP unit tests
python tests/test_task_sched.py   # scheduler unit tests
# End-to-end (start the server first): tests/e2e_*.py

# Frontend (Vue3, single entry)
cd frontend && npm install
npm run build                      # output frontend/dist, served at / and /v2
npx tsc --noEmit                   # type check
```

## Data Storage

- **Program data**: `dbmanager.db` (SQLite, `data/dbmanager.db`) — normalized tables: user accounts / roles / approval status (`users`),
  fine-grained permissions (`user_perms` / `user_perm_tables`), saved connection configs (`connections`, passwords encrypted),
  audit log (`audit_log`), scheduled tasks (`tasks`). Legacy `users.json` / `connections.json` / `tasks.json`
  are auto-migrated into the DB on first launch; originals are renamed `.bak` and kept (safe to delete once verified).
- **Custom location**: `DBM_DB_FILE` can point the DB file anywhere (e.g. data disk / shared dir)
- **System query**: admins can run read-only SELECT against the built-in SQLite from the top-bar "System Query"
  (system users / permissions / connections / audit / tasks); `/api/audit` exposes structured audit queries
- Sessions (online logins / connections) live in memory and clear on restart

## Logs

- **Runtime log**: `logs/dbmanager.log` (5MB x 3 rotation), with startup info and request logs
  (`method path status duration user=`)
- **Audit log**: `logs/audit.log`, key actions (login / create-delete-update / SQL writes / restore / import / tasks, etc.)
  appended as `time|IP|action|detail|user`, rotated past 5MB

## Security

- Default account `admin/admin123` is auto-created on first launch — **change the password in production immediately**
  (frontend "Change Password" or `POST /api/password`)
- Connection passwords are AES-GCM encrypted at rest (bound to the current Windows user via DPAPI), transported via RSA-OAEP
- Production databases can be flagged `read_only` (forced read-only; writes return 403)
- Connection visibility `visible_to` controls who can see / use a connection

## Notes

- LICENSE: **Apache License 2.0** — free to use / modify / redistribute (including commercial). See `LICENSE` at the root.
- The frontend is now a single Vue3 entry (`frontend/dist` build output; both `/` and `/v2` serve it).
  The legacy native frontend (`index.html` + `js/` + `css/`) has been removed; if the frontend is not built, the server returns 503 (`cd frontend && npm run build`).

## Contributing

Issues and Pull Requests are welcome. Dev/test conventions are in `docs/` and `CONTRIBUTING.md`;
security vulnerability reporting channel is in `SECURITY.md`.

## Support (optional)

The software itself is free — all features work without payment. To support its continued development:

- Sponsor: [GitHub Sponsors](https://github.com/sponsors/SamXMG) (Sponsor button on the repo page)
- Enterprise support subscription: prioritized response, deployment assurance, security advisories — see [`docs/SUPPORT.md`](docs/SUPPORT.md)
- Custom development: per-feature quotes, generic capabilities fed back to the open-source edition — see [`docs/SUPPORT.md`](docs/SUPPORT.md)

Sponsoring or not does not affect any rights. Apache-2.0 permits free use, modification, and redistribution (including commercial).
