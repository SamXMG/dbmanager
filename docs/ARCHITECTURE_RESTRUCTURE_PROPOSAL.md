# 后端目录结构优化提案（评估 + 方案）

> 生成日期：2026-08-15
> 目的：评估当前后端文件架构是否需要优化，给出明确的目录划分方案与迁移路径。
> 状态：**提案（未执行）**。本文只给方案，不含任何文件移动——需批准后单独作为重构 PR 落地。

---

## 1. 结论（TL;DR）

| 问题 | 结论 |
|---|---|
| 是否需要重构？ | **需要，但非紧急**。当前可运行、可测试（M2 覆盖率 67%），属"健康度/整洁度"优化，不是故障修复。 |
| `services/` 按功能拆分？ | **方向正确，保留不动**。 |
| `routes/` 按领域拆分？ | **方向正确，保留不动**。 |
| 真正该优化的点？ | **根目录 18 个基础设施文件平铺混排**，且数据访问层（DAL）无显式命名空间。建议新增 `db/` 并把平台文件按类型归入 `core/` `server/` `infra/`。 |
| 要不要把 routes/services 按 domain 深度合并？ | **不建议**。会破坏 `services` 的跨领域复用、制造循环依赖。 |
| 何时做？ | 作为**独立重构 PR**，与功能开发隔离；不推荐在换电脑/交付窗口期立刻大改。 |

---

## 2. 现状实测盘点

### 2.1 后端文件分布（实测）

```
dbmanager/
├── 根目录 .py（18 个，平铺）
│   ├── app.py            入口：服务器类/SSL/启动流程（双栈 IPv4+IPv6）
│   ├── manage.py         CLI 管理入口
│   ├── handler.py        HTTP 网关：会话/网关令牌/HTTPS/静态资源/路由装配
│   ├── handler_security.py 安全网关：SSRF/注入防护（P0）
│   ├── ops.py            业务门面：re-export 全部 services.*（向后兼容）
│   ├── config.py         配置与共享状态（常量/路径/缓存/锁/驱动选择）
│   ├── crypto.py         密码加解密（AES-GCM 落盘/RSA 传输/DPAPI）
│   ├── auth.py           账号体系（users.json→SQLite；角色 read/write/admin）
│   ├── i18n.py           国际化（t("key")）
│   ├── logging_conf.py   结构化日志配置
│   ├── dbcore.py         ★DAL-1：目标库引擎/URL 构建/连接缓存/事务连接
│   ├── sqlitedb.py       ★DAL-2：程序自身 SQLite（用户/权限/连接/审计/任务）
│   ├── store.py          ★DAL-3：连接配置持久化（封装 sqlitedb）
│   ├── scanner.py        扫描（端口/数据库探测）
│   ├── metrics.py        指标/监控
│   ├── task_sched.py     任务调度
│   ├── tunnel.py         SSH 隧道
│   └── get_ipv6.py       获取本机 IPv6 地址
├── routes/（7 领域，+__init__）   ← 已按领域拆分（正确）
│   ├── connection.py query.py schema.py files.py routines.py monitor.py admin.py
├── services/（11 功能，+__init__） ← 已按功能拆分（正确）
│   ├── core.py metadata.py nosql.py data.py sql.py ddl.py
│   ├── export.py sync.py routines.py tools.py backup.py
└── tests/                          ← 大量单测 + e2e
```

### 2.2 当前分层（依赖方向自上而下，无循环）

```
入口层      app.py / manage.py
HTTP 网关层  handler.py / handler_security.py
路由层(领域) routes/*            ← handle_get/handle_post
业务服务层(功能) services/*      ← 真正的业务逻辑
业务门面     ops.py              ← from services import * 的兼容壳
数据访问层   dbcore.py + sqlitedb.py + store.py   ← 散落根目录，无统一命名空间
平台基础设施 config/crypto/auth/i18n/logging_conf/scanner/metrics/task_sched/tunnel/get_ipv6
```

### 2.3 关键事实
- `ops.py` 是 `services/*` 的 **re-export 门面**（`from services.xxx import Y` 再 `__all__` 导出），说明架构演进路径：早期逻辑全在 `ops.py` 一个大文件 → 拆到 `services/` 按功能 → 用 `ops.py` 保持 `from ops import X` 旧调用不变。**这是"先拆功能、保留兼容"的范例，应沿用此策略做下一步整理。**
- `dbcore.py` 与 `sqlitedb.py`/`store.py` 虽同属"数据访问"，但职责不同：前者是**目标数据库连接引擎**，后者是**程序自身元数据持久化**。三者都裸放在根目录，新人难以一眼识别 DAL 边界。

---

## 3. 现存问题

1. **根目录承载多关注点，平铺混排**：入口、HTTP 网关、DAL、配置、加密、认证、日志、i18n、运维工具（扫描/指标/调度/隧道/IPv6）共 18 个模块挤在根目录，角色不直观。
2. **数据访问层无显式命名空间**：`dbcore`/`sqlitedb`/`store` 三者都是"数据库访问"，却与 `config`/`crypto` 等并列，缺少 `db/` 这样的语义容器。
3. **导入耦合在顶层**：全项目用裸模块导入（`import config`、`from config import X`、`import handler`），跨目录移动会牵动所有 import 路径与 `tests/` 引用。
4. **命名偶发不一致**：`handler_security.py`（下划线）与 `handler.py` 同类却不同风格；`get_ipv6.py` 是工具脚本而非模块，混入业务模块区。

---

## 4. 目标目录方案（"业务按功能、平台按类型"双轨）

```
dbmanager/
├── app.py                      # 保留根：应用入口（明确）
├── manage.py                   # 保留根：CLI 入口（明确）
├── ops.py                      # 保留根：业务门面（re-export services，向后兼容）
│
├── server/                     # 【新】HTTP 网关/服务器（按类型）
│   ├── __init__.py
│   ├── http_server.py          # ← handler.py（会话/网关令牌/HTTPS/静态/路由装配）
│   └── security.py             # ← handler_security.py（SSRF/注入防护）
│
├── routes/                     # 【保持】领域路由层
│   ├── __init__.py            #   ROUTE_MODS 注册顺序不变
│   ├── connection.py query.py schema.py files.py routines.py monitor.py admin.py
│
├── services/                   # 【保持】业务服务层（按功能）
│   ├── __init__.py
│   ├── core.py metadata.py nosql.py data.py sql.py ddl.py
│   ├── export.py sync.py routines.py tools.py backup.py
│
├── db/                         # 【新】数据访问层（显式 DAL）
│   ├── __init__.py
│   ├── engine.py               # ← dbcore.py（目标库引擎/URL/连接缓存/事务）
│   ├── meta_store.py           # ← sqlitedb.py（程序自身 SQLite：用户/权限/连接/审计/任务）
│   └── conn_store.py           # ← store.py（连接配置持久化封装）
│
├── core/                       # 【新】平台核心/基础设施（按类型）
│   ├── __init__.py
│   ├── config.py               # ← config.py
│   ├── crypto.py               # ← crypto.py
│   ├── auth.py                 # ← auth.py（账号体系）
│   ├── i18n.py                 # ← i18n.py
│   └── logging_conf.py         # ← logging_conf.py
│
├── infra/                      # 【新】运维/工具类（按类型）
│   ├── __init__.py
│   ├── scanner.py              # ← scanner.py
│   ├── metrics.py              # ← metrics.py
│   ├── task_sched.py           # ← task_sched.py
│   ├── tunnel.py               # ← tunnel.py（SSH 隧道）
│   └── ipv6.py                # ← get_ipv6.py（去掉 get_ 前缀，统一模块命名）
│
├── tests/                      # 【保持】单测 + e2e
└── frontend/                   # 【保持】
```

### 4.1 设计原则
- **业务代码按"功能/领域"分**：`services/`（功能复用）与 `routes/`（领域端点）的双层已清晰，且 `services` 被多个 `routes` 共享——**这是正确分层，保留**。
- **平台/基础设施按"类型/关注点"分**：HTTP 网关归 `server/`、DAL 归 `db/`、核心配置归 `core/`、运维工具归 `infra/`。平台代码不被"领域"切分，按职责大类聚合更自然。
- **不为复用而硬合并 domain**：把 `routes/connection` + `services/...` 合并成 `domains/connection/` 看似整洁，但 `services/metadata` 等被 5+ 个路由复用，强行按 domain 合并会制造循环依赖、破坏复用。故**不采用** domain 深度合并。

---

## 5. 迁移步骤与风险

### 5.1 主要风险
- **R1（最大工作量）**：全项目裸模块导入（`import config` 等）。移动后需改为 `from core import config` 或保持 `sys.path` 注入；`tests/` 中 `import handler` / `from routes import ...` / `from services import ...` 需同步改路径。
- **R2**：`app.py`/`handler.py` 是启动入口，移动需谨慎验证启动流程（双栈、HTTPS、线程池）。
- **R3**：`ops.py` 门面引用的 `services.*` 路径若变，需同步；`handler.py` 引用 `from ops import mutate` 等需核对。

### 5.2 推荐步骤（分批 + 回归）
1. 新建 `server/` `db/` `core/` `infra/` 目录，各加 `__init__.py`。
2. **分批移动**（每批 ≤3 个文件），每批执行：
   - 移动文件 → 改该文件及调用方的 import → 批量替换 `tests/` 引用；
   - 跑 `python -c "import app"` 验证导入；
   - 跑后端冒烟（`scripts/start.bat` / `python app.py` 起服务，`curl /api/...`）；
   - 跑 `pytest tests/ -q`（注意：全量覆盖率 `combine()` 会触发沙箱安全删除守卫，需 `dangerouslyDisableSandbox` 或 `rm -f .coverage .coverage.*` 绕过）。
3. 更新 `README.md` / `docs/` 架构图与启动说明。
4. 确认 CI（`pytest --cov-fail-under=60`）仍绿。

### 5.3 命名一致性附带清理
- `handler_security.py → server/security.py`、`get_ipv6.py → infra/ipv6.py`（去掉 `get_` 动词前缀，统一"名词即模块"风格）。

---

## 6. 优先级与执行时机建议

- **紧急度：低**。当前可运行、有测试覆盖，不是阻塞项。
- **价值：中**。降低新人认知负荷、显式化 DAL 边界、为后续"连接池治理/多租户"等改动提供清晰落点。
- **时机**：作为**独立重构 PR**，与功能开发隔离；避免在"换电脑/交付窗口"期大改（会让 `git` 状态混乱、跨机器同步复杂）。
- **最小可行第一步（可选）**：仅新增 `db/` 目录收口 `dbcore`/`sqlitedb`/`store` 三个 DAL 文件——风险最小、收益最直接（DAL 边界最模糊的部分先显式化），其余平台文件可后续分批。

---

## 7. 一句话总结
> 业务层（routes/services）的"按功能/领域"拆分已做对，保留；只需把根目录 18 个平台/基础设施文件按类型收口到 `server/` `db/` `core/` `infra/`，并显式化数据访问层——这是整洁度优化，建议独立 PR、配 pytest 回归，非紧急。
