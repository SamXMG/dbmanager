# Vue3 前端迁移差距清单(旧版 → /v2)

> 生成: 2026-08-12 | 方法: 旧版 index.html 按钮 + js/*.js ~230 函数 全量提取, 对照 frontend/src 逐项核实
> 状态: 阶段0-5 全部交付, **本清单所有项已实现**(2026-08-12 批2-6 完成), 下一步: 阶段6 旧前端下线(/v2 改 /)

## 已完成 ✅(全部)

连接管理(快速/我的连接/保存/测试)、认证(登录/注册/改密/账号管理)、网关、主题/视图切换、树导航(搜索/懒加载/跨库)、数据网格(排序/分页/单元格编辑/右键/按 tab 快照)、属性面板、工具栏(刷新/新增/删除/导出CSV/统计)、SQL 工作台全套(执行/格式化/解释/写模式/历史/收藏/多结果tab/结果过滤/导出CSV·Excel)、CodeMirror6 补全、表设计器(5-tab)、新建触发器、ER 关系图、数据同步(transfer)/结构同步(sync)、跨库 tab、DocTabs/状态条、右键菜单/弹窗体系、停止服务。

## 未实现 ✗

### P1 高优先级(常用功能缺失)

| # | 功能 | 旧版实现 | 说明 |
|---|------|----------|------|
| 1 | **列筛选 UI** | openFilter/applyFilter | grid store 的 buildWhere/setFilter 逻辑已就绪, 但网格**没有筛选入口**(列头无筛选, 工具栏无筛选条)——只差 UI |
| 2 | **查询构建器** | openQueryBuilder/qbBuild/qbLoadCols/qbAddCond | 可视化勾选列/条件/排序/limit 拼 SELECT 填入 SQL 台 |
| 3 | **数据导入向导** | openImport/parseCsv/parseImportFile/renderImportMap/doImport | CSV/XLSX 解析 → 列映射 → 批量插入(/api/import 已就绪) |
| 4 | **存储过程/函数/触发器编辑器** | openRoutine/saveRoutine/dropRoutine/execRoutine/procBar | 打开源码 /api/routine/source → 编辑 → 保存重建(DROP+CREATE)/执行/删除 |
| 5 | **事务模式真实生效** | toggleTransaction/commitTx/rollbackTx/txObj | 顶栏「事务」开关**只切本地状态, grid 增删改未传 transaction/tx_id** → 假开关 |
| 6 | **Redis/MongoDB 数据页** | redisNewKey/redisDelKey/redisTtl/redisAlter | 键/集合浏览、TTL 编辑; 当前 grid store 只支持关系型表 |

### P2 中优先级(常用/体验)

| # | 功能 | 旧版实现 | 说明 |
|---|------|----------|------|
| 7 | 全选/复制选中行/导出选中行 | toggleSelectAll/copySelectedRows/exportSelectedRows | 有行选中(Shift/Ctrl), 缺批量操作入口 |
| 8 | Excel 批量粘贴插入 | openPasteInsert/parsePasteInsert | 剪贴板 TSV/CSV 粘贴成行插入 |
| 9 | 备份/还原 | downloadBackup/openRestore/doRestore | 整库 SQL 脚本下载/上传还原(/api/backup /api/restore 已就绪) |
| 10 | 测试数据生成器 | genTestData/runGenData | 按列类型批量生成(/api/gen-data 已就绪) |
| 11 | schema diff 结构对比 | openSchemaDiff/runSchemaDiff/runSchemaSync | /api/schema/diff·sync 已就绪, 缺弹窗 |
| 12 | DB 用户与权限弹窗 | openUsers | 四方言登录/用户/角色/权限只读视图 |
| 13 | 全局快捷键 | F5/Ctrl+R 刷新, Ctrl+W 关 tab, Ctrl+Tab 切 tab, Ctrl+D 复制行 | 目前仅编辑器内 Ctrl+Enter/Ctrl+Shift+F |
| 14 | 列宽记忆/拖拽/双击输宽 | enableColResize/colWKey/saveColWidth/applyColWidths | 表维度 localStorage 记忆 |

### P3 低优先级(细节/较少用)

| # | 功能 | 说明 |
|---|------|------|
| 15 | 数据字典导出 UI | api exportSchema 已就绪, 缺右键/菜单入口 |
| 16 | 筛选/排序状态持久化 | 表维度 localStorage(saveTabState/tabStateKey) |
| 17 | 类型着色单元格 | 数字右对齐/日期/布尔样式(cellTypeClass) |
| 18 | 面包屑 | 选中对象完整路径(treeCrumbs) |
| 19 | 虚拟滚动 | 大表(万行)滚动重渲染, 当前一次性渲染最多 500 行/页, 可后置 |

## 补充完成(2026-08-12 批2-6, 用户指令「全部实现」)

- **批1 网格增强**: 列筛选 UI(列头▾面板 op+值)、全选 checkbox、复制/导出选中行、Excel 批量粘贴插入(TSV/CSV 解析→/api/import)、单元格类型着色(数字右对齐/日期/布尔/NULL)、列宽拖拽+表维度记忆。
- **批2 工具向导**: 查询构建器(可视化拼 SELECT)、数据导入向导(CSV 前端解析/XLSX 后端解析→列映射)、测试数据生成器、备份/还原、schema diff 对比、DB 用户与权限(新增 /api/db-users 路由, 修复原 /api/users 死代码)、数据字典导出。
- **批3 存储过程/函数/触发器编辑器**: RoutineModal(源码编辑/保存重建/执行参数收集/删除), 树双击+右键打开。
- **批4 事务真实现**: grid 增删改传 transaction+tx_id(按 tab 独立), 顶栏 开关+提交/回滚, 关闭自动回滚确认(修复原假开关)。
- **批5 交互**: 全局快捷键(F5/Ctrl+R/Ctrl+W/Ctrl+Tab/Ctrl+D)、SidePanel 面包屑、筛选/排序/页大小跨会话持久化、>300 行基础虚拟滚动。
- **批6 Redis/MongoDB**: 键/集合浏览(后端 /api/data 已支持) + Redis 新建键/TTL/删除键(走 /api/alter)。
- 后端改动: /api/db-users 路由(原 do_GET /api/users 与账号管理冲突为死代码)。
- 验证: tsc 0 错误 + build 成功(gzip ~217KB); e2e_stage5.py 11/11 + e2e_stage5b.py 16/16 PASS(事务回滚/提交、备份还原往返、gen-data、db-users、schema-diff、routine)。

## 下一步

**阶段6: 旧前端下线** —— /v2 改 /、旧 index.html/js/css 移除、Dockerfile 多阶段构建、新路由回归。
