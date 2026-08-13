# -*- coding: utf-8 -*-
"""dbmanager - routes.admin: 管理: 登录/用户/网关/调度任务/关机"""
import json
import os
import subprocess
import sys
import threading
import time

from urllib.parse import parse_qs, urlsplit

import auth
import config
import task_sched

from config import DEFAULT_PORT, HOST, PORT
from crypto import rsa_public_pem
from dbcore import (
    _norm_db_type, build_url, conn_hash, get_engine, get_mongo, get_redis,
    test_connection,
)
from ops import (
    _xlsx_bytes, alter_table, backup_database, commit_transaction, diff_schema,
    drop_routine, execute_routine, execute_schema_sync, explain_query,
    export_data, export_schema_doc, gen_data, get_columns, get_data,
    get_databases, get_er_data, get_indexes, get_relations, get_routine_params,
    get_routine_source, get_routines, get_tables, get_users_privs, import_data,
    mutate, parse_xlsx_import, restore_sql, rollback_transaction, run_sql,
    save_routine, stats_column, sync_table, transfer_data,
)
from store import (
    delete_connection, get_connection_by_name, list_connections, save_connection,
)
import sqlitedb  # 系统数据查询(/api/sysdb)与审计查询(/api/audit)


def _sysdb_validate(sql):
    """系统查询白名单校验: 仅单条只读 SELECT(防注入/防写坏系统数据)
    返回 (ok, message)"""
    s = sql.strip()
    if not s:
        return False, "SQL 不能为空"
    # 去掉开头注释与括号包裹, 取第一个有效词
    body = s
    for _ in range(3):
        body = body.lstrip()
        if body.startswith("--"):
            body = body.split("\n", 1)[-1] if "\n" in body else ""
        elif body.startswith("/*"):
            end = body.find("*/")
            body = body[end + 2:] if end >= 0 else ""
        elif body.startswith("("):
            body = body[1:]
        else:
            break
    if not body.upper().startswith("SELECT"):
        return False, "仅支持 SELECT 只读查询"
    if ";" in s:
        return False, "仅支持单条语句(禁止分号)"
    import re as _re
    for kw in ("insert", "update", "delete", "drop", "alter", "create",
               "attach", "detach", "vacuum", "pragma", "reindex"):
        if _re.search(r"\b%s\b" % kw, s.lower()):
            return False, "仅支持只读查询(检测到写操作关键字: %s)" % kw
    return True, ""


def _safe_error_short(e):
    """SQL 错误脱敏短文案(系统查询用): 透传 sqlite 错误信息对排查有用"""
    return str(e)[:300]


# ------------------------------
# 服务器配置读写 (/api/config/settings, 仅 admin)
# - 可编辑项 = config._ENV_MAP 中注册的 [server]/[auth] 键(白名单, 防写任意键)
# - 写回 dbmanager.conf: 逐行扫描保留注释与顺序, 仅更新白名单键; 键不存在则按默认值占位追加
# - 敏感键(gateway_token/default_pwd/ldap_bindpw)读时掩码, 前端传掩码占位符时不覆盖
# ------------------------------
_SENSITIVE_KEYS = {"gateway_token", "default_pwd", "ldap_bindpw"}
_MASK_PLACEHOLDER = "******"

# 需要重启才能生效的键(启动期绑定/读取): host/port(已绑定 socket)、ssl 与证书(握手加载)
_RESTART_KEYS = {"host", "port", "ssl", "ssl_cert", "ssl_key"}


def _restart_server():
    """后台重启服务进程: 启动新实例(app.py)并强制关闭 DBM_NO_KILL(依赖自动接管端口),
    旧实例 0.8s 后退出释放端口。返回 (ok, message)。"""
    py = sys.executable or "python"
    script = os.path.join(config.BASE_DIR, "app.py")
    env = dict(os.environ)
    env["DBM_NO_KILL"] = ""  # 允许新实例自动终止旧实例并接管端口
    try:
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([py, script], cwd=config.BASE_DIR, env=env,
                         creationflags=flags, close_fds=True)
    except Exception as e:
        return False, "启动新实例失败: %s" % e
    threading.Timer(0.8, lambda: os._exit(0)).start()
    return True, "重启中, 约 2~3 秒后恢复, 请重新登录"

def _settings_sections():
    """返回可编辑 section -> [键列表]（来源于 config._ENV_MAP 的注册键）"""
    out = {}
    for env_name, (section, key, default) in config._ENV_MAP.items():
        if section not in out:
            out[section] = []
        out[section].append((key, env_name, default))
    return out

def _load_settings_file():
    """读取 dbmanager.conf 原始行; 不存在时返回 None"""
    p = config._config_path()
    try:
        with open(p, "r", encoding="utf-8") as f:
            return p, f.readlines()
    except FileNotFoundError:
        return p, None

def _read_settings():
    """读取当前配置: 返回 {section: {key: {value, masked, default, env}}}"""
    out = {}
    cfg = config._load_config()
    for section, items in _settings_sections().items():
        out[section] = {}
        if not cfg.has_section(section):
            cfg.add_section(section)
        for key, env_name, default in items:
            try:
                raw = cfg.get(section, key, fallback=default)
            except Exception:
                raw = default
            masked = key in _SENSITIVE_KEYS and bool(raw)
            out[section][key] = {
                "value": (_MASK_PLACEHOLDER if masked else raw),
                "masked": masked,
                "default": default,
                "env": env_name,
                "apply": ("restart" if key in _RESTART_KEYS else "instant"),
            }
    return out

def _write_settings(updates):
    """写回配置(白名单键)。updates: {section: {key: value}}
    返回 (ok, message); 校验失败返回 (False, 原因)。"""
    path, lines = _load_settings_file()
    if lines is None:
        lines = ["# DB Manager 配置文件(由管理界面生成)\n", "\n", "[server]\n", "\n", "[auth]\n", "\n"]
    # 白名单键集合
    allowed = {k for _, items in _settings_sections().items() for k, _, _ in items}
    # 1. 校验(兼容两种载荷: 纯值 {key: "val"} 或前端整表 {key: {value, masked, ...}})
    validated = {}
    for section, kv in (updates or {}).items():
        if section not in ("server", "auth"):
            return False, "非法配置分组: %s" % section
        for key, val in kv.items():
            if key not in allowed:
                return False, "不允许修改的配置项: %s" % key
            if isinstance(val, dict):
                val = val.get("value", "")
            if key in _SENSITIVE_KEYS and val == _MASK_PLACEHOLDER:
                continue  # 掩码占位: 不覆盖
            if val is None:
                val = ""
            val = str(val)
            if "\n" in val or "\r" in val:
                return False, "配置值不允许包含换行: %s" % key
            if key == "port":
                try:
                    p = int(val)
                except ValueError:
                    return False, "port 必须是数字"
                if not (1 <= p <= 65535):
                    return False, "port 超出范围(1-65535)"
            if key in ("host", "ssl", "dev", "log", "no_open", "no_kill",
                       "auth_enabled", "allow_register") and val not in ("", "0", "1"):
                if key == "host":
                    pass  # host 允许任意值(IP/域名/0.0.0.0)
                else:
                    return False, "%s 只允许 0/1/空" % key
            validated.setdefault(section, {})[key] = val
    # 收集需要重启的变更键(仅统计"值真正变化"的, 前端整表提交时原值不算变更)
    cfg = config._load_config()
    restart_changed = []
    for section, kv in validated.items():
        for key, val in kv.items():
            if key not in _RESTART_KEYS:
                continue
            try:
                old = cfg.get(section, key, fallback="")
            except Exception:
                old = ""
            if old != val:
                restart_changed.append(key)
    if not validated:
        return True, "无有效变更", []
    # 2. 逐行更新(保留注释与顺序): 只在 [section] 内找 key, 找不到则在该 section 末尾追加
    section = None
    pending = dict(validated)  # 待写入的 section->{key:val}
    out = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip()
            out.append(line)
            continue
        if section and section in pending:
            # 形如  key = value 或 key=value (允许行首空白)
            line_body = line.lstrip()
            if "=" in line_body and not line_body.lstrip().startswith(("#", ";")):
                k, _, v = line_body.partition("=")
                k = k.strip()
                if k in pending[section]:
                    indent = line[:len(line) - len(line_body)]
                    out.append("%s%s = %s\n" % (indent, k, pending[section].pop(k)))
                    continue
        out.append(line)
    # 3. 追加未匹配的键到对应 section 末尾(段不存在则先补段头, 避免键落错段)
    for section, kv in pending.items():
        if not kv:
            continue
        # 定位 section 是否存在及其最后一行
        section_exists = False
        last_idx = None
        cur = None
        for i, line in enumerate(out):
            s = line.strip()
            if s.startswith("[") and s.endswith("]"):
                cur = s[1:-1].strip()
                if cur == section:
                    section_exists = True
            elif cur == section:
                last_idx = i
        if section_exists:
            insert_at = (last_idx + 1) if last_idx is not None else len(out)
            block = ["\n"]
        else:
            insert_at = len(out)
            block = ["\n[%s]\n" % section]
        for k, v in kv.items():
            block.append("%s = %s\n" % (k, v))
        out[insert_at:insert_at] = block
    # 4. 写回
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.writelines(out)
    except Exception as e:
        return False, "写入配置失败: %s" % e
    config._CONFIG_CACHE = None  # 失效缓存, 运行时读取项(如 LDAP/注册开关)下次 conf() 即生效
    if restart_changed:
        return True, "配置已保存；%s 需重启服务后生效，可点「立即重启」" % "、".join(restart_changed), restart_changed
    return True, "配置已保存并即时生效，无需重启", []


def handle_get(handler, path, q):
    """GET 路由: 已处理返回 True, 否则 False"""
    if path == "/api/users":
                    if handler._require_admin():
                        handler._send_json(200, {"users": auth.list_users()})
                    return True
    if path == "/api/tasks":
                    # 调度任务列表(P2-2)
                    handler._send_json(200, {"tasks": task_sched.list_tasks()})
                    return True
    if path == "/api/users/perms":
                    # 细粒度权限查询: 指定用户的连接/表级权限 + 全部连接名(权限配置弹窗用)
                    if not handler._require_admin():
                        return True
                    un = (q.get("username") or [""])[0]
                    if not un:
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    handler._send_json(200, {"perms": auth.user_perms(un),
                                             "connections": [c["name"] for c in list_connections()]})
                    return True
    if path == "/api/sessions":
                    # 在线用户列表(在线管理面板): 仅 admin
                    if not handler._require_admin():
                        return True
                    handler._send_json(200, {"sessions": auth.list_sessions()})
                    return True
    if path == "/api/audit":
                    # 审计查询(按 用户/操作 筛选, 时间倒序): 仅 admin
                    if not handler._require_admin():
                        return True
                    rows = sqlitedb.audit_query(user=(q.get("user") or [""])[0] or None,
                                                action=(q.get("action") or [""])[0] or None,
                                                limit=(q.get("limit") or ["200"])[0],
                                                offset=(q.get("offset") or ["0"])[0])
                    handler._send_json(200, {"rows": rows})
                    return True
    if path == "/api/config/settings":
                    # 服务器配置读取(管理界面用): 仅 admin
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    handler._send_json(200, {"sections": _read_settings(),
                                             "config_file": config._config_path()})
                    return True
    return False

def handle_post(handler, path, q):
    """POST 路由: 已处理返回 True, 否则 False"""
    if path == "/api/gateway/login":
                    handler._do_gateway_login()
                    return True
    if path == "/api/login":
                    b = handler._body()
                    if not isinstance(b, dict):
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    st, payload = auth.login(b.get("username", ""), b.get("password", ""),
                                             handler.client_address[0])
                    if st == "ok":
                        tok, role, user = payload
                        # HttpOnly Cookie 承载令牌(防 XSS 窃取); X-User-Token 头仍返回兼容 API 客户端
                        handler.add_cookie("dbm_user", tok, max_age=43200)
                        handler._send_json(200, {"ok": True, "token": tok, "user": user, "role": role,
                                                  "must_change_pwd": auth.must_change_pwd(user)})
                        handler._audit_action("login", user)
                    elif st == "pending":
                        handler._send_json(401, {"error": "账号待管理员审批, 请稍后再试"})
                    elif st == "rejected":
                        handler._send_json(401, {"error": "账号已被拒绝, 请联系管理员"})
                    elif st == "locked":
                        handler._send_json(429, {"error": "尝试次数过多, 请 %d 秒后再试" % payload})
                    else:
                        handler._send_json(401, {"error": "用户名或密码错误"})
                    return True
    if path == "/api/logout":
                    # 登出: 删服务端会话 + 清 Cookie(未登录调用也返回 200)
                    tok = (handler.headers.get("X-User-Token") or "")
                    if not tok:
                        from auth import _cookie_token
                        tok = _cookie_token(handler.headers.get("Cookie")) or ""
                    auth.logout(tok)
                    handler.add_cookie("dbm_user", "", max_age=0)
                    handler._send_json(200, {"ok": True})
                    return True
    if path == "/api/users":
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():   # 账号管理属管理操作(提权防护): 仅 admin
                        return True
                    b = handler._body()
                    u = auth.current_user(handler)
                    ok, msg = auth.save_user(b.get("username", ""), b.get("role", "read"),
                                             b.get("password") or None,
                                             cur_role=(u["role"] if u else None))
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("save_user", b.get("username", ""))
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/users/delete":
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():   # 账号管理属管理操作(提权防护): 仅 admin
                        return True
                    b = handler._body()
                    u = auth.current_user(handler)
                    ok, msg = auth.delete_user(b.get("username", ""), u["user"] if u else "")
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("delete_user", b.get("username", ""))
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/users/approve":
                    # 审批自助注册账号(局域网一次性部署: 成员注册 -> 管理员审批放权)
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    b = handler._body()
                    u = auth.current_user(handler)
                    ok, msg = auth.approve_user(b.get("username", ""), b.get("role", "read"),
                                                b.get("action", ""),
                                                cur_role=(u["role"] if u else None))
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("approve_user", "%s %s" % (b.get("action", ""), b.get("username", "")))
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/users/perms":
                    # 细粒度权限配置(单用户/批量): body {usernames: [...], perms: {连接: {read, write, tables, deny_tables}}}
                    # 权限变更属管理操作: 仅 admin + 审计
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    b = handler._body()
                    if not isinstance(b, dict):
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    u = auth.current_user(handler)
                    ok, msg = auth.set_user_perms(b.get("usernames") or [],
                                                  b.get("perms") or {},
                                                  cur_role=(u["role"] if u else None))
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("set_user_perms",
                                              "users=[%s] conns=%s" % (
                                                  ",".join(b.get("usernames") or []),
                                                  ",".join((b.get("perms") or {}).keys())))
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/sessions/kick":
                    # 强制踢下线: 仅 admin + 审计; 不能踢自己(后端纵深校验)
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    b = handler._body()
                    u = auth.current_user(handler)
                    ok, msg = auth.kick_user((b or {}).get("username", ""),
                                             u["user"] if u else None)
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("kick_user", (b or {}).get("username", ""))
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/sysdb":
                    # 系统数据查询: 在程序内置 SQLite 上执行只读 SELECT(系统用户/权限/连接/审计/任务)
                    # 仅 admin; 白名单校验(SELECT-only + 单语句 + 禁写关键字)防注入
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    b = handler._body()
                    sql = (b.get("sql") or "").strip() if isinstance(b, dict) else ""
                    if not sql:
                        handler._send_json(400, {"error": "请输入 SQL"})
                        return True
                    import re as _re
                    ok_msg, msg = _sysdb_validate(sql)
                    if not ok_msg:
                        handler._send_json(400, {"error": msg})
                        return True
                    try:
                        rows = sqlitedb.query(sql)
                        handler._send_json(200, {"rows": rows})
                        handler._audit_action("sysdb_query", sql[:120].replace("\n", " "))
                    except Exception as e:
                        handler._send_json(400, {"error": _safe_error_short(e)})
                    return True
    if path == "/api/tasks":
                    # 新建调度任务(P2-2)
                    b = handler._body()
                    d = task_sched.add_task(b.get("name", "task"), b.get("conn_name", ""),
                                            b.get("interval_min", 60), b.get("action", "backup"))
                    handler._send_json(200, d)
                    handler._audit_action( "task_add", d.get("name", ""))
                    return True
    if path == "/api/tasks/delete":
                    b = handler._body()
                    task_sched.delete_task(int(b.get("id", 0)))
                    handler._send_json(200, {"ok": True})
                    handler._audit_action( "task_del", str(b.get("id", 0)))
                    return True
    if path == "/api/tasks/toggle":
                    b = handler._body()
                    task_sched.toggle_task(int(b.get("id", 0)), bool(b.get("enabled")))
                    handler._send_json(200, {"ok": True})
                    handler._audit_action( "task_toggle", "%s enabled=%s" % (b.get("id", 0), b.get("enabled")))
                    return True
    if path == "/api/tasks/run":
                    # 手动立即执行一次
                    b = handler._body()
                    handler._send_json(200, task_sched.run_now(int(b.get("id", 0))))
                    return True
    if path == "/api/shutdown":
                    if not handler._require_admin():   # 关停服务仅限管理员(DoS防护)
                        return True
                    handler._send_json(200, {"ok": True, "msg": "服务已停止"})
                    def _sd():
                        srvs = config.SERVERS if isinstance(config.SERVERS, list) else [config.SERVERS]
                        for s in srvs:
                            try:
                                s.shutdown()
                            except Exception:
                                pass
                    threading.Thread(target=_sd, daemon=True).start()
                    return True
    if path == "/api/config/settings":
                    # 服务器配置保存(管理界面用): 仅 admin + 审计
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    b = handler._body()
                    if not isinstance(b, dict) or "sections" not in b:
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    ok, msg, restart_keys = _write_settings(b.get("sections") or {})
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg,
                                                 "restart_required": bool(restart_keys),
                                                 "restart_keys": restart_keys})
                        handler._audit_action("config_update", msg)
                    else:
                        handler._send_json(400, {"error": msg})
                    return True
    if path == "/api/config/restart":
                    # 一键重启服务(使 host/port/ssl 等启动期配置生效): 仅 admin + 审计
                    if handler._auth_blocked():
                        return True
                    if not handler._require_admin():
                        return True
                    ok, msg = _restart_server()
                    if ok:
                        handler._send_json(200, {"ok": True, "message": msg})
                        handler._audit_action("config_restart", msg)
                    else:
                        handler._send_json(500, {"error": msg})
                    return True
    return False
