# DB Manager Deployment Guide

> Version: 1.5.x. Covers four deployment shapes — local, internal/LAN team, Docker, and
> public (HTTPS + gateway) — plus a hardening checklist. Before deploying, read `LICENSE`
> at the repository root.

## 1. Deployment shapes at a glance

| Shape | Command / key points | Security baseline |
|---|---|---|
| Local single user | `python app.py` | Already met (listens on 127.0.0.1 only) |
| Internal / team | `DBM_HOST=0.0.0.0 python app.py` | See §4 internal hardening |
| Docker | See §3 | See §4 |
| Public single instance | `DBM_HOST=0.0.0.0 DBM_SSL=1` + reverse proxy | See §5 public hardening |

## 2. Requirements

- **Python 3.10+** (3.12 recommended); Windows / Linux / macOS all supported.
- Dependencies: `pip install -r requirements.lock` (reproducible, pinned transitive versions);
  for development `pip install -r requirements.txt` is enough.
- Optional drivers as needed: pyodbc (SQL Server, Windows desktop only), ldap3 (LDAP/AD login).
- The frontend is a pure static build `frontend/dist/`, served directly by the backend — no Node runtime needed.

## 3. Docker deployment

```bash
docker build -t dbmanager .
docker run -d --name dbm \
  -p 8770:8770 \
  -e DBM_DEFAULT_PWD='replace-with-strong-password' \
  -v dbmanager_data:/app/data \
  dbmanager
```

> The Dockerfile is multi-stage (node builds the frontend + python runtime).
> The `/app/data` volume holds `dbmanager.db` (SQLite: users/permissions/connection config),
> logs, and other runtime data. Legacy `users.json` / `connections.json` are auto-migrated
> into the DB on first launch (originals renamed to `.bak`). For production, add a health
> check with `GET /api/health` via compose.

## 4. Internal / team deployment hardening

1. **Force HTTPS or narrow the listener**:
   - Local only: keep the default `127.0.0.1`.
   - Multi-machine: set `DBM_HOST=0.0.0.0`, strongly recommend `DBM_SSL=1` (auto self-signed
     cert) or supply your own (`DBM_SSL_CERT` / `DBM_SSL_KEY`).
2. **Change password on first deploy**: logging in as admin forces a password change on first
   launch; or pre-set a strong password via `DBM_DEFAULT_PWD`.
3. **Least-privilege accounts**: create and distribute read-only / read-write accounts, keep
   admin for administrators only; mark production connections "force read-only".
4. **Gateway token**: for public / hybrid network access set `DBM_GATEWAY_TOKEN` (fixed token);
   internal IPs (RFC1918 / loopback / link-local) are exempt from verification.
5. **Audit**: `logs/audit.log` (key operations) is on by default; archive per your compliance retention.

## 5. Public deployment hardening (recommended architecture)

```
client ──HTTPS──▶ Nginx/Caddy (TLS termination + rate limit)──▶ DB Manager (127.0.0.1:8770)
```

1. **Reverse proxy + TLS**: bind DB Manager to `127.0.0.1` and let Nginx terminate TLS
   (more mature cert management, ACME auto-renewal), forwarding to 8770.
2. **Rate limiting**: Nginx `limit_req` on `/api/login` and `/api/gateway/login`
   (the app already locks after 5/5min; the proxy adds defense in depth).
3. **Gateway token**: set `DBM_GATEWAY_TOKEN`; external clients must enter the token on first
   visit (cookie session 8 hours).
4. **CSP / security headers**: built-in (X-Frame-Options DENY, X-Content-Type-Options nosniff,
   basic CSP) — do not override at the proxy.
5. **Monitoring**: scrape `/api/metrics` with Prometheus and use `/api/health` for liveness.
6. **Backup**: periodically back up `dbmanager.db` (SQLite: users/permissions/connection config),
   `.dbm_key`, `.dbm_gateway`, `.dbm_cert.pem` / `.dbm_key_ssl.pem` (losing keys means stored
   passwords can no longer be decrypted).

## 6. Configuration reference (dbmanager.conf preferred)

Daily config goes in `dbmanager.conf` at the project root (INI, template
`dbmanager.conf.example`), effective after restart.
**Priority: environment variable > config file > built-in default.** The following are env
var names (one-to-one with config keys, e.g. `DBM_HOST` ↔ `[server] host`); CI/Docker use
env vars, daily deploys should edit the config file directly.

| Variable | Purpose | Default |
|---|---|---|
| `DBM_HOST` | Listen address (safe default: local only; LAN: `host=0.0.0.0`) | `127.0.0.1` |
| `DBM_PORT` | Listen port | `8770` |
| `DBM_SSL=1` | Enable HTTPS (auto self-signed cert) | off |
| `DBM_SSL_CERT` / `DBM_SSL_KEY` | Path to your own cert | — |
| `DBM_DEFAULT_PWD` | Override the admin password created on first launch (first creation only) | `admin123` |
| `DBM_AUTH=1` | Force the account system even with no users | off |
| `DBM_ALLOW_REGISTER=1` | Open self-registration (defaults to read-only role) | off |
| `DBM_LDAP_URL` / `DBM_LDAP_BASE` | Enable LDAP/AD login | off |
| `DBM_GATEWAY_TOKEN` | Fixed public gateway token | auto-generated on first launch |
| `DBM_DEFAULT_CONN` | Default connection (JSON string) | none |
| `DBM_NO_OPEN=1` / `DBM_NO_KILL=1` | Don't auto-open browser / don't take over port | off |
| `DBM_DEV=1` | Dev mode (skip login, verbose errors) | off |

## 7. Health & monitoring

- **Liveness**: `GET /api/health` → `{"status":"ok","version":"1.5.0","uptime_seconds":…}`
  (no login; usable directly as K8s liveness/readiness).
- **Metrics**: `GET /api/metrics` → Prometheus text format
  (`dbm_requests_total` / `dbm_requests_by_path` / `dbm_status_codes` /
  `dbm_errors_total` / `dbm_auth_sessions` / `dbm_uptime_seconds`).
- Both endpoints expose no business data; when exposed publicly they are still protected by the gateway token.

## 8. Upgrade

1. Back up the data directory (§5 item 6 checklist).
2. Pull the new code/image, `pip install -r requirements.lock` or rebuild the image.
3. Restart; `dbmanager.db` schema is idempotent (legacy users.json/connections.json auto-migrate if present).
4. Confirm the new version via `/api/health`; spot-check login and audit log.

## 9. Troubleshooting

- **Service won't start**: check `logs/dbmanager.log`; confirm the port isn't taken
  (`DBM_NO_KILL=1` disables auto-taking-over the old instance).
- **Can't log in**: confirm credentials (data in `dbmanager.db`); the rate-limit lock clears after 5 minutes.
- **SQL Server won't connect**: install ODBC Driver 17/18; on Linux `msodbcsql18` (already in Dockerfile).
- **LAN access denied**: `DBM_HOST=0.0.0.0` + firewall allow 8770.
- **Cert warning**: self-signed certs trigger a browser warning; import as trusted or use a
  reverse proxy with a real cert.
