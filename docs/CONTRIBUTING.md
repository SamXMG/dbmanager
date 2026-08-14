# 贡献指南（Contributing）

感谢你对 DB Manager 的兴趣！无论是提 Issue、修 Bug 还是加功能，都欢迎。

## 快速开始

```bash
# 后端（Python 3.10+）
python -m pip install -r requirements.txt
python app.py                          # http://127.0.0.1:8770

# 前端（Vue3 + TS，默认入口 / 即服务 dist）
cd frontend
npm install
npm run dev                            # Vite dev server (5173, 代理 /api 到 8770)
npm run test                           # 单测
npm run typecheck                      # 类型检查
npm run build                          # 构建 dist（后端自动服务）
```

## 测试约定（重要）

- **后端**：`tests/` 下三套单测 + HTTP 全链路冒烟 + 安全 e2e，改动后本地全量跑一遍：
  ```bash
  python tests/smoke_test.py
  python tests/test_ops.py
  python tests/test_task_sched.py
  python tests/e2e_http_smoke.py
  ```
- **注意**：本机若 `users.json` 中 admin 仍是默认口令，运行安全 e2e 前需
  `export DBM_DEFAULT_PWD=<随机值>`（否则强制改密会 403 拦截测试请求）。
- **前端**：`npm run test`（vitest，核心逻辑：注入防护/格式化）。
- CI（`.github/workflows/ci.yml`）会在 PR 上跑全部：Py 3.10–3.12 × Ubuntu/Windows、
  静态检查、单测、安全 e2e、依赖漏洞扫描、前端测试/类型/构建。**PR 必须全绿**。

## 提交规范

- 遵循语义化版本；commit message 用中文、单行概括 + 关键细节（参考历史提交风格）；
- 涉及安全修复请在 message 中标注受影响接口与验证方式。

## 架构速览（改代码前必读）

```
app.py           入口（服务器/SSL/启动流程）
handler.py       HTTP 层：鉴权网关(_host/_gateway/_auth/_must_change/_require_write)、静态、审计
routes/          按领域路由（connection/query/schema/files/routines/monitor/admin）
services/        数据操作层（core/metadata/export/nosql/routines/tools/ddl/sync/backup/sql/data）
metrics.py       进程指标（Prometheus，零依赖，避免路由反向 import handler 的循环导入）
auth.py          账号体系（PBKDF2/RBAC/LDAP/限流/强制改密）
crypto.py        密码加解密（AES-GCM 落盘/RSA 传输/DPAPI）
store.py         连接配置持久化（加密落盘）
frontend/src/    Vue3 + TS + Pinia + CodeMirror 6（stores/ 为状态与核心逻辑，均有单测）
```

### 路由模块新增规则（踩过的坑）

1. 新路由模块**必须同时实现 `handle_get` 与 `handle_post`**（分发器按模块遍历调用，
   缺一个会 AttributeError → 500），并注册进 `routes/__init__.py` 的 `ROUTE_MODS`；
2. 不要在 routes 里 `import handler`（循环导入）——公共能力经 `handler._xxx()` 包装方法调用，
   指标等独立逻辑放 `metrics.py`；
3. 新 API 若为写操作：路径加入 `handler.WRITE_PATHS`（角色 + 只读连接双门禁）；
4. 只读端点若需免登录（探活/指标类），加入 `_auth_blocked`/`_must_change_blocked` 豁免并注明原因。

## Issue 模板

- **Bug**：版本、运行环境（OS/Python/数据库类型）、复现步骤、期望 vs 实际、日志片段（脱敏）；
- **功能建议**：使用场景、期望行为、可接受的最小实现。
