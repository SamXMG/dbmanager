# Security

DB Manager targets **internal / team database management**, with security designed in
throughout. When you find a security issue, **report it privately first — do not disclose
publicly** (a public PoC puts un-upgraded users at risk).

## Reporting vulnerabilities

- Preferred: GitHub's private channel — create a **Security Advisory** under the repository's
  `Security` tab (or contact the maintainer via private message / email, see the repo homepage).
- Please include in your report: affected version, vulnerability type (injection / privilege
  escalation / DoS / credential leak, etc.), reproduction steps or a minimal PoC, and the
  affected endpoint path.
- Typical handling: confirm, then **fix and release a patch within 14 days**, then disclose
  in CHANGELOG (without PoC details).

## Security model overview (for reviewers)

| Layer | Mechanism |
|---|---|
| Auth | Account system (PBKDF2-SHA256, 120k rounds), three-tier RBAC (read/write/admin), login rate limiting (5 failures → 5-min lock), optional LDAP/AD |
| Forced first password change | Before the default account changes its password, all business APIs return 403 globally (`must_change_pwd`) |
| Encryption | Connection passwords AES-GCM at rest (DPAPI-bound on Windows) + RSA-OAEP(SHA-256) in transit; key files 0600 |
| Injection protection | Data-layer identifier allowlist + parameterization + dialect escaping; per-statement read-only gate on SQL; `SELECT INTO` blocked; Mongo rejects code-execution operators like `$where` |
| Query limits | SELECT without LIMIT auto-appends a cap (default 500 / max 5000); request body capped at 100 MB; login and session rate limiting |
| Transport | Defaults to binding 127.0.0.1; optional HTTPS (self-signed or your own cert, Cookie Secure linked); public gateway token (internal IPs exempt) |
| Headers / audit | CSP, X-Frame-Options DENY, nosniff; key-operation audit log (time\|IP\|action\|detail\|user, rotated) |
| DoS surface | Request body 413 cap, query LIMIT fallback, lazy session cleanup, connection-pool cap |

## Accepted boundaries (trust model)

- **Internal trust model**: RFC1918 / loopback / link-local clients are exempt from the gateway
  token (the gateway only constrains public access).
- Production read-only protection relies on the connection config flag `read_only` (write ops
  return 403); administrators are responsible for marking it correctly.
- The audit log serves compliance retention; if a local root-level attacker directly deletes or
  tampers with files, that is out of scope for this software.

## Pre-release checklist (maintainers)

Before an open-source release / tagging: confirm `users.json` / `connections.json` / `.dbm_*` /
`logs/` / `localdb/` are not committed (already gitignored); never write real credentials in
commit messages or code comments; tagging `v*` triggers the Release pipeline for full verification.
