# -*- coding: utf-8 -*-
"""dbmanager - routes.admin: 管理: 登录/用户/网关/调度任务/关机"""
import json
import os
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
    return False
