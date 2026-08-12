# Changelog

本项目遵循[语义化版本](https://semver.org/lang/zh-CN/)。发版流程：更新 `config.py VERSION` 与 `frontend/package.json version` → 追加本节 → 打 tag `vX.Y.Z`（自动触发 Release 构建）。

## [1.5.0] - 2026-08-12

### 新增
- 强制首次改密：默认 admin 账号首次登录必须修改密码（is_default 标记，兼容老部署默认口令检测）；未改密前业务接口一律 403，只放行改密、登出和配置；登录响应和 /api/config 返回 must_change_pwd，前端强制改密弹窗不可关闭
- 健康检查与监控指标：/api/health（探活，免登录）、/api/metrics（Prometheus 文本格式），指标统计独立成 metrics.py，无第三方依赖
- 前端收口：默认入口 / 直接服务 Vue3 构建产物，旧版 index.html 只在未构建时兜底
- 开源授权：切换为 Apache License 2.0（可自由使用/修改/再分发含商用）；发布前重写 git 历史清除全部敏感文件（密钥、连接配置、测试库，139→133 commits）
- 文档：新增 docs/USER_GUIDE.md（用户手册）、docs/DEPLOYMENT.md（部署指南）、docs/API.md（接口参考）
- 前端单元测试：引入 vitest（18 项），覆盖筛选条件与 SQL 格式化的注入防护；接入 CI 和发版流程

### 工程化
- 请求日志接入指标计数（方法/路径/状态码/5xx，线程安全）
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
