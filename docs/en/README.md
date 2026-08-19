# DB Manager Documentation

> A self-hosted, web-based multi-database admin tool (targeting the high-frequency
> scenarios of Navicat / DBeaver). Apache-2.0 licensed.
> One Python process manages **SQLite / MySQL / PostgreSQL / SQL Server / Oracle /
> MongoDB / Redis**, plus OceanBase / TiDB / KingbaseES via protocol compatibility.

## What is this

DB Manager is a self-hosted, browser-based multi-database management tool. The browser
is the only client — it ships with an account system, read/write roles, LDAP/AD,
connection-level ACL, audit logging, and encrypted transport. Suitable for individuals,
internal teams, and private on-prem deployments.

- **Multi-database**: 10 database types under one UI, with dialect-aware metadata / DDL / EXPLAIN / import-export
- **Data browsing**: paginated grid, sort & filter, cell editing, Excel bulk paste, CSV/XLSX import-export
- **SQL workbench**: CodeMirror 6 editor, multiple result tabs, history & favorites, EXPLAIN visualization, write-mode danger confirmation
- **Object management**: table designer, stored procedures / functions / triggers, ER diagram, schema diff & sync
- **Tools**: query builder, test-data generator, backup & restore, scheduled tasks, data dictionary
- **Security**: AES-GCM at rest + Windows DPAPI + RSA-OAEP in transit; PBKDF2 account hashing; read/write/admin roles;
  login rate limiting (5 failures → 5-minute lock); LDAP/AD; connection ACL; production read-only enforcement; audit log

## Quick start

```bash
python -m pip install -r requirements.txt
python app.py            # default http://127.0.0.1:8770, opens browser automatically
```

> On first launch a default admin `admin` is created, but the **initial password is no longer the fixed `admin123`**: when `DBM_DEFAULT_PWD` is unset the system generates a **16-char random password** (printed only to the startup log `logs/dbmanager.log`, search "初始口令"); when set, it uses that value. **The first login forces a password change.** For LAN / public deployments, get the initial password, change it, and enable HTTPS first. See the Deployment Guide and User Manual §2.2.

## Documentation

- [User Manual](guide) — daily use: connections, data browsing, SQL workbench, permissions, audit
- [API Reference](api) — HTTP API endpoints and examples
- [Deployment Guide](deployment) — local / LAN / Docker / public deployments and hardening
- [Security Model](security) — threat model, encryption, vulnerability reporting
- [Support & Services](support) · [Enterprise Roadmap](enterprise) · [Contributing](contributing)

## License

Apache-2.0. Free to use, modify, and redistribute (including commercially). See `LICENSE`
at the repository root.
