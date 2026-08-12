## 改动说明

简要描述这次改动解决什么问题。

## 测试

- [ ] 后端：`python tests/smoke_test.py` 通过
- [ ] 后端：`python tests/e2e_http_smoke.py` 通过（本机 users.json 为默认口令时先 `export DBM_DEFAULT_PWD=<随机值>`）
- [ ] 前端：`npm run test` + `npm run typecheck` 通过
- [ ] 若新增路由模块：已实现 `handle_get` 与 `handle_post` 双接口并注册进 `ROUTE_MODS`

## 类型

- [ ] Bug 修复
- [ ] 新功能
- [ ] 重构（行为不变）
- [ ] 文档

## 其他

如果涉及安全，请先在 SECURITY.md 的私密渠道沟通，不要在 PR 中贴敏感信息。
