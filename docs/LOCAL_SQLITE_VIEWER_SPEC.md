# 本地 SQLite 文件加载与查看功能 — 方案文档

> 状态：待评审（v1 方案）
> 路线决策：纯浏览器 **sql.js（WASM）**，非"上传到后端"
> 作者：MVP 开发专家团（架构视角）

---

## 1. 背景与目标

### 1.1 现状（已基于代码核实）
- 现有 SQLite 连接靠用户**手填"服务器侧文件路径"**打开：`frontend/src/layouts/ConnPanel.vue:243` 的 `sqlitePath` 输入框 → 后端 `sqlite3.connect()` 打开。
- 前端**没有任何 `<input type="file">`**，所有连接均为"填参数"式。
- 全仓**没有文件上传端点**（搜 `UploadFile` / `multipart` 仅命中 `node_modules` 与 `client.ts` 的通用 body 处理）。
- 后端已具备只读打开模式（`server/handler.py` 的 `_conn_readonly_blocked()` / `WRITE_PATHS`），但那是服务端路径场景，与"浏览器挑本地文件"无关。

### 1.2 目标
让浏览器用户通过**文件选择器**直接打开本机 `.db` / `.sqlite` / `.sqlite3` 文件，并浏览表结构、翻看数据、执行只读 SQL —— 体验显著优于手填路径。

### 1.3 非目标（v1 不做）
- 不把文件**写回原路径**（浏览器也拿不到原路径，且安全上不鼓励）。
- 不纳入后端"已保存连接"体系（sql.js 库是会话内内存态，不适合持久化为连接配置）。
- 不做跨库 JOIN / 多文件联合查询。

---

## 2. 方案选型结论

| 维度 | A. 上传字节→后端打开 | B. 纯浏览器 sql.js（**选定**） |
|------|----------------------|-------------------------------|
| 服务端信任 | 需后端处理不可信字节 | 无，文件不出浏览器 |
| 离线 / 隐私 | 文件上送服务端 | 文件仅留本机内存 |
| 远程部署可用 | 是 | 否（仅本机浏览器） |
| 显示层复用 | 直接复用后端绑定组件 | 需前端自行承接显示 |
| 工作量 | 中（新增上传端点 + 解析） | 中（WASM 资源 + 本地 provider） |

**选 B 的理由**：dbmanager 本身是本机工具，`sql.js` 把 SQLite 编译进 WASM，文件完全在浏览器内打开，零服务端信任、可离线、隐私最好；代价（显示层需前端承接）已在第 4–5 节设计内消化。用户明确选择此路线。

---

## 3. 架构与数据流

```
[浏览器]
<input type="file" accept=".db,.sqlite,.sqlite3">
        │  FileReader / arrayBuffer()
        ▼
LocalDbStore (Pinia) ──加载──▶ sql.js: new SQL.Database(Uint8Array)
        │                              │
        │  listTables()                │  db.exec / db.prepare
        │  getSchema(table)            │
        │  query(sql,{limit,offset})   │
        │  exportBytes()               │
        ▼                              │
LocalDbViewer.vue
   ├─ 表树（左）  ◀── listTables / getSchema
   ├─ DataGrid（右，复用） ◀── query()
   └─ SQL 框 + 执行 + 导出 ◀── query / exportBytes
```

- **文件字节永不离开浏览器**：不上传、不落服务端磁盘。
- 打开后是**内存态数据库**；任何写操作只影响内存副本，原文件不变。

---

## 4. 数据 / 接口抽象

新增 `LocalDbStore`（Pinia，沿用 `frontend/src/stores/ui.ts` 风格）封装 sql.js，对外暴露：

```ts
interface LocalDbStore {
  loaded: boolean
  fileName: string
  load(bytes: Uint8Array, name: string): void          // 打开，内部校验魔数 + try/catch
  listTables(): { name: string; type: string; sql: string }[]
  getSchema(table: string): { name: string; type: string; notnull: boolean; pk: boolean }[]
  rowCount(table: string): number
  query(sql: string, opts?: { limit?: number; offset?: number }):
        { columns: string[]; rows: any[][]; truncated: boolean }
  exportBytes(): Uint8Array                                // 导出内存副本供下载
  close(): void
}
```

**复用策略（两档）**：
- **MVP（推荐先做）**：`LocalDbViewer.vue` 内部直接用 `LocalDbStore`，不强行重构现有后端绑定组件（`ObjectTree`/`DataGrid`/`SqlWorkbench` 目前都通过 `api/client.ts` 调后端）。风险最低、交付最快。
- **v2 统一（后续）**：定义 `QueryProvider` 接口，`BackendProvider`（现有）与 `LocalSqlJsProvider`（新）双实现，让同一套 UI 绑定「当前 provider」。实现成本低但牵涉面广，留作后续。

---

## 5. 前端改动清单

| 类型 | 文件 | 说明 |
|------|------|------|
| 依赖 | `frontend/package.json` | 增加 `sql.js` |
| 构建 | `frontend/vite.config.ts` | 处理 `sql-wasm.wasm` 资源：`locateFile` 指向 `/sql-wasm.wasm`（由 Vite 复制到 `dist`），或用 `?url` 导入 |
| 新增 | `frontend/src/stores/localDb.ts` | 封装 sql.js，实现第 4 节接口 + 单测 |
| 新增 | `frontend/src/components/LocalDbViewer.vue` | 文件选择 + 表树 + 复用 `DataGrid.vue` + SQL 框 + 导出；加载/错误/空态齐全 |
| 改 | `frontend/src/layouts/ConnPanel.vue` | 连接区增加「打开本地数据库」入口，点击打开 `LocalDbViewer`（模态或独立视图） |
| 改 | `frontend/src/components/DataGrid.vue`（可能） | 确认 props 形态（`{columns, rows}`）与 `query()` 输出对齐；必要时加轻量适配层 |
| 改 | `locales/zh-CN.json` / `locales/en.json` | 新增 `conn.openLocal` / `localDb.*` 文案（沿用现有 `tr()` 机制） |

**后端改动：无。** sql.js 为纯前端 WASM；WASM 资源由 Vite 在构建期产出并由前端静态托管，`app.py` / `server/` 无需改动。

---

## 6. 安全与限制（必做）

1. **魔数校验**：打开前检查字节头是否为 `SQLite format 3\000`，否则拒绝并提示「不是有效的 SQLite 文件」。
2. **异常兜底**：`new SQL.Database()` 与每次查询均 `try/catch`；损坏 / 加密 / 版本不支持的文件给出友好报错，**不崩页面**。
3. **体积上限**：默认 `200MB`（可配）。超出弹确认框，避免 WASM 堆 OOM 拖垮标签页。
4. **只读浏览默认**：SQL 框仅允许 `SELECT` / `PRAGMA` / `EXPLAIN` 类只读语句；若用户执行写语句，明确提示「仅影响内存副本，原文件不会被修改」，并引导用「导出」保存。
5. **隐私**：文件不离开浏览器，无上传、无日志落盘。

---

## 7. 大结果集与性能

- `query()` 用 `db.prepare(sql)` + `stmt.step()` + `stmt.getAsObject()` **分页取数**，避免 `db.exec()` 一次性把全表拉进内存。
- 配合 `DataGrid` 已有分页 / 虚拟滚动（沿用），大表只取当前页数据。
- `listTables()` / `getSchema()` 走 `sqlite_master`，开销极小。

---

## 8. 测试

- **单测** `localDb.ts`：用 fixture `.db`（或 sql.js 现场建库后 `exportBytes()` 生成字节）验证 `listTables` / `getSchema` / `query` 分页 / `rowCount` / `exportBytes`；并验证魔数校验拒绝非 SQLite 字节。
- **组件测** `LocalDbViewer.vue`：挂载 + fixture，断言表树渲染、网格出数据、SQL 执行出结果、导出触发下载。
- **手动 e2e**：打开一个真实 `.db`，走通「选择文件 → 看表 → 翻页 → 跑 SQL → 导出」全流程。

---

## 9. 改动文件汇总

新增：
- `frontend/src/stores/localDb.ts`
- `frontend/src/components/LocalDbViewer.vue`
- `docs/LOCAL_SQLITE_VIEWER_SPEC.md`（本文件）

修改：
- `frontend/package.json`、`frontend/vite.config.ts`
- `frontend/src/layouts/ConnPanel.vue`
- `frontend/src/components/DataGrid.vue`（按需 props 对齐）
- `locales/zh-CN.json`、`locales/en.json`

后端：无

---

## 10. 风险与后续

- **WASM 大文件 OOM**：以体积上限 + 分页取数缓解；超大库建议仍走现有「服务器侧路径」SQLite 连接。
- **与后端绑定组件的统一**：`QueryProvider` 抽象留 v2，避免首版过度重构。
- **原地写回原文件（可选 v2）**：Chromium 下可用 File System Access API（`showSaveFilePicker`）支持「保存回原文件」，需用户手势且仅 Chromium，作为可选增强。

---

## 11. 实施步骤（建议顺序）

1. 装 `sql.js` + 打通 Vite 的 `sql-wasm.wasm` 资源（先跑通 hello world：打开 fixture 打印表名）。
2. 实现 `LocalDbStore` 接口 + 单测。
3. `LocalDbViewer` 骨架：文件选择 + 表树 + 复用 `DataGrid`。
4. SQL 执行 + 分页 + 导出下载。
5. `ConnPanel` 入口 + i18n 文案。
6. 组件测试 + 手动验证；`vitest --run` 与 `vite build` 绿灯。

---

## 12. 验收标准（Definition of Done）

- [ ] 浏览器文件选择器可打开 `.db/.sqlite/.sqlite3`。
- [ ] 表树、表结构、分页数据正常显示，复用既有 `DataGrid` 视觉。
- [ ] 只读 SQL 可执行并出结果；写语句有安全提示。
- [ ] 非 SQLite / 损坏文件有友好报错，页面不崩。
- [ ] 「导出」可下载内存副本为 `.db`。
- [ ] 单测 + 组件测通过，`vite build` 成功。
- [ ] 中英文文案齐备。
