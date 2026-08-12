# dbmanager 前端 Vue3 迁移方案（精简版 · v2 修正）

> 本文档为**迁移方案设计**，不含代码改动。落地时按阶段分多轮执行，每轮产出可验证的增量。
>
> **决策已定**：① 分阶段推进，不一次性全量重写；② SQL 编辑器用 CodeMirror 6（非 Monaco）；③ 不引入框架级 UI 库（Element Plus/Naive UI 都不要），组件手写。
>
> **v2 修正（基于批判性复核）**：
> - CodeMirror 依赖：`codemirror` 元包不含 SQL 语言和补全，必须单独装 `@codemirror/lang-sql`/`@codemirror/autocomplete` 等 6 个拆分包（依赖总数 7→13，体积结论不变）
> - 路由模式：用 `createWebHashHistory`（hash 模式），避免刷新 `/v2/main` 后端 404
> - 工程目录：Vue 工程放 `frontend/` 子目录，避免覆盖旧 `index.html` 导致旧前端入口消失
> - 后端静态服务：不动 `STATIC_DIRS` 白名单，新增 `/v2` 入口从 `frontend/dist/` 读
> - 体积预估修正：~400-500KB gzip（非 300KB），仍比 Monaco 版省 75%+
> - 样式：现有 `css/style.css` 是 CSS 变量 + `[data-theme]` 体系，原样搬进 Vue 当全局样式，主题切换零成本

---

## 一、目标与约束

### 目标
将现有原生 JS 前端（5 文件、~4500 行、全局函数 + 20+ 跨文件全局变量）迁移到 **Vue 3 + Vite + Pinia + TypeScript**，最终产物为 Vite 构建的**纯静态文件**（`dist/` 目录），由现有 Python `http.server` 后端直接 serve，**不引入 Node 运行时到生产部署**。

### 硬约束
1. **后端不动**：Python `http.server` + `handler.py` 的 API 契约保持不变，Vue 应用作为静态客户端对接。
2. **纯静态产物**：`npm run build` 产出 `dist/`，部署时只拷贝 `dist/`，不跑 `npm run dev`/SSR。
3. **零外网依赖**：保持自托管特性，CodeMirror 和所有依赖走本地打包，不引 CDN。
4. **功能对等**：迁移期间旧前端保持可用，新旧可并存（后端 serve 两套入口），逐功能切换。
5. **依赖最小化**：只装必要项，不引框架级 UI 库。

### 非目标
- 不改后端 API。
- 不改数据库连接/加密/隧道逻辑（这些在后端，与前端无关）。
- 不做 SSR/SSG——这是 Web 工具不是内容站。

---

## 二、技术栈选型（精简）

| 层 | 选型 | 体积(gzip) | 理由 |
|----|------|-----------|------|
| 框架 | Vue 3（Composition API + `<script setup>`） | ~45KB | 现代响应式，生态成熟 |
| 构建 | Vite 5 | — | 产物纯静态，HMR 快，配置极简 |
| 语言 | TypeScript | — | 20+ 全局变量耦合严重，类型约束能显著降风险 |
| 状态 | Pinia | ~8KB | Vue3 官方推荐，store 拆分天然契合现有状态分布 |
| 路由 | Vue Router 4 | ~15KB | 单页应用，连接面板/主界面/各弹窗路由化 |
| SQL 编辑器 | **CodeMirror 6（拆分包）** | **~60KB** | 体积仅 Monaco 的 1/30，SQL 高亮+补全+折叠全有 |
| 虚拟滚动 | `vue-virtual-scroller` | ~5KB | 大表性能必需 |
| HTTP | **原生 fetch + composable** | 0 | 不引 axios，手写 30 行拦截器 composable |
| UI 组件 | **手写** | 0 | DBA 工具 UI 就树/表格/弹窗/分页几样，手写不费事 |
| 包管理 | pnpm | — | 体积小、快 |

### 依赖清单（13 个：7 依赖 + 3 dev + 3 codemirror 拆分包）

> ⚠️ `codemirror` 元包**不含** SQL 语言和补全，必须单独装 `@codemirror/lang-sql`、`@codemirror/autocomplete` 等。按元包执行会装出**没有 SQL 高亮和补全**的编辑器。

```
dependencies:
  vue  vue-router  pinia  vue-virtual-scroller
  codemirror  @codemirror/state  @codemirror/view  @codemirror/commands
  @codemirror/language  @codemirror/autocomplete  @codemirror/lang-sql

devDependencies:
  vite  typescript  @vitejs/plugin-vue
```

### 体积预估
- Vue+Pinia+Router ≈ 68KB gzip
- CodeMirror 6（仅 sql 语言包 + autocompletion + view/state/commands/language）≈ 50-70KB gzip
- vue-virtual-scroller ≈ 5KB gzip
- 业务代码（现有 4500 行含表设计器/导入/ER/虚拟滚动，迁移后 min 约 200-300KB）gzip ≈ 60-90KB
- **总计 ≈ 400-500KB gzip**（对比旧方案 Monaco 版 2.2MB，**省 75%+**）
- **合理目标：总 < 500KB gzip**，仍在 Monaco 版 1/4 以内

### 为什么砍掉这些
| 砍掉 | 原因 |
|------|------|
| ~~monaco-editor~~ | 2MB gzip 对内网工具过度配置，90% 功能（多光标/minimap/断点）DBA 用不上 |
| ~~@guolao/vue-monaco-editor~~ | Monaco 的 Vue 封装，随 Monaco 一起砍 |
| ~~element-plus~~ | 200KB 全量、表格/树/弹窗手写不费事，避免组件库样式定制成本 |
| ~~axios~~ | 原生 fetch + composable 30 行搞定，省 13KB + 一层抽象 |
| ~~@vueuse/core~~ | 手写几个 composable 即可，省 40KB |

### 为什么是 CodeMirror 6 而不是 Monaco
| 维度 | CodeMirror 6 | Monaco |
|------|-------------|--------|
| gzip 体积 | ~80KB | ~2MB |
| 运行时内存 | 单实例 ~5MB | 单实例 30-50MB |
| SQL 语法高亮 | ✅ 内置 | ✅ 内置 |
| 自动补全 | ✅ `@codemirror/autocomplete` | ✅ |
| 代码折叠 | ✅ | ✅ |
| 多光标/minimap | ❌ | ✅（但 DBA 用不上） |
| 首屏加载 | 快（可不放首屏） | 慢（必须懒加载） |
| Vite 集成 | 原生 ESM，零配置 | 需 worker 配置 |

**结论**：CodeMirror 6 是 DBA 工具的"刚好够用"档，Monaco 是过度配置。

---

## 三、现状分析（迁移基线）

| 维度 | 现状 | 迁移影响 |
|------|------|----------|
| 模块化 | 无，5 文件按 `<script>` 顺序加载，全挂 `window` | 全部改 ES Module + 组件 |
| 状态管理 | `store.js` 25 行发布-订阅 + 20+ 全局变量散落各文件 | 收敛到 Pinia stores |
| DOM 生成 | 大量 `innerHTML` 字符串拼接 + 内联 `onclick="func('${escAttr(...)}')"` | 改 Vue 模板 + 事件绑定 |
| SQL 编辑器 | 自绘 `<textarea>` + `<pre>` 叠加高亮 + 补全下拉（~600 行） | 换 CodeMirror 6 |
| 虚拟滚动 | 手写固定行高 32px + 占位行 | 用 `vue-virtual-scroller` |
| 列宽拖拽 | 手写 mousedown/mousemove + localStorage 记忆（~150 行） | 封装为可复用指令/组件 |
| 模态框 | 单个 `#modal` 容器，`showModal(html)` 注入 innerHTML | 拆为独立组件 + Teleport |
| fetch 拦截 | monkey-patch `window.fetch` 注入 token + 处理 401 | 改 composable（不引 axios） |
| 第三方依赖 | 零 | 新增 7 个（全部打包，无 CDN） |
| 后端静态服务 | `STATIC_DIRS` 白名单：仅 `/css/` `/js/` 两个扁平目录，拒 `..` 和子目录 | **需适配 Vite 产物结构**（见第六章） |

---

## 四、组件拆分设计

基于现状调研，目标组件树（`#` 标注的是首轮地基要落的空壳，其余后续按阶段填充）：

```
App.vue                        # 根：布局壳子，条件渲染 ConnPanel / MainLayout
├── # AppHeader.vue            # 顶栏：dbinfo / viewSwitch / auth / theme / tx / stop
├── # ConnPanel.vue           # 连接表单 + Navicat 快速连接 + 我的连接入口
├── MainLayout.vue            # flex 容器，条件渲染 browse/sql 两视图
│   ├── # SidePanel.vue       # 左侧栏容器
│   │   ├── SideConns.vue     #   我的连接列表
│   │   └── ObjectTree.vue    #   Navicat 风格树：库→schema→类型分组（手写递归组件）
│   ├── BrowseView.vue        # 数据浏览主区
│   │   ├── # DocTabs.vue     #   多文档标签
│   │   ├── # Toolbar.vue     #   操作栏（刷新/新增/导出/筛选等）
│   │   ├── DataGrid.vue      #   表格+虚拟滚动+行选中+列宽拖拽
│   │   ├── StructPanel.vue   #   结构视图：字段/索引表
│   │   ├── StatBar.vue       #   统计栏
│   │   └── Pager.vue         #   分页
│   ├── SqlWorkbench.vue      # SQL 工作台
│   │   ├── SqlEditor.vue    #   CodeMirror 6 编辑器
│   │   ├── ProcBar.vue       #   存储过程编辑横幅
│   │   ├── SqlResultTabs.vue #   多查询结果 tab
│   │   └── SqlHistory.vue    #   历史/收藏面板
│   └── # PropsPanel.vue      # 右侧属性面板
├── # StatusBar.vue           # 底部状态条
├── Modals/                   # Teleport 弹窗
│   ├── # ConnMgrModal.vue   # 连接管理
│   ├── # AuthModal.vue      # 登录/注册
│   ├── # GatewayModal.vue   # 网关验证
│   ├── AlterTableModal.vue  # 表设计器（字段/索引/外键/触发器）
│   ├── ImportModal.vue      # 导入 CSV/XLSX/粘贴
│   ├── SchemaDiffModal.vue  # 结构对比/同步
│   └── GenericModal.vue     # 通用 showModal 替代
├── ContextMenu.vue          # 右键菜单
├── FilterPopup.vue         # 列筛选弹窗
└── # Toast.vue             # 消息提示
```

### 手写组件说明（不引 UI 库的底气）
| 组件 | 手写成本 | 备注 |
|------|---------|------|
| 树（ObjectTree） | 中 | 递归组件 + 懒加载，~80 行 |
| 表格（DataGrid） | 高 | 已有手写虚拟滚动基础，封装成组件 + `vue-virtual-scroller` |
| 弹窗（Modals） | 低 | `<Teleport>` + `v-if`，每个 ~30 行 |
| 分页（Pager） | 低 | 计算页码数组，~40 行 |
| 右键菜单 | 低 | 绝对定位 + `v-if`，~30 行 |
| Toast | 低 | 数组队列 + `TransitionGroup`，~30 行 |

**结论**：除 DataGrid 外都是低成本，手写完全可行，省掉 Element Plus 200KB。

### Pinia Store 拆分

| Store | 收敛的全局变量 | 职责 |
|-------|---------------|------|
| `useConnectionStore` | `API` `CONN` `SESSION` `PUB_KEY` `CONN_LIST` `DEFAULT_CONN` | 连接建立/断开、Session 管理、RSA 公钥获取、连接列表 CRUD |
| `useAuthStore` | `USER_TOKEN` `ROLE` `NAME` | 登录/注册/改密、角色权限判断、token 持久化(localStorage) |
| `useDatabaseStore` | `TABLES` `FULL_TABLES` `DBS` `curDb` `ROUTINES` | 切库、树数据、表/存储过程列表 |
| `useTabStore` | `TABS` `activeId` `tabSeq` `current` `currentMeta` `currentPage` | 多文档标签 CRUD、当前表/页码/元数据 |
| `useGridStore` | `curSort` `filters` `selectedRows` `lastSelIdx` `editingCell` `currentTab` | 网格状态：排序/筛选/选中/编辑 |
| `useSqlStore` | `SQL_TABS` `SQL_ACTIVE` `writeMode` `SQL历史` `SQL收藏` | SQL 工作台状态、结果 tab、写模式 |
| `useUIStore` | `theme` `transactionMode` | 主题、事务模式、toast/modal/ctxMenu 等 UI 状态 |

---

## 五、API 调用契约（前端→后端）

### 请求头约定
| 头 | 用途 | 注入位置 |
|----|------|---------|
| `X-Session` | 服务端会话 token（优先） | fetch 拦截 composable |
| `X-Conn` | Base64 编码的连接 JSON（回退，含 RSA 加密密码） | fetch 拦截 composable |
| `X-User-Token` | 账号登录 token | fetch 拦截 composable |
| `X-Gateway-Token` | 公网访问令牌 | fetch 拦截 composable |

### API 分组
**连接/配置**：`GET /api/config` · `GET /api/pubkey` · `POST /api/connect` · `POST /api/test` · `POST /api/databases` · `POST /api/shutdown`

**连接管理**：`GET /api/connections` · `POST /api/connections` · `POST /api/connections/delete`

**表结构/元数据**：`GET /api/tables` · `GET /api/columns?s=&t=` · `GET /api/indexes?s=&t=` · `GET /api/relations?s=&t=` · `GET /api/er?s=&t=` · `POST /api/objects` · `GET /api/routines` · `GET /api/routine/source?s=&name=&kind=` · `GET /api/routine/params?s=&name=&kind=`

**数据 CRUD**：`GET /api/data?s=&t=&page=&size=&where=&order=` · `POST /api/row` · `PUT /api/row` · `DELETE /api/row` · `POST /api/stats`

**SQL**：`POST /api/sql`（支持 write 模式）· `POST /api/explain`

**导入导出**：`GET /api/export?s=&t=&where=&fmt=` · `GET /api/export/schema` · `POST /api/export/sql` · `POST /api/import` · `POST /api/import/xlsx` · `GET /api/backup` · `POST /api/restore`

**结构变更/同步**：`POST /api/alter` · `POST /api/sync` · `POST /api/transfer` · `POST /api/schema/diff` · `POST /api/schema/sync` · `POST /api/gen-data`

**存储过程**：`POST /api/routine/save` · `POST /api/routine/drop` · `POST /api/routine/execute`

**事务**：`POST /api/transaction/commit` · `POST /api/transaction/rollback`

**账号体系**：`POST /api/login` · `POST /api/register` · `POST /api/password` · `GET /api/users` · `POST /api/users` · `POST /api/users/delete` · `POST /api/gateway/login`

---

## 六、工程目录布局 + 路由模式（隐藏坑修正）

### 6.1 Vite 工程不能放项目根
现有 `index.html`（原生 JS 版）在项目根，由后端 `GET /` serve。若 Vite 的 `index.html` 也放根目录，**会覆盖后端 serve 的原生版 index.html，旧前端入口当场消失**。

**方案**：Vue 工程放 `frontend/` 子目录，产物 `frontend/dist/`。
```
dbmanager/
├── app.py  config.py  handler.py  ...   # 后端(不动)
├── index.html  css/  js/               # 旧前端(并存到阶段6下线)
└── frontend/                           # Vue 工程根
    ├── package.json  vite.config.ts  tsconfig.json
    ├── index.html                      # Vite 入口(在 frontend/ 下, 不碰根 index.html)
    ├── src/
    │   ├── main.ts  App.vue
    │   ├── router/  api/  stores/  components/  layouts/
    │   └── assets/
    │       └── styles.css              # 现有 css/style.css 原样搬进来(见 6.3)
    └── dist/                           # build 产物(后端 serve 这里)
        ├── index.html
        └── assets/
            ├── index-abc123.js
            └── index-def456.css
```

### 6.2 路由模式必须用 hash（不能 history）
路由是 `/main`、入口是 `/v2`。若用 `createWebHistory`（history 模式），刷新 `http://x/v2/main` 后端会 **404**——后端只 serve 了 `/v2` 一个入口，没有 `/v2/main` 的通配处理。

**方案**：用 `createWebHashHistory`（hash 模式）。
```ts
// src/router/index.ts
import { createRouter, createWebHashHistory } from 'vue-router'
const router = createRouter({
  history: createWebHashHistory(),   // hash 模式: /v2/#/main, 后端零改动
  routes: [/* ... */]
})
```
- URL 形如 `http://x:8770/v2#/main`，刷新后端只看到 `/v2`，返回 `dist/index.html`，前端路由自行解析 `#/main`。
- 后端零改动，一个入口够用。

### 6.3 样式直接搬现有 CSS（零成本主题）
现有 `css/style.css` 已是 CSS 变量 + `[data-theme="dark"]` 体系（`--bg/--panel/--border/--primary` 等，深浅主题靠 `body[data-theme]` 切换）。**迁移时原样搬进 `frontend/src/assets/styles.css` 当全局样式**，主题切换零成本，不用重写。这能省下阶段 6 不少工作量。

```ts
// main.ts
import './assets/styles.css'   // 原样搬, 不改
```
Vue 组件内的 scoped 样式可复用这些变量（`color: var(--text)`），深浅主题随 `useUIStore.theme` 切换 `body[data-theme]` 即可。

---

## 七、后端静态资源服务适配（关键对接点）

### 问题
现有 `config.py:22-25` 的 `STATIC_DIRS` 白名单只认 `/css/` 和 `/js/` 两个扁平目录，且 `handler.py:314-328` 显式拒绝 `..` 和子目录（`/` 和 `\\` 都拒）。Vue 产物在 `frontend/dist/assets/` 下（带哈希、子目录），**现有白名单 serve 不到，且路径是 frontend/dist/ 不是 BASE_DIR**。

### 方案：新增 `/v2` 入口 + `/assets/` 路由从 frontend/dist/ 读
**后端只做这一处小改**（属地基阶段，不算改后端 API）：

1. `handler.py` 新增 `/v2` 入口分流：
   - `GET /v2` → 返回 `frontend/dist/index.html`
   - `GET /v2/assets/xxx` → 从 `frontend/dist/assets/` 读扁平哈希文件（拒 `..`）
2. **不动 `STATIC_DIRS` 白名单**（那是旧前端的 `/css/` `/js/`，别混进来）。新增独立的 `/v2/assets/` 处理分支，显式指向 `frontend/dist/assets/`。
3. `handler.py` 静态资源分支放宽规则：`/v2/assets/` 下允许单层文件名（Vite 产物是扁平哈希文件，无深层嵌套），仍拒 `..`。
4. 旧入口 `GET /` → 现有 `index.html`，两套前端并存。

### Vite 构建配置
```ts
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
export default defineConfig({
  base: './',              // 相对路径产物, /v2/ 子路径也能跑
  build: {
    outDir: 'dist',
    assetsDir: 'assets',   // 统一放 assets/, 对齐后端 /v2/assets/ 路由
  },
  plugins: [vue()],
  server: {
    proxy: { '/api': 'http://127.0.0.1:8770' }   // 开发时转发到后端
  }
})
```

### 开发模式
- `pnpm dev`（在 `frontend/` 下）起 Vite dev server（5173），proxy 把 `/api` 转发到 `http://127.0.0.1:8770`（现有后端）。
- 开发时前端跑 5173、后端跑 8770，CORS 已由 `handler.py:_origin_allowed` 处理（内网放行）。
- 生产部署只跑后端 8770，serve `frontend/dist/` 静态文件。

---

## 八、CodeMirror 6 集成要点

### 替换范围
- 删除 `js/sql.js` 中约 600 行自绘编辑器逻辑（textarea + pre 叠加高亮、补全下拉、滚动同步、Tab/方向键处理）
- 用 CodeMirror 6 封装 `<SqlEditor v-model="sql" />` 组件

### 最小依赖
```
codemirror              # 核心 + 基础命令
@codemirror/language    # 语法树
@codemirror/autocomplete # 补全
@codemirror/view        # 视图层
@codemirror/state       # 状态管理
@codemirror/commands     # 快捷键
@codemirror/lang-sql    # SQL 语言包（高亮 + 基础补全）
```

### 关键配置
```ts
// SqlEditor.vue
import { EditorView, keymap } from '@codemirror/view'
import { defaultKeymap, historyKeymap } from '@codemirror/commands'
import { autocompletion } from '@codemirror/autocomplete'
import { sql } from '@codemirror/lang-sql'
import { EditorState } from '@codemirror/state'

// 语言: SQL（dialect 可按当前连接 db_type 切 mysql/mssql/postgresql）
// 主题: 随 useUIStore.theme 切换（亮色/暗色，用 @codemirror/view 的 theme 扩展）
// 补全: sql() 自带关键字补全，叠加自定义补全源
//   数据源 = useDatabaseStore().TABLES + 当前表 currentMeta.columns
//   用 autocompletion({ override: [tableCompletions, columnCompletions] })
// 快捷键: Cmd/Ctrl+Enter 执行（keymap 注册，emit 事件给父组件）
```

### 主题切换
CodeMirror 6 用 `EditorView.theme()` 写一份亮色、一份暗色扩展，随 `useUIStore.theme` 用 `Compartment` 动态切换，不重载编辑器。

### 对比自绘编辑器的收益
| 维度 | 自绘 textarea+pre | CodeMirror 6 |
|------|------------------|---------------|
| 代码量 | ~600 行 | ~60 行（组件）+ 配置 |
| 语法高亮 | 手写正则，易漏 | 官方 lang-sql，覆盖完整 |
| 补全 | 手写下拉 + 方向键 | 官方 autocomplete，含模糊匹配 |
| 滚动同步 | 手写 | 内置 |
| 撤销/重做 | 无 | 内置 history |
| 代码折叠 | 无 | 内置 |

---

## 九、分阶段落地路线

### 阶段 0：地基（首轮，本轮若执行只做这步）
**产出**：Vue3+Vite 工程骨架 + 空壳能连后端跑通。

- [ ] `package.json` + `pnpm install`（在 `frontend/` 下）：vue, vue-router, pinia, vue-virtual-scroller, codemirror, @codemirror/state, @codemirror/view, @codemirror/commands, @codemirror/language, @codemirror/autocomplete, @codemirror/lang-sql, vite, typescript, @vitejs/plugin-vue
- [ ] `vite.config.ts`（base='./', assetsDir='assets', proxy /api → 8770）
- [ ] `tsconfig.json`
- [ ] `src/main.ts`：挂载 App + 装 Pinia + Router
- [ ] `src/App.vue`：根布局，`<RouterView>`
- [ ] `src/router/index.ts`：路由表（`/` 连接面板、`/main` 主界面，**用 `createWebHashHistory`**）
- [ ] `src/api/client.ts`：原生 fetch 封装 + 拦截器 composable（注入 X-Session/X-User-Token/X-Gateway-Token + 401 处理 + RSA 加密密码）
- [ ] `src/api/` 下按模块分文件：`connection.ts` `database.ts` `data.ts` `sql.ts` `schema.ts` `routine.ts` `account.ts`（覆盖第五章 API 契约）
- [ ] `src/stores/` 7 个 store 骨架文件（只定义 state + actions 签名，逻辑留空）
- [ ] `src/layouts/` + `src/components/` 空壳组件（只 `<template><div>占位</div></template>`）
- [ ] `src/assets/styles.css`：从现有 `css/style.css` 原样搬（复用 CSS 变量 + `[data-theme]` 主题）
- [ ] 后端 `handler.py` 新增 `/v2` 入口 + `/v2/assets/` 从 `frontend/dist/assets/` 读（不动 `STATIC_DIRS`）
- [ ] `pnpm build` 产出 `frontend/dist/`，`python app.py` 后访问 `/v2` 加载到 Vue 空壳页（验证链路通）

**验证标准**：`pnpm build` 产出 `frontend/dist/`（~400-500KB gzip），`python app.py` 后访问 `/v2` 加载到 Vue 应用，fetch 能调通 `/api/config` 和 `/api/pubkey`，控制台无报错。

### 阶段 1：连接与认证
- `ConnPanel.vue`：连接表单、Navicat 快速连接、测试连接、建立连接（RSA 加密密码）
- `AuthModal.vue`：登录/注册/改密
- `GatewayModal.vue`：公网网关验证
- `useConnectionStore` + `useAuthStore` 完整实现
- 路由守卫：未连接 → 跳 `/`

**验证**：能从 Vue 端连上一个真实数据库，进入主界面（空）。

### 阶段 2：主框架 + 树
- `MainLayout.vue` + `SidePanel.vue` + `ObjectTree.vue`（手写递归树组件，懒加载库/schema/表/routines）
- `DocTabs.vue` 多文档标签
- `StatusBar.vue`
- `useDatabaseStore` + `useTabStore`

**验证**：树能展开到表，双击表打开新 tab（内容区暂空）。

### 阶段 3：数据网格（最难）
- `DataGrid.vue`：`vue-virtual-scroller` 虚拟滚动、行选中（Ctrl/Shift）、单元格编辑、右键菜单
- `Toolbar.vue` + `Pager.vue` + `StatBar.vue`
- 列宽拖拽封装为 `v-resizable-col` 指令 + localStorage 记忆
- `useGridStore`
- `ContextMenu.vue` + `FilterPopup.vue`

**验证**：分页浏览、排序、筛选、增删改、导出全部可用。

### 阶段 4：SQL 工作台
- `SqlEditor.vue`：集成 CodeMirror 6，配置 SQL 语法、补全源（从 `useDatabaseStore` 取表/列名）
- `SqlResultTabs.vue`：多结果 tab、EXPLAIN 树/表渲染
- `SqlHistory.vue`：历史/收藏（localStorage）
- 写模式开关、事务包裹
- `useSqlStore`

**验证**：SQL 执行、只读/写双模式、EXPLAIN、历史收藏、补全可用。

### 阶段 5：高级功能弹窗（手写 UI 里最重的三个，分批迁移逐个验证）
> ⚠️ 表设计器（现约 300 行）、导入列映射、结构同步是手写 UI 里最重的三个，建议**按弹窗逐个迁移、逐个验证**，别和 ER 图挤一轮。

- 5a：`AlterTableModal.vue` 表设计器（字段/索引/外键/触发器/SQL 预览）
- 5b：`ImportModal.vue` 导入（CSV/XLSX/粘贴 + 列映射）
- 5c：`SchemaDiffModal.vue` 结构对比/同步
- 5d：存储过程编辑/执行/删除 + 备份/还原
- 5e：数据同步、ER 图（保持手绘 SVG，不引图库）

### 阶段 6：收尾
- 全局快捷键（手写 `useKeyboard` composable，20 行搞定）
- 深浅主题切换（CSS 变量 + `useUIStore.theme`）
- 旧 `index.html` 下线，`/v2` 改为 `/`
- `Dockerfile` 更新：构建期 `pnpm build`，运行期只 serve `dist/`

---

## 十、风险与对策

| 风险 | 等级 | 对策 |
|------|------|------|
| 全量重写周期长，中途旧前端腐化 | 高 | 新旧并存，后端按路径分流，旧前端直到阶段 6 才下线 |
| `DataGrid` 虚拟滚动+编辑+列宽+选中耦合极重 | 高 | 单独成阶段 3，先迁移只读网格再逐步加编辑/选中 |
| 20+ 全局变量依赖耦合，Pinia 拆分可能遗漏 | 中 | 按表逐变量映射到 store，迁移每个功能时核对变量清单 |
| CodeMirror 6 补全数据源对接 | 低 | `@codemirror/lang-sql` 自带关键字，表名/列名用 `autocompletion` 叠加 |
| 后端静态服务白名单放宽引入安全风险 | 低 | 仅放行 `assets/` 单层扁平文件，仍拒 `..`，与现有安全策略一致 |
| 内联 onclick 里的 `escAttr` 转义逻辑在 Vue 模板里消失，可能引入 XSS | 中 | Vue 模板默认转义，但动态 HTML（如 ER 图 SVG）需用 `v-html` 显式标注并审计 |
| 不引 UI 库导致组件开发量上升 | 中 | 除 DataGrid 外都是低成本组件，且现有原生 JS 已有实现可参考 |

---

## 十一、验收标准

- [ ] `pnpm build` 产出 `dist/`（纯静态，无 Node 运行时依赖）
- [ ] 产物体积 < 500KB gzip（对比旧方案 Monaco 版 2.2MB）
- [ ] `python app.py` 后访问入口加载 Vue 应用，无控制台错误
- [ ] 功能对等：连接/浏览/CRUD/SQL/导入导出/表设计/结构同步/存储过程 全部可用
- [ ] 性能不退化：数据网格 1 万行滚动流畅（虚拟滚动）、SQL 编辑器输入无卡顿
- [ ] 旧前端下线，单入口
- [ ] `Dockerfile` 多阶段构建：build 阶段装 pnpm 构产物，运行阶段只拷 `dist/`

---

## 十二、首轮（地基）工作清单

如确认执行，首轮只做这些，产出可验证的空壳（所有前端文件在 `frontend/` 子目录下）：

1. 初始化 Vite 工程（`frontend/` 下）：`package.json` `vite.config.ts` `tsconfig.json` `index.html`(Vite 入口)
2. 装依赖（13 个）：vue vue-router pinia vue-virtual-scroller + codemirror @codemirror/state @codemirror/view @codemirror/commands @codemirror/language @codemirror/autocomplete @codemirror/lang-sql + vite typescript @vitejs/plugin-vue
3. `src/main.ts` + `src/App.vue` + `src/router/index.ts`（路由表骨架，**用 `createWebHashHistory`**）
4. `src/api/client.ts`（fetch + 拦截器 composable，含 RSA 密码加密逻辑从 base.js 搬过来）
5. `src/api/*.ts` 7 个模块文件（函数签名 + 调用契约，逻辑可先 return mock）
6. `src/stores/*.ts` 7 个 store（state + action 签名）
7. `src/components/` + `src/layouts/` 空壳组件（占位 template）
8. `src/assets/styles.css`（从现有 `css/style.css` 原样搬，复用 CSS 变量 + `[data-theme]` 主题）
9. 后端 `handler.py` 新增 `/v2` 入口分流 + `/v2/assets/` 从 `frontend/dist/assets/` 读（不动 `STATIC_DIRS` 白名单）
10. `pnpm build`（在 `frontend/` 下）→ `dist/`，`python app.py` → 访问 `/v2` 看到空壳，控制台无报错，fetch 调通 `/api/config`

**预计产出**：~16 个文件，~650 行代码，可独立验证。

---

## 十三、与旧方案（Monaco 版）的差异

| 维度 | 旧方案 | 本方案 |
|------|--------|--------|
| SQL 编辑器 | Monaco（2MB） | CodeMirror 6 拆分包（~60KB） |
| UI 库 | Element Plus（200KB） | 手写（0） |
| HTTP | axios（13KB） | 原生 fetch + composable（0） |
| 工具集 | @vueuse/core（40KB） | 手写 composable（0） |
| 依赖总数 | 11 个 | **13 个**（CM6 拆分包多 6 个，但总体积小得多） |
| 产物体积 | ~2.6MB gzip | **~400-500KB gzip** |
| 路由模式 | history（需后端通配） | **hash（后端零改动）** |
| 工程目录 | 项目根（覆盖旧 index.html） | **`frontend/` 子目录（新旧并存）** |
| 组件开发 | 框架库现成 | 手写（除 DataGrid 外都低成本） |
| SQL 编辑器能力 | 顶配（多光标/minimap） | 够用（高亮/补全/折叠/撤销） |
| 样式 | 重写 | **原样搬现有 CSS 变量体系** |
| 适用场景 | 通用 IDE 级 | DBA 工具刚好够用 |
