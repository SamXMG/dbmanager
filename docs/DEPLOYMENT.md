# DB Manager 部署指南

> 适用版本：1.4.x。覆盖本机、内网/团队、Docker、公网（HTTPS + 网关）四种部署形态，
> 以及安全加固清单。部署前请先阅读仓库根目录 `LICENSE`（商业使用授权）。

## 1. 部署形态速查

| 形态 | 命令/要点 | 安全基线 |
|---|---|---|
| 本机单用户 | `python app.py` | 默认已满足（仅监听 127.0.0.1） |
| 内网/团队 | `DBM_HOST=0.0.0.0 python app.py` | 见 §4 内网加固 |
| Docker | 见 §3 | 见 §4 |
| 公网单实例 | `DBM_HOST=0.0.0.0 DBM_SSL=1` + 反代 | 见 §5 公网加固 |

## 2. 环境要求

- **Python 3.10+**（推荐 3.12）；Windows / Linux / macOS 均可；
- 依赖：`pip install -r requirements.lock`（可复现部署，含传递依赖精确版本）；
  开发用 `pip install -r requirements.txt` 即可；
- 可选驱动按需安装：pyodbc（SQL Server，仅 Windows 桌面版）、ldap3（LDAP/AD 登录）；
- 前端为纯静态构建产物 `frontend/dist/`，由后端直接服务，无需 Node 运行时。

## 3. Docker 部署

```bash
docker build -t dbmanager .
docker run -d --name dbm \
  -p 8770:8770 \
  -e DBM_DEFAULT_PWD='替换为强密码' \
  -v dbmanager_data:/app/data \
  dbmanager
```

> 说明：Dockerfile 为多阶段构建（node 构建前端 + python 运行时）。
> `/app/data` 挂载卷保存 users.json / connections.json / 日志等运行时数据。
> 生产建议配合 compose 增加健康检查：`GET /api/health`。

## 4. 内网 / 团队部署加固

1. **强制 HTTPS 或收敛监听**：
   - 仅本机使用：保持默认 `127.0.0.1`；
   - 多机访问：设 `DBM_HOST=0.0.0.0`，并强烈建议 `DBM_SSL=1`（自动生成自签名证书）
     或提供自有证书（`DBM_SSL_CERT`/`DBM_SSL_KEY`）。
2. **首次部署改密**：启动后登录 admin 会强制改密；或提前 `DBM_DEFAULT_PWD` 设置强密码。
3. **账号最小权限**：创建只读/读写账号分发，admin 仅保留管理员；生产库连接勾选「强制只读」。
4. **网关令牌**：公网/混合网络访问时设置 `DBM_GATEWAY_TOKEN`（固定令牌）；
   内网 IP（RFC1918/回环/链路本地）客户端免验证。
5. **审计**：默认已开启 `logs/audit.log`（关键操作），按合规要求保留周期自行归档。

## 5. 公网部署加固（推荐架构）

```
客户端 ──HTTPS──▶ Nginx/Caddy（TLS 终结 + 限流）──▶ DB Manager (127.0.0.1:8770)
```

1. **反向代理 + TLS**：DB Manager 绑定 `127.0.0.1`，由 Nginx 终结 TLS（证书管理更成熟，
   支持 ACME 自动续期），并转发到 8770；
2. **速率限制**：Nginx `limit_req` 对 `/api/login`、`/api/gateway/login` 限流
   （应用内已有 5 次/5 分钟锁定，反代再加一层纵深）；
3. **网关令牌**：设 `DBM_GATEWAY_TOKEN`，外部客户端首次访问需输入令牌（Cookie 会话 8 小时）；
4. **CSP/安全头**：已内置（X-Frame-Options DENY、X-Content-Type-Options nosniff、
   基础 CSP），反代不要覆盖；
5. **监控**：接入 Prometheus 抓取 `/api/metrics`，用 `/api/health` 做探活；
6. **备份**：定时备份 `users.json`、`connections.json`、`.dbm_key`、`.dbm_gateway`、
   `.dbm_cert.pem`/`.dbm_key_ssl.pem`（丢失密钥将无法解密已存密码）。

## 6. 环境变量参考

| 变量 | 作用 | 默认 |
|---|---|---|
| `DBM_HOST` | 监听地址（安全默认仅本机） | `127.0.0.1` |
| `DBM_PORT` | 监听端口 | `8770` |
| `DBM_SSL=1` | 启用 HTTPS（自动生成自签名证书） | 关 |
| `DBM_SSL_CERT` / `DBM_SSL_KEY` | 自有证书路径 | — |
| `DBM_DEFAULT_PWD` | 覆盖首次创建 admin 的密码（仅首建生效） | `admin123` |
| `DBM_AUTH=1` | 无 users.json 也强制启用账号体系 | 关 |
| `DBM_ALLOW_REGISTER=1` | 开放自助注册（默认只读角色） | 关 |
| `DBM_LDAP_URL` / `DBM_LDAP_BASE` | 启用 LDAP/AD 登录 | 关 |
| `DBM_GATEWAY_TOKEN` | 固定公网网关令牌 | 首次启动自动生成 |
| `DBM_DEFAULT_CONN` | 默认连接（JSON 字符串） | 无 |
| `DBM_NO_OPEN=1` / `DBM_NO_KILL=1` | 不自动开浏览器 / 不自动接管端口 | 关 |
| `DBM_DEV=1` | 开发模式（跳过登录、错误透传） | 关 |

## 7. 健康检查与监控

- **探活**：`GET /api/health` → `{"status":"ok","version":"1.4.0","uptime_seconds":…}`
  （无需登录，K8s liveness/readiness 可直接使用）；
- **指标**：`GET /api/metrics` → Prometheus 文本格式
  （`dbm_requests_total` / `dbm_requests_by_path` / `dbm_status_codes` /
  `dbm_errors_total` / `dbm_auth_sessions` / `dbm_uptime_seconds`）；
- 两个端点均不含业务数据，公网暴露时仍受网关令牌保护。

## 8. 升级

1. 备份数据目录（§5 第 6 条清单）；
2. 拉取新版本代码/镜像，`pip install -r requirements.lock` 或重建镜像；
3. 重启服务；`users.json` 自动幂等迁移（admin 角色升级等）；
4. 用 `/api/health` 确认新版本号，抽查登录与审计日志。

## 9. 故障排查

- **服务起不来**：查看 `logs/dbmanager.log`；确认端口未被占用（`DBM_NO_KILL=1`
  可禁止自动接管旧实例）；
- **登录不了**：确认 `users.json` 存在且密码正确；限流锁 5 分钟自动解除；
- **SQL Server 连不上**：安装 ODBC Driver 17/18；Linux 需 `msodbcsql18`（Dockerfile 已含）；
- **局域网访问被拒**：`DBM_HOST=0.0.0.0` + 防火墙放行 8770；
- **证书告警**：自签名证书浏览器会提示，可导入信任或改用反代 + 正式证书。
