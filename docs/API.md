# DB Manager API 参考（概览）

> 版本：1.4.x。Base URL：`http(s)://<host>:<port>`。
> 认证：登录成功后服务端签发会话（HttpOnly Cookie `dbm_user` 或请求头 `X-User-Token`）；
> 连接上下文通过 `X-Session`（按名直连会话）或 `X-Conn`（Base64 连接 JSON，密码 RSA 加密）传递。
> 密码字段统一走 `rsa:` 前缀加密（先 GET `/api/pubkey`）。

## 约定

- 成功返回 JSON；错误返回 `{"error": "..."}`（脱敏，不含堆栈）。
- 鉴权失败：`401 {"require_login": true}`；权限不足：`403`；
  强制改密拦截：`403 {"must_change_pwd": true}`；请求体超限：`413`。
- 写操作路径（`/api/row`、`/api/import`、`/api/alter`、`/api/restore`、`/api/sync`、
  `/api/routines/*`、`/api/schema-sync`、`/api/connections*`、`/api/transaction/*`、
  `/api/gen-data`、`/api/transfer`）要求 write/admin 角色，且对 `read_only` 连接拒绝。

## 监控与配置

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 探活：`{status, version, uptime_seconds, pid, auth_required, sessions, requests_total, errors_total, python}`（免登录） |
| GET | `/api/metrics` | Prometheus 文本格式指标（免登录） |
| GET | `/api/config` | 全局配置：`{version, auth_required, auth_user, auth_role, must_change_pwd, register_enabled, saved_connections, api_base, gateway_required, default_conn}` |
| GET | `/api/pubkey` | RSA 公钥（PEM），用于密码加密 |
| GET | `/api/gateway/status` | 网关令牌状态 |

## 认证与账号

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | `{username, password}` → `{ok, token, user, role, must_change_pwd}`；Set-Cookie `dbm_user` |
| POST | `/api/logout` | 登出（删会话 + 清 Cookie），未登录也 200 |
| POST | `/api/password` | 改密：`{old_password, new_password}`（新密码 ≥6 位） |
| POST | `/api/register` | 自助注册（仅 `DBM_ALLOW_REGISTER=1` 时开放，默认只读角色） |
| GET | `/api/users` | 账号列表（admin） |
| POST | `/api/users` | 新建/更新账号：`{username, role, password?}`（admin；非 admin 不得授予 admin 角色） |
| POST | `/api/users/delete` | 删除账号（admin；不能删自己） |
| POST | `/api/gateway/login` | 公网网关令牌验证：`{token}` → Set-Cookie `dbm_gw` |
| POST | `/api/shutdown` | 关停服务（仅 admin） |

## 连接管理

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/connections` | 可见连接列表（按角色过滤） |
| POST | `/api/connections` | 保存/更新连接（写权限；`visible_to`/`mode` 仅 admin） |
| POST | `/api/connections/delete` | 删除连接 |
| POST | `/api/connect` | 建立连接会话：`{db_type, server, port, uid, pwd, database?}` → `{session}` |
| POST | `/api/test` | 测试连接（需 write；拒绝 URL/路径形式 server，防 SSRF） |

## 数据浏览与查询

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/databases` | 数据库列表 |
| GET | `/api/tables` | 表/集合/键列表（含 Mongo 集合、Redis 键） |
| GET | `/api/objects` | 对象树（库/表/视图等） |
| GET | `/api/columns` | 列信息：`?s=&t=` |
| GET | `/api/indexes` | 索引列表 |
| GET | `/api/relations` | 外键关系 |
| GET | `/api/data` | 分页数据：`?s=&t=&page=&size=&sort=&where=`（where 为方言 SQL；Mongo 传 JSON 条件） |
| POST | `/api/sql` | SQL 执行：`{sql, limit?, write?, database?}` → `{results: [...]}`；无 LIMIT 的 SELECT 自动限 500 行 |
| POST | `/api/explain` | EXPLAIN：`{sql, database?}` |
| POST | `/api/row` | 行增改：`{s, t, values, transaction?, tx_id?}`（PUT/DELETE 同路径） |
| POST | `/api/import` | 数据导入（CSV/TSV/Excel 粘贴） |
| POST | `/api/export/sql` | 查询结果导出（CSV/XLSX） |
| POST | `/api/stats` | 列统计（count/sum/avg） |
| POST | `/api/gen-data` | 测试数据生成 |
| POST | `/api/transaction/commit` / `rollback` | 事务提交/回滚（按 tx_id） |

## 结构操作

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/alter` | 表结构变更：`{action, ...}`（create/rename/drop/truncate/clear/copy/maintain/set_ttl… 四方言） |
| GET | `/api/er` | ER 图数据 |
| POST | `/api/schema/diff` | 结构对比：`{src, dst, schema, table}` |
| POST | `/api/schema/sync` | 结构同步执行 |
| POST | `/api/sync` | 数据同步：`{target_conn, ...}` |
| POST | `/api/transfer` | 跨库传输 |

## 备份与字典

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/backup` | 备份当前库（SQL 文本下载；BLOB/日期规范化） |
| POST | `/api/restore` | 还原 SQL |
| GET | `/api/export/schema` | 数据字典导出 |
| GET | `/api/db-users` | DB 用户与权限视图 |

## 存储过程 / 调度

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/routines` | 存储过程/函数/触发器列表 |
| GET | `/api/routine/source` | 对象源码 |
| GET | `/api/routine/params` | 参数列表 |
| POST | `/api/routine/save` / `drop` / `execute` | 保存重建 / 删除 / 参数化执行 |
| GET | `/api/tasks` | 调度任务列表 |
| POST | `/api/tasks` | 新建任务：`{name, conn_name, interval_min, action}` |
| POST | `/api/tasks/delete` / `toggle` / `run` | 删除 / 启停 / 立即执行 |

## 示例：登录 → 连接 → 查询

```bash
# 1. 登录(得到 token, 同时种 Cookie)
TOKEN=$(curl -s -X POST $BASE/api/login -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"****"}' | jq -r .token)

# 2. 建立连接会话(SQLite 示例)
SESS=$(curl -s -X POST $BASE/api/connect -H "X-User-Token: $TOKEN" \
  -d '{"db_type":"sqlite","database":"app.db"}' | jq -r .session)

# 3. 查询(带 X-Session 上下文)
curl -s "$BASE/api/data?s=&t=emp&page=1&size=10" -H "X-User-Token: $TOKEN" -H "X-Session: $SESS"
```
