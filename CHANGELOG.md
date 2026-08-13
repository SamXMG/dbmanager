# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。发版流程：更新 `config.py VERSION` 与 `frontend/package.json version` → 追加本节 → 打 tag `vX.Y.Z`（自动触发 Release 构建）。

## [Unreleased] - 配置中心化

### 新增
- **配置文件 `dbmanager.conf`**：INI 格式（UTF-8），日常配置写文件、改后重启生效；
  优先级 **环境变量 > 配置文件 > 内置默认值**（环境变量保留给 CI/Docker/临时覆盖）。
  模板见 `dbmanager.conf.example`，本地 `dbmanager.conf` 已入 .gitignore（防敏感项入库）
- 局域网开放改为改配置：`[server] host = 0.0.0.0`，不再依赖环境变量；`start_lan.bat` 语义保持
- **服务器配置管理界面（仅 admin）**：顶栏「服务器配置」弹窗可读/改 dbmanager.conf
  （`GET/POST /api/config/settings`）；敏感键（网关令牌/默认密码/LDAP 密码）掩码显示、掩码占位不覆盖；
  白名单键校验（port 范围/开关取值/防换行注入），写回保留注释与段归属，变更审计
- **配置即时生效 + 一键重启**：LDAP/注册开关/强制认证/网关令牌等运行时读取项保存后**即时生效**；
  host/port/HTTPS 等启动期配置标「需重启」，提供 `POST /api/config/restart`（仅 admin）**一键重启**，
  新实例自动接管端口，约 2~3 秒恢复（前端弹窗带生效类型标签 + 立即重启按钮）

### 工程化
- `config.py` 新增 `conf()/conf_int()/conf_bool()` 统一读取（22 处环境变量读取点全部收口）
- `auth.py` LDAP 配置改为运行时读取（`_ldap_cfg()`），配置管理界面改 LDAP 无需重启即生效

### 修复
- `tests/test_auth_ldap.py`、`tests/test_task_sched.py` 数据层失配：仍在 mock 旧 users.json/tasks.json，
  而程序数据已迁 SQLite——测试会**污染真实 dbmanager.db**（写入测试账号/任务）。已改为在 import 前
  将 `DBM_DB_FILE` 指到临时库隔离，并改用 sqlitedb API 写入，防污染真实数据
- **安全 P0（专业复核 2026-08-13 确认的两处真实注入 + 门禁回归）**：
  - `services/tools.py stats_column`：`/api/stats` 的 `where` 此前裸拼进 `text(...)`，未走
    `safe_where_clause`——已对齐 get_data/export 范式（禁分号/注释 + 字段白名单），已认证用户
    无法再 UNION/子查询抽取数据
  - `services/core.py _check_default`：`/api/alter` 的 default 校验正则过松（仅拦 `--`/`*/`/双特殊符），
    单分号+子查询可绕过——已改为**白名单**（数字/单引号字符串/NULL/布尔/安全时间函数），PG/MSSQL
    上无法再执行任意 SQL
  - **CI e2e 修复**：`.github/workflows/ci.yml` 后端 job 的 e2e 两 step 补 `env: DBM_DEFAULT_PWD`；
    `e2e_http_smoke.py`/`e2e_auth.py`/`e2e_acl.py` 登录密码改为读取 `DBM_DEFAULT_PWD`（未设置回退
    admin123），并给 e2e_http_smoke 子进程隔离 `DBM_DB_FILE`——本地实测 e2e_auth 17 / acct 19 /
    acl 17 / http_smoke 11 全绿（此前 CI 干净检出必红）
  - `crypto.py _load_rsa_key`：`.dbm_rsa` 私钥生成后补 `os.chmod(0o600)`（与 `.dbm_key` 对齐，
    Linux/Mac 防同机其他用户读私钥）
  - `handler.py`：`/api/register` 移出公网网关豁免白名单——公网客户端必须先验证网关令牌才能注册
    （内网/局域网注册不受影响，审批流+IP 限流保留），堵住外部无令牌自助注册面

## [1.5.0] - 2026-08-12

### 新增
- 程序数据迁 SQLite：用户/角色/审批状态/细粒度权限/连接配置统一存 `dbmanager.db`（WAL，事务原子写）；
  旧版 users.json / connections.json 首次启动自动迁移入库（源文件改名 .bak 保留）；`DBM_DB_FILE` 可自定义位置
- 细粒度权限：管理员按用户配置连接（库）级读写开关 + 表级白名单/黑名单，支持批量配置；服务端统一拦截
  （连接入口 / 数据读写 / 对象树 / SQL 控制台表名），仅 admin 可配、权限变更审计
- 在线用户管理：实时列表（用户名/角色/登录时间/IP/最后活跃/当前操作/会话数，5s 轮询）+ 一键踢下线
  （二次确认、删除全部会话、不能踢自己）
- 强制首次改密：默认 admin 账号首次登录必须修改密码（is_default 标记，兼容老部署默认口令检测）；未改密前业务接口一律 403，只放行改密、登出和配置；登录响应和 /api/config 返回 must_change_pwd，前端强制改密弹窗不可关闭
- 健康检查与监控指标：/api/health（探活，免登录）、/api/metrics（Prometheus 文本格式），指标统计独立成 metrics.py，无第三方依赖
- 前端收口：默认入口 / 直接服务 Vue3 构建产物，旧版 index.html 只在未构建时兜底
- 开源授权：切换为 Apache License 2.0（可自由使用/修改/再分发含商用）；发布前重写 git 历史清除全部敏感文件（密钥、连接配置、测试库，139→133 commits）
- 文档：新增 docs/USER_GUIDE.md（用户手册）、docs/DEPLOYMENT.md（部署指南）、docs/API.md（接口参考）
- 前端单元测试：引入 vitest（18 项），覆盖筛选条件与 SQL 格式化的注入防护；接入 CI 和发版流程

### 工程化
- 请求日志接入指标计数（方法/路径/状态码/5xx，线程安全）
- 请求体解析加缓存：权限检查与路由处理各读一次 body 不再重复读流（修复请求挂起）
- 程序数据全面规范化：users 拆真列 + 权限拆关系表（user_perms/user_perm_tables）、connections 拆真列、
  审计日志入表（audit_log，与 audit.log 文件双写）、调度任务入表（tasks，旧 tasks.json 自动迁移）
- 系统查询：POST /api/sysdb（admin 只读 SELECT，白名单校验防注入）+ GET /api/audit 审计筛选查询；
  前端「系统查询」面板（快捷查询：用户/权限/连接/审计/任务）
- 前端 API_BASE 兼容 node 测试环境
- 版本号更新到 1.5.0

### 修复
- 新增路由模块缺 handle_post 导致 POST 请求 500（补空实现并纳入回归）
- 启动时明文 HTTP 监听非回环地址时增加安全提醒

### 开源变现配套
- .github/FUNDING.yml：GitHub 仓库页自动显示 Sponsor 按钮
- docs/SUPPORT.md：赞助、企业支持订阅、定制开发说明
- docs/ENTERPRISE.md：企业版路线图（规划中，全部为开源版之上的增量功能）
- README 增加「支持项目」说明

## [1.4.0] - 2026-08-12

### 新增
- **多数据库扩展**：Oracle（python-oracledb thin，免客户端）/ MongoDB（pymongo 独立路径）/ Redis（redis-py + RESP2 兼容 Redis 5）完整支持；OceanBase/TiDB（MySQL 协议）、KingbaseES（PG 协议）一键连接
- **查询能力**：MongoDB 筛选框 JSON 条件查询（find 过滤/排序，拒绝 `$where` 等代码执行操作符）；Redis 键 pattern/类型过滤
- **Navicat 化右键菜单**：连接/库/表/视图 4 层重构，表级 16 项（新建/重命名/复制表/维护/清空/截断/删除等）；固定表快捷方式（pinned-bar）
- **后端新 action**：rename_table / truncate_table / clear_table / copy_table / maintain（四方言兼容）
- **工程化**：routes/ + services/ 分层重构（handler 1311→~800 行，ops 1974→11 模块）；CI 补强（pyflakes/import 完整性/HTTP 全链路冒烟/前端 vue-tsc + build）；版本号与 CHANGELOG

### 修复
- Redis 5 无 `HELLO` 命令导致的连接失败（强制 RESP2）
- 连接管理/登录弹窗未传 `show` prop 导致不显示（vue-tsc 发现）
- ObjectTree 表项类型缺 `name` 字段（vue-tsc 发现）
- git rebase 卡死恢复（`git rebase --abort` 回到 main）

### 变更
- 前端由纯 JS 重构为 Vue3 + TypeScript + Pinia + CodeMirror6 + 虚拟滚动
- 增加登录认证（默认 admin/admin123）、角色分级（read/write/admin）、LDAP 可选

## [1.3.0] - 2026-08-11

- Vue3 迁移（阶段 4/5）：SQL 工作台、表设计器、ER 关系图、数据同步、右键菜单组件化
- SSH 隧道连接、云厂商连接模板、EXPLAIN 可视化、ER 图

## [1.0.0] - 2026-08-11

- 初始功能：多数据库连接、数据浏览/编辑、SQL 控制台、导入导出、备份还原
