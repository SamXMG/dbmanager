# DB Manager User Manual

> For DB Manager 1.5.x. Intended for developers, DBAs, and operators who manage databases day to day.

## 1. Introduction

DB Manager is a **unified multi-database management tool** (covering the high-frequency
scenarios of Navicat / DBeaver): a single web app manages **SQLite / MySQL / PostgreSQL /
SQL Server / Oracle / MongoDB / Redis**, and is compatible with OceanBase / TiDB /
KingbaseES via protocol normalization. It bundles an account system, read/write
permissions, LDAP/AD, connection-level ACL, audit logging, and encrypted transport —
suitable for individuals, internal teams, and private enterprise deployments.

## 2. Getting started

### 2.1 Launch

```bash
python -m pip install -r requirements.txt
python app.py            # default http://127.0.0.1:8770, opens browser automatically
```

On Windows you can also double-click `setup_new_pc.bat` (installs dependencies and starts).

### 2.2 First login (important)

- On first launch a default admin `admin` is created (password `admin123`; override with
  the `DBM_DEFAULT_PWD` environment variable).
- **The system forces a password change on first login**; business features are blocked
  until you do.
- After logging in, immediately create regular accounts (read-only / read-write roles) in
  "Account Management", and mark production connections as "force read-only".

### 2.3 Creating a connection

1. Click "New Connection", choose a database type, and fill in host / port / account / password.
2. SSH tunnel (jump host) and cloud-vendor connection templates are supported.
3. Passwords are encrypted in transit via RSA-OAEP and at rest via AES-GCM (DPAPI-bound on Windows).
4. After saving, the connection appears as a card under "My Connections" on the left;
   double-click to expand the database / table object tree.

## 3. Core features

### 3.1 Data browsing (DataGrid)

- Paginated grid: sort (click column header), filter (column header ▾ panel), row selection, cell editing.
- Large-table optimization: virtual scrolling above 300 rows, streaming "load all" (cap 50,000 rows).
- Excel bulk paste insert: copy a table and paste directly into the grid to insert in bulk.
- Column-width drag and per-table memory of sort / filter / page size across sessions.
- Type-aware coloring: numbers right-aligned, dates / booleans colored, NULL shown italic-gray.

### 3.2 SQL workbench

- CodeMirror 6 editor: keyword highlighting, table/column autocomplete, Ctrl+Enter to execute.
- Multi-statement batch execution → one result tab per statement.
- **Write mode**: a danger confirmation appears before write operations (INSERT/UPDATE/DELETE/DDL).
- History / favorites (persisted across sessions), SQL formatting (Ctrl+Shift+F), EXPLAIN visualization.
- In-result filtering (no re-query) and CSV/Excel export.

### 3.3 Object management

- Table designer: columns / indexes / foreign keys / triggers with live SQL preview.
- Stored procedures / functions / triggers: view source, save-rebuild, parameterized execute, delete.
- ER diagram, schema diff / sync, data-level sync (across tables / databases / connections).

### 3.4 Tools

- Query builder (visual SELECT), data import wizard (CSV/XLSX column mapping), test-data generator.
- Backup / restore (SQL text, BLOB/date normalized round-trip).
- Scheduled tasks: periodic backup (minute-based interval, tasks reference saved connections).
- Data dictionary export, DB user & permission view.

### 3.5 MongoDB / Redis

- MongoDB: collection browsing, JSON condition queries (`{"age": {"$gt": 30}}`, rejects
  code-execution operators like `$where`), document CRUD by `_id`.
- Redis: key browsing (string/hash/list/set/zset as tables), create / edit / TTL / delete keys.

## 4. Accounts & permissions

| Role | Can do |
|---|---|
| read (read-only) | browse data, query, export, EXPLAIN |
| write (read-write) | read + insert/update/delete, import, backup/restore, DDL |
| admin | write + account management, connection visibility / read-only marking, gateway token, shutdown |

- Login rate limiting: the same IP + account locked for 5 minutes after 5 consecutive failures.
- Production protection: a connection can be marked `read_only` (write ops return 403).
- Connection visibility: `visible_to` controls who can see / use a connection (configurable by admin).
- LDAP/AD: after setting `DBM_LDAP_URL` / `DBM_LDAP_BASE`, domain accounts can log in directly
  (role follows local config).

### Fine-grained permissions (per database / table read-write)

An admin can configure **connection (database)-level** permissions for each user via
"Account Management → user row → Permissions":

- Each connection can independently enable / disable **read** and **write**.
- Table scope is one of three: **all tables** / **only specified tables (allowlist)** /
  **forbidden specified tables (denylist)**, with one-click pull of real table names or manual entry.
- Connections without configuration are **invisible and inaccessible** to that user; admin is unrestricted.
- **Bulk configuration** is supported: select multiple users in Account Management → "Bulk set permissions".
- Permissions take **effect immediately** (the next request from a logged-in user is intercepted server-side).
- Allow/deny lists also apply to the object tree (only permitted tables show) and the SQL console
  (crossing table-name boundaries is rejected).

> Note: permission config only affects saved connections matched by connection name;
> manually entered temporary connections (non-saved) are not covered. For a user with
> configured permissions, the accessible connection set = authorized connections (the original
> `visible_to` still applies; the two are unioned).

### Online user management (real-time + kick)

The top-bar "**Online Users**" (admin only) auto-refreshes every 5 seconds, showing each
user's **username / role / login time / source IP / last active / current action / session count**
(multiple devices on one account are aggregated and counted).

- Click "**Kick**" requires a second confirmation; after confirming, **all sessions** of that
  user are disconnected immediately (unusable until re-login).
- You cannot kick yourself; kick and permission changes are both audited.

### Self-registration & approval (LAN team scenario)

This tool is positioned as a one-time LAN deployment: the admin deploys once, team members
need no client, just a browser.

1. A member clicks "Register" on the login page and submits a username and password.
2. The registered account is in a **pending approval** state and **cannot log in** (login
   prompts "account pending admin approval").
3. The admin logs in and clicks "**Account Management**": approve (choose read-only / read-write
   role) or reject the pending account.
4. After approval the member can log in; a rejected account cannot log in.
5. The admin can also directly "Create User" in Account Management (no approval needed), or
   adjust roles / delete existing accounts.

> Self-registration is on by default; for public / compliance scenarios disable it with
> `DBM_ALLOW_REGISTER=0` (admin-created accounts only).

## 5. Audit & logs

- Key operations (login / CRUD / SQL writes / restore / import / tasks / password change) are
  written to `logs/audit.log` in the format `time|IP|action|detail|user`, rotated at 5 MB.
- Runtime log `logs/dbmanager.log` (5 MB × 3 rotations) includes request logs
  `method path status duration user=`.
- The audit log cannot be disabled from the frontend, suitable for compliance scenarios.

## 6. FAQ

**Q: Forgot the admin password?**
Stop the service, then reset the admin in the database (`dbmanager.db` — use a sqlite tool
or delete the user record and restart to recreate the default account; remove the `is_default`
flag to skip the forced password change). Back up the db file first.

**Q: After login it says "please change the default password first" but the change fails?**
The change-password API requires the correct old password and a new password of at least 6
characters. If you logged in with an LDAP account, the local password-change path applies —
contact your admin.

**Q: How to access over LAN / public network?**
Explicitly set `DBM_HOST=0.0.0.0` to listen on a non-loopback address. Public deployment
must enable HTTPS (`DBM_SSL=1`) together with a gateway token; see the Deployment Guide.

**Q: Why can't some databases connect?**
- SQL Server needs the ODBC Driver 17/18 installed locally (Windows desktop only).
- Oracle uses python-oracledb thin mode, no client install needed.
- Redis 5 and below auto-use the RESP2 protocol, no extra config needed.

## 7. Version & support

- Version is shown at `/api/health` or the top bar; changelog is in `CHANGELOG.md`.
- This software is Apache-2.0 open source; usage and distribution terms are in `LICENSE`
  at the repository root.
