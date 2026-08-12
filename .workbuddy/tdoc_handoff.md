# dbmanager 数据库管理工具 · 项目交接与部署指南

> 本文档用于跨电脑接续开发。新电脑上打开本文档 + 项目文件夹,即可完整恢复工作上下文。

## 一、项目简介

轻量级「多数据库 Web 管理端」:单文件 Python 后端 + 单文件 HTML 前端,无框架依赖,SQLAlchemy 统一抽象。定位:**个人/内网数据库工具,对标 Navicat 高频使用场景**。

- **技术栈**:Python 3.13(http.server + SQLAlchemy 2.0) + 原生 HTML/JS(零依赖)
- **支持数据库**:SQL Server / MySQL(MariaDB) / PostgreSQL / SQLite
- **文件结构**:
  - `app.py`(2017 行)— 后端:90 个函数、22+ API 路由
  - `index.html`(1698 行)— 前端:101 个 JS 函数,单 script 块
  - `connections.json` — 已保存连接(密码 DPAPI 加密)
  - `setup_new_pc.bat` — 新电脑一键部署脚本
  - `get_ipv6.py/.bat` — 公网 IPv6 地址获取(硬编码 WLAN 网卡名)

## 二、当前功能清单(2026-08-11 迭代完成)

| 模块 | 能力 |
|---|---|
| 连接管理 | 手动连接/按名直连、Navicat 连接自动发现、密码 DPAPI 加密落盘、RSA 传输加密 |
| 数据浏览 | 表/视图分组折叠(151 表+38 视图)、多文档标签、分页、**单击选中/双击打开** |
| 数据编辑 | **双击单元格弹窗编辑**(大文本 textarea/日期选择器/NULL 复选框)、整行弹窗、行内新增/删除、事务模式(per-tab 隔离) |
| 查询筛选 | 列头排序(升/降/取消)、表头筛选(等于/区间/LIKE/为空/日期选择器/**介于...之间**)、WHERE 函数白名单(30+ 函数) |
| SQL 控制台 | 只读校验(SELECT/SHOW,禁多语句/DML)、历史记录(单击回填/**双击回填并执行**)、结果导出 CSV |
| 导出导入 | CSV/JSON 导出(带 BOM)、CSV 导入向导(列映射/预览/批量)、数据字典(Markdown) |
| 表结构 | DDL 向导(加/删/改列、索引)、按方言生成 SQL |
| 高级 | ER 图(SVG 关系图)、库对库同步(append/replace)、用户权限只读查看 |
| 安全 | CORS Origin 白名单、Host 校验(防 DNS rebinding)、会话 12h 过期、连接文件原子写、防双开 |

## 三、快速启动

```bash
python app.py        # 浏览器自动打开 http://127.0.0.1:8770
```

环境要求:Python 3.13 + sqlalchemy + pycryptodome + PyMySQL + pg8000 + pyodbc + ODBC Driver 17 for SQL Server。

VS Code 调试:项目已配置 `.vscode/launch.json`(F5 直接跑,解释器锁定)。

## 四、新电脑部署(3 步)

1. **装 Python**:python.org 下载 3.10+(勾选 Add to PATH)
2. **一键部署**:双击项目里的 `setup_new_pc.bat`(自动装依赖、检测 ODBC 驱动、启动)
3. **重建连接**:打开工具后,「我的连接」里每条连接点"编辑"→ 重新输入密码 → 保存
   (密码是 DPAPI 加密,绑定旧电脑 Windows 账户,新电脑必须重输)

## 五、已保存的连接(2026-08-11)

| 名称 | 类型 | 地址 | 账号 | 状态 |
|---|---|---|---|---|
| Premier20260807UAT | SQL Server | 192.168.23.29\sql2025 | dbholder | ✅ 可用(189 张表) |
| Sam | SQL Server | Sam(localhost):1433 | sa/88888888 | ✅ 可用 |
| 本地MariaDB | MySQL | localhost:3307 | root | ⚠️ 需先启动 MariaDB 服务 |
| php | MySQL | localhost:3008 | root | ⚠️ 需先启动服务 |

## 六、安全架构要点

- **存储**:密码 AES-256-GCM → 已升级 **Windows DPAPI**(绑定账户,拷走目录也解不开;非 Windows 回退 AES)
- **传输**:前端 WebCrypto RSA-OAEP/SHA-256 加密密码(rsa: 前缀),服务端私钥解密;本机 localhost 自动生效
- **防攻击**:CORS Origin 白名单回显、域名形式 Host 一律 403(防 DNS rebinding)、会话 token 不落前端、SQL 白名单校验

## 七、给 AI 的接续上下文(重要)

在另一台电脑的 WorkBuddy 里打开本项目时,把下面这段粘贴给 AI,即可恢复全部上下文:

```
这是 dbmanager 数据库管理工具项目。2026-08-11 已完成:数据丢失级 bug 修复(commit 在 with 外)、
会话模式 PUT/DELETE 修复、CORS/Host 安全加固、DPAPI+RSA 密码加密、ODBC 驱动自适应、
空库 DSN 模式坑修复(空库默认连 master)、连接文件原子写+防双开、SQL 控制台(只读)、
列排序/筛选(日期/介于)/导出导入/数据字典/表结构 DDL/ER 图/库对库同步/用户权限只读、
双击事件(表列表/单元格弹窗编辑/SQL 历史/连接列表)。
当前连接:Premier20260807UAT(192.168.23.29\sql2025, dbholder)、Sam(本机 sa/88888888)。
已知坑:①改代码后必须杀干净旧进程(PowerShell Get-NetTCPConnection 确认端口释放)再启动;
②Edit 工具对超长行静默失败,renderGrid 这类长行用 Python 直接改文件;
③connections.json 换机需重输密码(DPAPI 绑定账户)。
遗留:SSH 隧道(需 paramiko)、回归测试脚本(建议优先)、PyInstaller 打包 exe。
```

## 八、遗留事项与建议(按优先级)

1. **回归测试脚本**(P0):把连接→读→改→删→SQL→导出核心链路固化成 test_api.py,防改坏
2. **PyInstaller 打包 exe**(P1):双击即用,终结环境问题
3. **右键菜单 + 快捷键**(P1):对标 Navicat 操作效率
4. **SQL 编辑器增强**(P1):语法高亮 + 格式化
5. 路由 if 链重构为分发表(P2);SSH 隧道(按需)
