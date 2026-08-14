# DB Manager 首次发布操作清单（优化路线图 0.2）

> 适用：本地代码已就绪（`main` 最新含 P0/P1 全部修复），准备公开 GitHub 仓库并触发首次 Release。
> 执行人：本机用户（沙箱环境无 GitHub 凭据，以下命令均在本机 Git Bash / PowerShell 执行）。

---

## 一、发布前自检（本机 30 秒）

```bash
cd <仓库根>   # D:\Code\Git\数据库工具\dbmanager
git status            # 应为干净(无未提交/未跟踪)
git log --oneline -3  # 最近应含: 5e57ba8 refactor(handler 拆分) ...
python -c "import app; print('import OK')"
```

可选（完整回归，约 3 分钟）：
```bash
python tests/smoke_test.py && python tests/test_p0_security.py && python tests/test_audit.py
```

---

## 二、轮换本机密钥（发布前必做，防旧密钥随历史泄露）

```bash
# 1) 删除旧密钥(删除后下次启动自动重生)
rm -f .dbm_rsa .dbm_key .dbm_gateway
# 2) 启动一次让程序重生密钥
python app.py &   # 观察日志生成 .dbm_gateway 令牌
# 3) 确认新密钥已生成
ls -la .dbm_rsa .dbm_key .dbm_gateway
# 4) 若启用了 HTTPS 自签证书, 一并轮换
rm -f .dbm_cert.pem .dbm_key_ssl.pem
```

> 注意：轮换后**旧连接配置里用旧密钥加密的密码将无法解密**，需在界面重新输入密码保存（`get_connection_by_name` 会给出明确提示）。

---

## 三、推送公开仓库（force push）

```bash
git remote -v                # 确认 origin = GitHub(SamXMG/dbmanager)
git push -f origin main --tags
git push -f origin --all     # 如存在其他分支一并推送
```

> 首次公开推送用 `-f` 覆盖远端旧历史（此前为私有仓库）。推送后立即在 GitHub 确认：
> - 仓库可见性已设为 Public
> - 历史中无敏感文件（`git-filter-repo` 已清理，发布前可再抽查 `git log --name-only | grep -iE "\.pem|\.key|\.db$"` 应无结果）

---

## 四、触发首次 Release

### 方式 A：GitHub 网页（推荐，最直观）
1. 打开仓库 → Releases → 新建 Release
2. Tag：`v1.5.0`（当前 `config.py VERSION` / `frontend/package.json version` 均为 1.5.0）
3. 标题：`v1.5.0`；正文从 CHANGELOG 摘录（首版可写总览 + 安全特性）
4. 点 Publish → `release.yml` 自动构建（Ubuntu/Windows 矩阵 + Docker 镜像）

### 方式 B：命令行
```bash
git tag v1.5.0
git push origin v1.5.0
# 之后在 GitHub Releases 页面编辑/发布该 tag 的 Release
```

> 发布动作触发后，观察 Actions 页签：backend 矩阵（Py 3.10-3.12 × U/W）、frontend、docker 三个 job 应全绿。

---

## 五、发布后验证（冒烟）

```bash
# 本机
python app.py        # 默认入口 / 服务 Vue3 构建产物
curl -s http://127.0.0.1:8770/api/health   # 应返回 ok

# Docker(可选)
docker build -t dbmanager .
docker run -p 8770:8770 -v dbmanager_data:/app/data dbmanager
curl -s http://127.0.0.1:8770/api/health
```

页面验收点：登录（首次强制改密）→ 连接 SQLite 测试库 → 对象树/网格/SQL 工作台 → 弹窗按钮可关闭（事件委托）→ 主题切换。

---

## 六、回滚预案

| 场景 | 处置 |
|---|---|
| Release 构建红 | 修代码重推 tag（`git tag -d v1.5.0 && git push origin :v1.5.0` 后重打） |
| push 后发现敏感文件泄露 | **立即轮换全部密钥 + 重写历史**（git-filter-repo 清除后 force push），并重置 GitHub 令牌 |
| 远端历史被拒（非 fast-forward） | 按现状即 force push 场景，无需额外操作 |
| 密钥轮换后密码解不开 | 界面重新输入密码保存（连接编辑弹窗），无需回滚 |

---

## 七、发布后短期清单（P1 backlog，不阻塞发版）

- [ ] 双前端退役：确认 `js/` 无入口引用后删除（需用户确认，当前为 dist 缺失兜底）
- [ ] mypy 从 non-blocking 转阻断（存量标注收敛后）
- [ ] 响应体类型契约（~22 处 any）收口
- [ ] docsify 文档站 / issue·PR 模板 / i18n
