# DB Manager

[![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/SamXMG/dbmanager/actions/workflows/ci.yml/badge.svg)](https://github.com/SamXMG/dbmanager/actions/workflows/ci.yml)

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
- **部署**：单命令启动、IPv4/IPv6 双栈、可选 HTTPS（自签证书）、Docker 镜像、
  Windows 一键安装脚本

## 快速开始

```bash
# 1. 安装依赖（Python 3.10+）
python -m pip install -r requirements.txt
# 可复现部署(固定精确版本, 含传递依赖): python -m pip install -r requirements.lock

# 2. 启动（默认 http://127.0.0.1:8770，自动打开浏览器）
python app.py

# 或双击 setup_new_pc.bat（自动装依赖并启动）
```

> ⚠️ **安全警告**：首次启动 `ensure_default()` 会**自动创建** `users.json` 并生成默认管理员 `admin / admin123`（admin 角色）——即默认部署就是"认证开启 + 公开弱口令"，LAN/公网部署**必须立即登录修改默认密码**，否则内网任意人可登录接管（配合账号管理接口可进一步提权）。可用环境变量 `DBM_DEFAULT_PWD` 覆盖首次建库密码（仅首次创建生效）。仅在手动删除 `users.json` 且未设 `DBM_AUTH=1` 时才为单机无鉴权模式。

## Docker 部署

```bash
docker build -t dbmanager .
docker run -p 8770:8770 -v dbmanager_data:/app/data dbmanager
```

## 配置（环境变量）

| 变量 | 作用 | 默认 |
|------|------|------|
| `DBM_HOST` / `DBM_PORT` | 监听地址 / 端口（安全默认仅本机；局域网/公网访问显式设 `DBM_HOST=0.0.0.0`） | `127.0.0.1` / `8770` |
| `DBM_DEV=1` | 开发模式（跳过登录、错误透传详情） | 关 |
| `DBM_AUTH=1` | 强制启用账号体系（无 users.json 也启用） | 关 |
| `DBM_DEFAULT_PWD` | 覆盖首次创建默认 admin 的密码（仅首建生效） | `admin123` |
| `DBM_ALLOW_REGISTER=1` | 开放自助注册（默认只读角色） | 关 |
| `DBM_LDAP_URL` / `DBM_LDAP_BASE` | 启用 LDAP/AD 认证（可选依赖 ldap3） | 关 |
| `DBM_LDAP_ATTR` | LDAP 登录属性 | `sAMAccountName` |
| `DBM_GATEWAY_TOKEN` | 固定公网网关令牌 | 首次启动自动生成 |
| `DBM_SSL=1` / `DBM_SSL_CERT` / `DBM_SSL_KEY` | 启用 HTTPS | 关 |
| `DBM_DEFAULT_CONN` | 默认连接（JSON 字符串，免手动连接） | 无 |
| `DBM_NO_OPEN=1` / `DBM_NO_KILL=1` | 不自动开浏览器 / 不自动接管端口 | 关 |
| `DBM_NO_KILL` 说明 | 双实例启动时自动终止旧实例 | 自动 |

## 项目结构

```
app.py          入口（服务器/SSL/启动流程）
handler.py      HTTP 层：全部 API 路由、会话/网关鉴权、审计、请求日志
ops.py          数据操作层：元数据/CRUD/SQL 控制台/导入导出/同步/EXPLAIN
dbcore.py       引擎管理（URL 构建/缓存/超时/连接测试）
auth.py         账号体系（登录/RBAC/LDAP/限流）
crypto.py       密码加解密（AES-GCM 落盘/RSA 传输/DPAPI）
store.py        连接配置持久化
config.py       配置与共享状态
task_sched.py   调度任务（定时备份，tasks.json 持久化）
logging_conf.py 结构化日志（控制台 + logs/dbmanager.log 轮转）
frontend/       Vue3 迁移版前端（Vite + TS + Pinia + CodeMirror 6）
index.html+js/  旧版原生前端（迁移完成前并存，访问 /v2 用新版）
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

# 前端(迁移版 /v2)
cd frontend && npm install
npm run build                      # 产物 frontend/dist, 后端 /v2 自动读取
npx tsc --noEmit                   # 类型检查
```

## 日志

- **运行日志**：`logs/dbmanager.log`（5MB × 3 轮转），含启动信息与请求日志
  （`方法 路径 状态 耗时 user=`）
- **审计日志**：`logs/audit.log`，关键操作（登录/增删改/SQL 写/还原/导入/任务等）
  按 `时间|IP|操作|详情|用户` 追加，超 5MB 轮转

## 安全

- 默认账号 `admin/admin123` 首次启动自动创建 —— **生产环境请立即改密**
  （前端「改密」或 `POST /api/password`），或先创建 `users.json` 再启动
- 连接密码 AES-GCM 加密落盘（Windows 上绑定当前用户 DPAPI），传输走 RSA-OAEP
- 生产库可在连接配置中标记 `read_only`（强制只读，写操作 403）
- 连接可见性 `visible_to` 控制谁能看到/使用该连接

## 说明

- LICENSE：**Apache License 2.0 开源**，可自由使用/修改/再分发（含商用），详见根目录 `LICENSE`
- 旧版前端（`index.html` + `js/`）已不再是默认入口（`/` 直接服务 Vue3 构建产物），
  仅作为前端未构建时的开发兜底保留，后续将彻底移除

## 贡献

欢迎 Issue 与 Pull Request。开发/测试约定见 `docs/` 与 `CONTRIBUTING.md`；
安全漏洞报告渠道见 `SECURITY.md`。

## 支持项目（可选）

软件本身免费，不付费也能用全部功能。想支持它继续发展的话：

- 赞助：[GitHub Sponsors](https://github.com/sponsors/SamXMG)（仓库页 Sponsor 按钮）
- 企业支持订阅：优先响应、部署保障、安全通告，见 [`docs/SUPPORT.md`](docs/SUPPORT.md)
- 定制开发：专属功能按单报价，通用能力回馈开源版，见 [`docs/SUPPORT.md`](docs/SUPPORT.md)

赞助与否不影响任何权利。Apache-2.0 允许自由使用、修改、再分发（含商用）。
