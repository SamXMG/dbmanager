# DBManager 商业级改造路线图 (REMEDIATION ROADMAP)

> 生成日期：2026-08-14
> 基线：基于 2026-08-14 全量代码重读评估（非截断快照）
> 目标：从「内网商用级团队工具」→「可公开售卖的商业产品」
> 状态：待确认

---

## 0. 背景与总览

当前快照相比最初评估已是**代际级变化**：此前误判的 6 项（分层架构 / 持久化统一 / 安全响应头 / CI 工业级 / 前端测试 / 旧前端退役）已全部落地，并额外完成了 AES-GCM 落盘、审计双写、网关令牌、Prometheus metrics、Docker 多阶段构建、6 篇文档等工程化改造。

剩余差距按「是否阻断公开商用」分为四级。本路线图把每一项落成**可执行 Backlog**，含改动点、验收标准、工期、依赖、风险。所有"现状"均经代码/配置核验（见各条 `核实` 字段）。

**综合基线评分（评估结论）**

| 维度 | 完成度 |
|------|--------|
| 核心功能 | 92% |
| 安全 | 85% |
| 工程化 | 75% |
| 可观测性 | 80% |
| 部署交付 | 65% |
| 文档 | 85% |
| 产品化 | 50% |

**总工期估算**：P0（2-3 周）+ P1（1-1.5 周）≈ 4-4.5 周可达公开商用门槛；P2/P3 为可选增强。

---

## 1. 里程碑规划

| 里程碑 | 范围 | 工期 | 出口标准 |
|--------|------|------|----------|
| **M0 门禁对齐** | P1-6 Docker 瘦身 + .bak 清理 + 建分支策略 | 0.5-1 天 | 镜像瘦身验证通过；根目录无残留备份 |
| **M1 产品化硬伤（P0）** | i18n + 安装包/自动更新 | 2-3 周 | 中英切换无硬编码残留；双击安装即用；更新机制可用 |
| **M2 工程化收尾（P1）** | 前端 lint + 门禁转阻断 + 覆盖率 | 1-1.5 周 | ESLint 0 warning；mypy/ruff format 阻断；覆盖率门槛生效 |
| **M3 功能深度（P2，可选）** | 执行计划树形 / undo UI / 协作 | 2-3 周 | 逐项独立验收 |
| **M4 增强（P3，可选）** | Sentry / SSO / 审计页 / 会话外置 | 1-2 周 | 逐项独立验收 |

关键路径：**M0 → M2（低风险先收口）→ M1（大块并行）→ M3/M4（按需）**。

---

## 2. 详细 Backlog

### P0 — 产品化硬伤（公开商用前必须补）

#### P0-1：i18n 国际化
- **现状**：前端全部硬编码中文；`frontend/package.json` 无 `vue-i18n`，无语言包（已核验：devDeps 仅含 vite/vitest/vue-tsc 等，无 i18n 依赖）。
- **改动点**：
  - `frontend/package.json` 新增 `vue-i18n`（依赖，非 dev）；
  - 新增 `frontend/src/locales/{zh-CN,en-US}.ts`；
  - 抽离约 200 处模板/store 硬编码字符串为 `$t(key)`；
  - 新增语言切换组件（接入现有 ui store，`body[data-theme]` 同机制）；
  - 后端错误文案若前端展示，需同步 key 或维持中文+英文双字段。
- **验收标准（EARS）**：
  - When 用户切换语言为 English，系统**必须**将所有 UI 文本渲染为英文且无中文硬编码残留；
  - If 新增字符串未提供英文翻译，CI**必须**在 i18n 完整性检查中失败。
- **工期**：3-5 天
- **依赖**：无（可独立启动）
- **风险**：字符串抽取易漏，需先定 key 命名规范（如 `module.action.noun`）；CodeMirror SQL 提示等动态文本需单独处理。

#### P0-2：安装包 / 自动更新
- **现状**：仅 `python app.py` 与 Docker；无 `.exe/.msi/.dmg/.deb`；无自动更新。普通用户无法一键安装。
- **改动点**：
  - 打包：`PyInstaller` 单文件/单目录（Windows 优先），或原生安装器（NSIS/InnoSetup）/ macOS `.pkg` / Linux `.deb`；
  - 自动更新：GitHub Release 版本比对 + 增量下载 + 重启自检；
  - 文档：`docs/DEPLOYMENT.md` 增补桌面安装章节。
- **验收标准**：
  - When 用户在无 Python 环境的机器双击安装包，系统**必须**完成安装并启动可访问的 Web 服务；
  - When 检测到新 Release，系统**必须**提示并更新，且更新失败可回滚。
- **工期**：1-2 周
- **依赖**：**决策待定**——目标平台（Win/macOS/Linux 优先级）、是否需代码签名/公证。
- **风险**：ODBC 驱动/动态库（msodbcsql18、unixODBC）打包体积与路径；Windows SmartScreen 与 macOS Gatekeeper 签名成本。

---

### P1 — 工程化收尾

#### P1-3：前端 ESLint / Prettier
- **现状**：`frontend/package.json` 无 eslint/prettier 依赖与脚本；`.eslintrc`/`.prettierrc` 不存在（已核验）；CI frontend job 仅 vitest + vue-tsc + build + npm audit（ci.yml 125-146）。
- **改动点**：
  - `frontend/package.json` 增 `eslint` + `eslint-plugin-vue` + `@typescript-eslint/*` + `prettier` + `eslint-config-prettier`；
  - 新增 `.eslintrc.cjs` / `.prettierrc.json`；
  - 新增 `npm run lint` / `npm run format`；
  - CI frontend job 接入 `npm run lint` 作为门禁。
- **验收标准**：
  - While CI 运行前端 lint，系统**必须**在 `eslint --max-warnings 0` 非零时失败；
  - If 提交含未格式化代码，`prettier --check`**必须**失败。
- **工期**：2-3 天（含存量格式化一轮）
- **依赖**：无

#### P1-4：mypy / ruff format 转阻断
- **现状**：ci.yml 第 31-37 行，`ruff format --check` 与 `mypy` 均为 `continue-on-error: true`；mypy 仅查 5 文件（`scanner.py handler_security.py services/core.py config.py dbcore.py`），非全量（已核验）。`.pre-commit-config.yaml` 中二者亦为非阻断提示项。
- **改动点**：
  - 分步：先扩 `mypy` 覆盖至 `routes/`、`services/` 全量，补齐存量类型注解；
  - `ruff format` 全量格式化（CI 注释称当前 52 文件未对齐）；
  - 收敛后移除两处 `continue-on-error: true`，改为硬门禁；
  - 同步更新 `.pre-commit-config.yaml` 使本地与 CI 一致。
- **验收标准**：
  - When 存量类型注解收敛完成，CI 中 mypy**必须**对全量目标文件以 0 error 阻断；
  - When ruff format 全量对齐，`ruff format --check .`**必须**阻断未格式化提交。
- **工期**：2-3 天
- **依赖**：与 P1-3 协调顺序（建议先 P1-3 前端、P1-4 后端并行）

#### P1-5：测试覆盖率报告
- **现状**：ci.yml 第 40-41 行 `python -m pytest tests/ -q` 无 `--cov`；无覆盖率门槛（已核验）。
- **改动点**：
  - `requirements.lock`/测试依赖增 `pytest-cov`；
  - CI 改为 `pytest --cov=services --cov=routes --cov-report=xml --cov-fail-under=60`（门槛从 60% 起步，逐里程碑抬升）；
  - 可选接入 Codecov 上传报告。
- **验收标准**：
  - When PR 触发 CI，系统**必须**产出覆盖率报告；
  - If 覆盖率低于门槛，系统**必须**阻断合并。
- **工期**：1-2 天（含补测试抬升覆盖）
- **依赖**：无

#### P1-6：Docker 运行时瘦身
- **现状**：Dockerfile 第 21-23 行，runtime 阶段（python:3.12-slim）装了 `gcc g++ unixodbc-dev`（已核验）。但第 35 行 `pip install -r requirements.txt` 在 runtime 阶段执行，`gcc/g++` 用于编译 psycopg2/oracledb 等轮子——故**不能简单删除**，正确修法是拆 builder 阶段。
- **改动点**：
  - 新增 Python builder 阶段（`python:3.12-slim` + `gcc g++ unixodbc-dev`），`pip wheel` 预编译所有依赖；
  - runtime 阶段仅保留 `unixodbc`（无 `-dev`）、`curl`、`gnupg`，从 builder 拷预编译 wheel 后 `pip install --no-index`；
  - 保留 msodbcsql18 安装（需 curl/gnupg，已在 runtime 合理）。
- **验收标准**：
  - When 镜像构建完成，runtime 层**必须**不含 `gcc`/`g++`/`unixodbc-dev`；
  - After `docker run` 起库，`import app`**必须** OK（docker job 已校验，ci.yml 154-155）。
- **工期**：0.5-1 天
- **依赖**：注意 psycopg2（PG）、oracledb（Oracle）等编译型驱动需在 builder 阶段成功编译。

#### P1-7（并入）：根目录 `.bak` 残留清理
- **现状**：`connections.json.bak`、`users.json.bak` 为迁移备份残留（评估 P3-14）。
- **改动点**：加入 `.gitignore`（`*.bak`），或迁移后删除；运维说明补一句。
- **工期**：0.25 天

---

### P2 — 功能深度（可选，公开商用后可后置）

| 编号 | 项 | 现状 | 验收方向 | 工期 |
|------|----|------|----------|------|
| P2-7 | 执行计划树形/图形化 | `ExplainPlanModal` 仅展示 EXPLAIN 原始文本 | DataGrip 式树形节点 + 成本占比高亮 + 慢节点定位 | 3-5 天 |
| P2-8 | 数据修改 undo / 事务回滚 UI | 有事务模式但无"撤销上一步"按钮 | 行编辑/批量删除后提供撤销入口 | 2-3 天 |
| P2-9 | 团队协作 | 无共享查询/收藏云同步/表注释协作 | 单机场景可后置，集群/团队场景才需 | 1-2 周 |

---

### P3 — 可选项

| 编号 | 项 | 说明 | 优先级 |
|------|----|------|--------|
| P3-10 | 会话内存态外置 | `USER_SESSIONS` 字典重启丢失、无法多实例；集群才需 Redis | 低 |
| P3-11 | 错误上报（Sentry） | 崩溃只能看日志，无法主动发现 | 中 |
| P3-12 | OIDC/SAML SSO | 仅 LDAP，大企业 SSO 不够 | 中 |
| P3-13 | 审计日志可视化页面 | 当前只能写 SQL 查 `audit_log`；缺时间/用户筛选+导出 UI | 中 |
| P3-14 | 根目录 `.bak` → `.gitignore` | 见 P1-7 | 低 |

---

## 3. 依赖关系与关键路径

```
M0 (Docker瘦身 + .bak清理)  ──┐
                               ├─→ M2 (P1-3/P1-4/P1-5 工程化) ──┐
M1 (P0-1 i18n)  ──────────────┤                                      ├─→ M3 (P2) ─→ M4 (P3)
M1 (P0-2 安装包) ─────────────┘                                      ┘
```

- P0-1 与 P0-2 相互独立，可派不同人并行（前端 vs 打包/发布）。
- P1-3（前端 lint）与 P1-4（后端门禁）可并行；二者均不依赖 P0。
- P1-5（覆盖率）依赖已有测试基础，建议与 P1-3/P1-4 同里程碑收口。
- P1-6（Docker 瘦身）独立且低风险，放入 M0 最先做。

---

## 4. 验收总表（EARS 摘要）

| 编号 | 功能 | EARS 验收标准 | 优先级 |
|------|------|---------------|--------|
| AC-P0-1 | i18n | When 切换 English，系统必须全量渲染英文且无中文硬编码残留 | P0 |
| AC-P0-2 | 安装包 | When 无 Python 环境双击安装，系统必须启动可访问 Web 服务 | P0 |
| AC-P0-3 | 自动更新 | When 检测新 Release，系统必须提示并可回滚更新 | P0 |
| AC-P1-1 | 前端 lint | While CI 运行，`eslint --max-warnings 0` 非零必须失败 | P1 |
| AC-P1-2 | 后端门禁 | When 存量收敛，`mypy` 全量 0 error 且 `ruff format --check` 必须阻断 | P1 |
| AC-P1-3 | 覆盖率 | When PR 触发 CI，必须产出覆盖率报告且低于门槛阻断 | P1 |
| AC-P1-4 | Docker 瘦身 | When 镜像构建完成，runtime 必须不含 gcc/g++/unixodbc-dev | P1 |

---

## 5. 决策待定（OPEN-DECISIONS）

| 项 | 问题 | 影响 | 建议倾向 |
|----|------|------|----------|
| D-1 | 安装包目标平台优先级（Win/macOS/Linux） | 决定 P0-2 打包工具链与签名成本 | Windows 优先（用户环境为 Windows） |
| D-2 | i18n 是否扩展到日韩/ RTL | 决定语言包结构与 key 设计 | 中英双语起步，结构预留扩展 |
| D-3 | 自动更新走 GitHub Release 还是自建通道 | 决定更新服务架构 | GitHub Release 比对（零运维） |
| D-4 | 代码签名/公证预算 | 决定 SmartScreen/Gatekeeper 绕过成本 | 先 Windows 签名，macOS 后续 |

---

## 6. 变更记录

| 日期 | 变更内容 | 原因 | 影响范围 |
|------|----------|------|----------|
| 2026-08-14 | 初版路线图 | 基于全量代码评估落 Backlog | 全文档 |
| 2026-08-14 | 追加实施规格附录 | 把清单级 Backlog 补到可执行级（含 Dockerfile / eslint / CI diff / i18n / PyInstaller 骨架） | §7 |
| 2026-08-14 | **M2 补测试收口** | services/routes 覆盖率 16%→**67%**（实测 2661 stmts / 881 miss），新增 13 个单测文件（含 `services/routines` 94% + `routes/routines` 100%）；CI `--cov-fail-under` `15`→`60`（钉死防回退，shadow 测试全绿） | `tests/`、` .github/workflows/ci.yml` |

---

## 7. 实施规格附录（可直接落地）

> 本节把 §2 的清单补成"开发者可复制执行"的级别。P1 项为低风险快赢，P0 项给出基于建议默认值的骨架（标注待 D-x 决策）。

### 7.1 P1-6 Docker 运行时瘦身（替换 Dockerfile）

核心思路：新增 Python builder 阶段编译轮子，runtime 阶段只保留 `unixodbc`（无 `-dev`）与 `curl/gnupg`。

```dockerfile
# ---- 阶段1: 前端构建 ----
FROM node:20-alpine AS fe
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---- 阶段2: Python 依赖编译(builder) ----
FROM python:3.12-slim AS pybuilder
WORKDIR /build
# 编译型驱动(psycopg2/oracledb 等)需要 gcc/g++/unixodbc-dev —— 仅在此阶段
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc g++ unixodbc-dev curl gnupg \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip wheel --no-cache-dir -r requirements.txt -w /build/wheels

# ---- 阶段3: Python 运行时 ----
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    DBM_NO_OPEN=1
# 运行时只需 unixodbc(无 -dev) + curl(ODBC 脚本) + gnupg
RUN apt-get update && apt-get install -y --no-install-recommends \
        unixodbc curl gnupg \
    && rm -rf /var/lib/apt/lists/*
# 微软 ODBC Driver 18(按需, 不连 SQL Server 不影响启动)
RUN curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
# 从 builder 拷预编译 wheel, 离线安装(无需 gcc)
COPY --from=pybuilder /build/wheels ./wheels
RUN pip install --no-cache-dir --no-index ./wheels && rm -rf ./wheels
# 后端源码 / 分层 / 前端产物(同原结构)
COPY app.py config.py crypto.py dbcore.py handler.py ops.py store.py tunnel.py auth.py \
     logging_conf.py task_sched.py get_ipv6.py sqlitedb.py metrics.py \
     scanner.py handler_security.py ./
COPY services ./services
COPY routes ./routes
COPY --from=fe /fe/dist ./frontend/dist
RUN mkdir -p /app/data && chmod 777 /app/data
EXPOSE 8770
CMD ["python", "app.py"]
```

验收：`docker run --rm dbmanager python -c "import app; print('ok')"` 通过（ci.yml docker job 已覆盖）；`docker run --rm --entrypoint bash dbmanager -c "which gcc || echo NO_GCC"` 应输出 `NO_GCC`。

### 7.2 P1-3 前端 ESLint / Prettier

`frontend/package.json` 增量：

```json
{
  "scripts": {
    "lint": "eslint . --max-warnings 0",
    "format": "prettier --write \"src/**/*.{ts,vue}\""
  },
  "devDependencies": {
    "eslint": "^9.0.0",
    "eslint-plugin-vue": "^9.0.0",
    "@typescript-eslint/eslint-plugin": "^8.0.0",
    "@typescript-eslint/parser": "^8.0.0",
    "prettier": "^3.0.0",
    "eslint-config-prettier": "^9.0.0"
  }
}
```

`frontend/eslint.config.js`（ESLint 9 flat config）：

```js
import pluginVue from 'eslint-plugin-vue'
import tsParser from '@typescript-eslint/parser'
import tsPlugin from '@typescript-eslint/eslint-plugin'
import prettier from 'eslint-config-prettier'

export default [
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: { parser: tsParser, parserOptions: { ecmaVersion: 2022, sourceType: 'module' } },
    plugins: { '@typescript-eslint': tsPlugin },
    rules: {
      'vue/multi-word-component-names': 'off',
      '@typescript-eslint/no-explicit-any': 'warn'
    }
  },
  prettier
]
```

`frontend/.prettierrc.json`：`{ "semi": false, "singleQuote": true, "printWidth": 100 }`

CI `frontend` job 在 `npm run build` 前加：

```yaml
- name: Lint
  run: npm run lint
```

### 7.3 P1-4 mypy / ruff format 转阻断

收敛步骤（先不急着改 CI，避免误伤发版）：
1. 本地 `ruff format .` 全量对齐（CI 注释称当前 52 文件未对齐）；
2. 给 `routes/`、`services/` 补类型注解；
3. 确认 `mypy routes services scanner.py handler_security.py services/core.py config.py dbcore.py` 0 error；
4. 再移除 ci.yml 第 32、36 行的 `continue-on-error: true`，并将 mypy 文件清单扩到全量目标。

目标 CI 片段（收敛后）：

```yaml
- name: Format check (ruff format, 全量阻断)
  run: ruff format --check .
- name: Type check (mypy, 全量阻断)
  run: mypy routes services scanner.py handler_security.py services/core.py config.py dbcore.py
```

### 7.4 P1-5 测试覆盖率

`requirements.lock` 增 `pytest-cov`；CI `backend` job 单测步改为：

```yaml
- name: Unit tests (pytest + coverage)
  run: python -m pytest tests/ -q --cov=services --cov=routes --cov-report=xml --cov-fail-under=60
```

门槛从 60% 起步，M2 收口后逐里程碑抬升（如 70% → 80%）。可选接 Codecov 上传 `coverage.xml`。

### 7.5 P0-1 i18n 实施骨架（待 D-2 确认范围）

建议默认值：中英双语起步，结构预留日韩/RTL 扩展。

1. 安装：`cd frontend && npm i vue-i18n`
2. 装配 `frontend/src/locales/index.ts`：
   ```ts
   import { createI18n } from 'vue-i18n'
   import zhCN from './zh-CN'
   import enUS from './en-US'
   const saved = localStorage.getItem('dbm-lang') || 'zh-CN'
   export const i18n = createI18n({ legacy: false, locale: saved, fallbackLocale: 'en-US', messages: { 'zh-CN': zhCN, 'en-US': enUS } })
   ```
3. `main.ts` 注册 `app.use(i18n)`；语言切换组件接 ui store，写入 `localStorage('dbm-lang')` 并 `i18n.global.locale.value = lang`。
4. 抽离约 200 处：先用正则扫描定位硬编码中文 —— `rg -n "[\x{4e00}-\x{9fff}]+" frontend/src --glob '!locales/*'`，逐一定义 key（命名 `module.action.noun`，如 `login.title`）。
5. 模板改 `<h1>{{ $t('login.title') }}</h1>`；脚本改 `t('login.title')`。
6. CI 加 i18n 完整性：比对 `zh-CN`/`en-US` 的 key 集合，缺失即 fail。

### 7.6 P0-2 安装包 / 自动更新（待 D-1/D-3/D-4）

建议默认值：Windows 优先；自动更新走 GitHub Release 比对；签名预算后续定。

1. PyInstaller 单文件：
   ```bash
   pyinstaller --onefile --name dbmanager --hidden-import services --hidden-import routes ^
     --add-data "frontend/dist;frontend/dist" app.py
   ```
   需在 `.spec` 中收集 `services/`、`routes/` 全部模块与 `frontend/dist`。
2. Windows 安装器：Inno Setup（`.iss`）包裹 PyInstaller 产物 + 运行时；或 NSIS。
3. 自动更新（GitHub Release 比对）：
   - 启动请求 `https://api.github.com/repos/<owner>/dbmanager/releases/latest` 取 `tag_name`；
   - 与本地 `version` 比对，新则下载对应 asset，校验 sha256，静默替换并重启；
   - 失败回滚到上一可用版本。
4. 代码签名（D-4）：Windows 建议对 `.exe` 做签名绕 SmartScreen；macOS 后续做 `.pkg` + Gatekeeper 公证。

---

## 8. 执行顺序建议（落地节奏）

1. **M0**：先落 7.1（Docker 瘦身）+ P1-7（.bak→.gitignore）—— 低风险、半天出成果。
2. **M2 并行**：7.2（前端 lint）+ 7.3（后端门禁收敛）+ 7.4（覆盖率）—— 同一里程碑收口工程化。
3. **M1**：待 D-1/D-2/D-3 确认后并行推 7.5（i18n）+ 7.6（安装包）。
4. **M3/M4**：按需捡 P2/P3。

> 下一步：确认 4 项决策（或采纳建议默认值）即可解锁 P0；P1 四项无需决策，可立即开工。
