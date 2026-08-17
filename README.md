# DB Manager

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/SamXMG/dbmanager/actions/workflows/ci.yml/badge.svg)](https://github.com/SamXMG/dbmanager/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/Docs-文档站-blue)](https://samxmg.github.io/dbmanager/)

[English](README.en.md) · **简体中文** · [文档站](https://samxmg.github.io/dbmanager/)

多数据库管理工具（对标 Navicat / DBeaver 高频场景）：一个 Python 进程同时管理
SQLite / MySQL / PostgreSQL / SQL Server / Oracle / MongoDB / Redis，
另兼容 OceanBase / TiDB / KingbaseES（协议归一化）。内置账号体系、读写权限、LDAP/AD、
连接级 ACL、审计日志与传输加密，适合内网团队与个人使用。

A self-hosted, web-based multi-database admin tool (SQLite / MySQL / PostgreSQL /
SQL Server / Oracle / MongoDB / Redis, plus OceanBase / TiDB / KingbaseES via
protocol compatibility). One Python process, browser UI, security-first defaults:
accounts & RBAC, LDAP/AD, connection ACL, audit log, encrypted storage.

<!-- 发布前替换为真实截图: 建议截一张主界面(对象树+数据网格)并放到 docs/screenshot.png -->

## 功能特性

- **多数据库**：10 种数据库类型统一界面；方言化元数据/DDL/EXPLAIN/导入导出
- **数据浏览**：分页网格（排序/筛选/全选/单元格编辑/右键菜单/列宽记忆）、大表虚拟滚动、
  流式"加载全部"、Excel 批量粘贴插入、CSV/XLSX 导入导出
- **SQL 工作台**：CodeMirror 6 编辑器（关键字高亮/表·字段自动补全）、多结果 tab、
  历史/收藏、格式化、EXPLAIN、写模式（事务包裹+危险确认）
- **对象管理**：表设计器（字段/索引/外键/触发器/SQL 预览）、存储过程/函数/触发器编辑器、
  ER 关系图、结构对比/同步、数据级同步
- **工具**：查询构建器、测试数据生成器、备份/还原、调度任务（定时备份）、数据字典导出、
  DB 用户与权限视图
- **安全**：AES-GCM 落盘 + Windows DPAPI 绑定机器 + RSA-OAEP 传输加密；
  PBKDF2-SHA256(12 万轮) 账号哈希；角色 read/write/admin；登录限流（5 次锁 5 分钟）；
  LDAP/AD 接入；连接可见性 ACL；生产库强制只读；审计日志（操作/用户/IP）
- **权限与在线管理**：管理员可对每个用户按连接（库）配置读写权限与表级白名单/黑名单，
  支持批量配置；在线用户面板实时显示登录时间/IP/当前操作/会话数，可一键强制踢下线（二次确认）
- **服务器配置（admin）**：顶栏「服务器配置」直接读/改 `dbmanager.conf`（监听地址/端口/HTTPS/注册/LDAP 等），
  敏感项掩码显示，保存后重启生效——无需手动编辑文件
- **系统查询**：对内置 SQLite 执行只读 SQL（admin）：系统用户/权限/连接/审计日志/调度任务，直接可查
- **部署**：单命令启动、IPv4/IPv6 双栈、可选 HTTPS（自签证书）、Docker 镜像、
  Windows 一键安装脚本

## 快速开始

**一键启动**（推荐）：装依赖 + 编译前端静态产物 + 启动，全程一个命令。

```bash
# Linux / macOS
./start.sh                 # 后台启动并自动打开浏览器 http://127.0.0.1:8770
./start.sh --fg            # 前台启动 (调试用, 关终端即停)
./start.sh stop|restart|status|build

# Windows
双击 manage.py             # 前台启动 (窗口保持可见, 关窗口即停)
# 或: python manage.py start        # 后台启动
#    python manage.py stop          # 停止
```

> 前端编译为纯静态文件 `frontend/dist/`，由后端 Python `http.server` 直接 serve——
> **不运行任何 node 服务器**，一个 Python 进程同时提供 API 与 Web 界面。

手动分步（等价）：

```bash
# 1. 安装依赖（Python 3.10+）
python -m pip install -r requirements.txt
# 可复现部署(固定精确版本, 含传递依赖): python -m pip install -r requirements.lock

# 2. 编译前端为静态产物 (dist/ 已存在则 start 自动跳过, 无需每次构建)
cd frontend && npm install && npm run build && cd ..

# 3. 启动（默认 http://127.0.0.1:8770）
python app.py
# 或双击 scripts/setup_new_pc.bat（自动装依赖并启动）
```

### 局域网访问（其他电脑连进来）

默认只监听本机（安全设计）。要开放给局域网：

```bash
# ① 改配置: 编辑 dbmanager.conf, 将 [server] 下 host 改为 0.0.0.0
# ② 启动: python app.py (Windows 也可双击 scripts/start_lan.bat)
```

还需两步：
1. **防火墙放行 8770**（管理员 PowerShell 或 CMD 执行一次）：
   `netsh advfirewall firewall add rule name="DB Manager 8770" dir=in action=allow protocol=TCP localport=8770`
2. 其他电脑浏览器访问 `http://<本机局域网IP>:8770`（本机 IP 用 `ipconfig` 查看）

> ⚠️ 开放局域网后，同一网段任何人都能访问——务必先登录改掉默认密码，
> 生产环境强烈建议配合 `ssl=1`（HTTPS，见下节配置表）。

> ⚠️ **安全警告**：首次启动 `ensure_default()` 会**自动创建**默认管理员 `admin / admin123`（admin 角色，数据存 `dbmanager.db`）——即默认部署就是"认证开启 + 公开弱口令"，LAN/公网部署**必须立即登录修改默认密码**，否则内网任意人可登录接管（配合账号管理接口可进一步提权）。可用配置项 `default_pwd`（或环境变量 `DBM_DEFAULT_PWD`）覆盖首次建库密码（仅首次创建生效）。仅在数据库无任何用户且未设 `auth_enabled=1`（`DBM_AUTH=1`）时才为单机无鉴权模式。

## Docker 部署

```bash
docker build -t dbmanager .
docker run -p 8770:8770 -v dbmanager_data:/app/data dbmanager
```

## 配置（dbmanager.conf 配置文件）

日常配置写项目根 **`dbmanager.conf`**（UTF-8 INI，模板见 `dbmanager.conf.example`，改后重启生效）。

> 优先级：**环境变量 > 配置文件 > 内置默认值**。环境变量保留给 CI/Docker/临时覆盖，
> 日常使用无需设置任何环境变量。敏感项（网关令牌/默认密码/LDAP 密码）建议留空由系统自动管理。

| 配置项（`[server]`） | 作用 | 默认 |
|------|------|------|
| `host` | 监听地址：`127.0.0.1`=仅本机（安全默认）；**`0.0.0.0`=开放局域网/公网** | `127.0.0.1` |
| `port` | 监听端口 | `8770` |
| `db_file` | 程序数据文件位置（如数据盘/共享目录） | `data/dbmanager.db`（data/ 目录） |
| `dev` | `1`=开发模式（跳过登录、错误透传详情） | 关 |
| `log` | `1`=控制台输出每请求一行（调试用） | 关 |
| `no_open` / `no_kill` | 不自动开浏览器 / 不自动接管端口 | 关 |
| `ssl` / `ssl_cert` / `ssl_key` | `ssl=1` 启用 HTTPS（自动生成自签名证书）；或提供自有证书 | 关 |
| `gateway_token` | 公网网关令牌（留空自动生成并保存 `.dbm_gateway`） | 自动 |
| `default_conn` | 默认连接（JSON 字符串，免手动连接） | 无 |

| 配置项（`[auth]`） | 作用 | 默认 |
|------|------|------|
| `default_pwd` | 首次创建默认 admin 的密码（仅首建生效；⚠️ 明文落盘，建议留空） | `admin123` |
| `allow_register` | `0`=关闭自助注册（默认开启：成员注册后待管理员审批） | 开 |
| `auth_enabled` | `1`=强制启用账号体系（数据库无用户也启用） | 关 |
| `ldap_url` / `ldap_base` | 启用 LDAP/AD 认证（可选依赖 ldap3） | 关 |
| `ldap_binddn` / `ldap_bindpw` | 可选绑定查询账号 | 无 |
| `ldap_attr` | LDAP 登录属性 | `sAMAccountName` |

## 项目结构

```
app.py          入口（服务器/SSL/启动流程）
handler.py      HTTP 层：全部 API 路由、会话/网关鉴权、审计、请求日志
ops.py          数据操作层：元数据/CRUD/SQL 控制台/导入导出/同步/EXPLAIN
dbcore.py       引擎管理（URL 构建/缓存/超时/连接测试）
auth.py         账号体系（登录/RBAC/LDAP/限流）
crypto.py       密码加解密（AES-GCM 落盘/RSA 传输/DPAPI）
store.py        连接配置持久化
config.py       配置与共享状态（dbmanager.conf 读取，优先级 环境变量 > 配置 > 默认）
task_sched.py   调度任务（定时备份，tasks 存 SQLite）
logging_conf.py 结构化日志（控制台 + logs/dbmanager.log 轮转）
frontend/       Vue3 前端（Vite + TS + Pinia + CodeMirror 6，唯一入口；构建产物 frontend/dist）
docs/           设计文档 / 迁移差距清单
tests/          单测 + 端到端脚本
logs/           审计日志(audit.log) + 运行日志(dbmanager.log)
```

## 开发

```bash
# 后端测试
python tests/smoke_test.py        # 冒烟
python tests/test_ops.py          # 操作层单测
python tests/test_auth_ldap.py    # 认证/LDAP 单测
python tests/test_task_sched.py   # 调度任务单测
# 端到端(需先启动服务): tests/e2e_*.py

# 前端(Vue3, 唯一入口)
cd frontend && npm install
npm run build                      # 产物 frontend/dist, 后端 / 与 /v2 自动读取
npx tsc --noEmit                   # 类型检查
```

## 数据存储

- **程序数据**：`dbmanager.db`（SQLite，`data/dbmanager.db`）——规范化表存储：用户账号/角色/审批状态（`users`）、
  细粒度权限（`user_perms`/`user_perm_tables`）、保存的连接配置（`connections`，密码加密存储）、
  审计日志（`audit_log`）、调度任务（`tasks`）。旧版 `users.json` / `connections.json` / `tasks.json`
  首次启动自动迁移入库，源文件改名为 `.bak` 保留；确认无误后可删除。
- **自定义位置**：`DBM_DB_FILE` 可指定数据库文件路径（如数据盘/共享目录）
- **系统查询**：管理员顶栏「系统查询」可对内置 SQLite 执行只读 SELECT
  （系统用户/权限/连接/审计/任务），`/api/audit` 提供结构化审计查询
- 会话（在线登录/连接）在内存中，重启即清

## 日志

- **运行日志**：`logs/dbmanager.log`（5MB × 3 轮转），含启动信息与请求日志
  （`方法 路径 状态 耗时 user=`）
- **审计日志**：`logs/audit.log`，关键操作（登录/增删改/SQL 写/还原/导入/任务等）
  按 `时间|IP|操作|详情|用户` 追加，超 5MB 轮转

## 安全

- 默认账号 `admin/admin123` 首次启动自动创建 —— **生产环境请立即改密**
  （前端「改密」或 `POST /api/password`）
- 连接密码 AES-GCM 加密落盘（Windows 上绑定当前用户 DPAPI），传输走 RSA-OAEP
- 生产库可在连接配置中标记 `read_only`（强制只读，写操作 403）
- 连接可见性 `visible_to` 控制谁能看到/使用该连接

## 说明

- LICENSE：**Apache License 2.0 开源**，可自由使用/修改/再分发（含商用），详见根目录 `LICENSE`
- 前端已收口为 Vue3 单入口（`frontend/dist` 构建产物；`/` 与 `/v2` 均服务该产物）。
  旧版原生前端（`index.html` + `js/` + `css/`）已彻底移除；未构建前端时服务返回 503 提示（`cd frontend && npm run build`）

## 贡献

欢迎 Issue 与 Pull Request。开发/测试约定见 `docs/` 与 `CONTRIBUTING.md`；
安全漏洞报告渠道见 `SECURITY.md`。

## 支持项目（可选）

软件本身免费，不付费也能用全部功能。想支持它继续发展的话：

- 赞助：[GitHub Sponsors](https://github.com/sponsors/SamXMG)（仓库页 Sponsor 按钮）
- 企业支持订阅：优先响应、部署保障、安全通告，见 [`docs/SUPPORT.md`](docs/SUPPORT.md)
- 定制开发：专属功能按单报价，通用能力回馈开源版，见 [`docs/SUPPORT.md`](docs/SUPPORT.md)

赞助与否不影响任何权利。Apache-2.0 允许自由使用、修改、再分发（含商用）。
