# DB Manager 文档

> 多数据库管理工具（对标 Navicat / DBeaver 高频场景），Apache-2.0 开源。
> 一个 Python 进程同时管理 **SQLite / MySQL / PostgreSQL / SQL Server / Oracle / MongoDB / Redis**，
> 并兼容 OceanBase / TiDB / KingbaseES（协议归一化）。

## 这是什么

DB Manager 是一个自托管、Web 化的多数据库管理工具：浏览器即客户端，内置账号体系、
读写权限、LDAP/AD、连接级 ACL、审计日志与传输加密，适合个人、内网团队与企业私有化部署。

- **多数据库**：10 种数据库类型统一界面，方言化元数据 / DDL / EXPLAIN / 导入导出
- **数据浏览**：分页网格、排序筛选、单元格编辑、Excel 批量粘贴、CSV/XLSX 导入导出
- **SQL 工作台**：CodeMirror 6 编辑器、多结果 tab、历史收藏、EXPLAIN 可视化、写模式危险确认
- **对象管理**：表设计器、存储过程/函数/触发器、ER 关系图、结构对比与同步
- **工具**：查询构建器、测试数据生成器、备份还原、调度任务、数据字典
- **安全**：AES-GCM 落盘 + Windows DPAPI + RSA-OAEP 传输；PBKDF2 账号哈希；角色 read/write/admin；
  登录限流（5 次锁 5 分钟）；LDAP/AD；连接 ACL；生产库强制只读；审计日志

## 快速开始

```bash
python -m pip install -r requirements.txt
python app.py            # 默认 http://127.0.0.1:8770，自动打开浏览器
```

> 首次启动自动创建默认管理员账号 `admin`，但**初始密码不再固定为 `admin123`**：未配置 `DBM_DEFAULT_PWD` 时由系统生成 **16 位随机口令**（仅打印在启动日志 `logs/dbmanager.log`，搜索「初始口令」），已配置时取该值；**首次登录强制改密**。公网/局域网部署务必先拿到初始口令并改密、启用 HTTPS。详见《部署指南》与《用户手册》2.2 节。

## 文档导航

- [用户手册](USER_GUIDE) —— 日常使用：连接、数据浏览、SQL 工作台、权限、审计
- [API 参考](API) —— HTTP API 端点与示例
- [部署指南](DEPLOYMENT) —— 本机 / 内网 / Docker / 公网四种形态与安全加固
- [安全模型](SECURITY) —— 威胁模型、加密与漏洞报告渠道
- [支持与服务](SUPPORT) · [企业版路线图](ENTERPRISE) · [贡献指南](CONTRIBUTING)

## 许可证

Apache-2.0 开源，可自由使用、修改、再分发（含商用）。详见仓库根目录 `LICENSE`。
