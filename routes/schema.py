# -*- coding: utf-8 -*-
"""dbmanager - routes.schema: 结构: 表列索引/关系/ER/改表/对象/用户权限/结构对比"""
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
    if path == "/api/tables":
                    conn = handler._resolve_conn()
                    # 表级权限过滤: 只返回用户有权限的表(白名单/黑名单), 对象树所见即所得
                    handler._send_json(200, handler._filter_tables(get_tables(conn)))
                    return True
    if path == "/api/columns":
                    conn = handler._resolve_conn()
                    handler._send_json(200, get_columns(conn, q.get("s", [""])[0], q.get("t", [""])[0]))
                    return True
    if path == "/api/indexes":
                    conn = handler._resolve_conn()
                    handler._send_json(200, get_indexes(conn, q.get("s", [""])[0], q.get("t", [""])[0]))
                    return True
    if path == "/api/er":
                    # ER 图: 中心表 + 直接外键关联表结构
                    conn = handler._resolve_conn()
                    handler._send_json(200, get_er_data(conn, q.get("s", [""])[0], q.get("t", [""])[0]))
                    return True
    if path == "/api/relations":
                    conn = handler._resolve_conn()
                    handler._send_json(200, get_relations(conn, q.get("s", [""])[0], q.get("t", [""])[0]))
                    return True
    if path == "/api/db-users":
                    # DB 用户与权限只读视图(四方言): 原 /api/users 与账号管理冲突不可达, 独立路由
                    conn = handler._resolve_conn()
                    handler._send_json(200, get_users_privs(conn))
                    return True
    return False

def handle_post(handler, path, q):
    """POST 路由: 已处理返回 True, 否则 False"""
    if path == "/api/objects":
                    # Navicat 风格树: 按库取该库的表/视图/存储过程/函数/触发器(临时换 database, 不改会话)
                    conn = handler._resolve_conn()
                    b = handler._body()
                    db = (b.get("database") or "").strip() if isinstance(b, dict) else ""
                    ci = dict(conn)
                    # sqlite 的 database 是文件路径(非库名), 忽略换库参数
                    if db and ci.get("db_type") != "sqlite":
                        ci["database"] = db
                    handler._send_json(200, {"tables": get_tables(ci), "routines": get_routines(ci)})
                    return True
    if path == "/api/alter":
                    b = handler._body()
                    conn = handler._resolve_conn()
                    d = alter_table(conn, b.get("s"), b.get("t"),
                                    b.get("action"), b.get("payload") or {},
                                    b.get("tx_id", ""))
                    handler._send_json(200, d)
                    handler._audit_action( "alter",
                           "%s.%s %s" % (b.get("s", ""), b.get("t", ""), b.get("action", "")))
                    return True
    if path == "/api/schema/diff":
                    # 表结构对比: src(默认当前会话连接) -> dst 差异清单
                    b = handler._body()
                    src, dst = b.get("src") or {}, b.get("dst") or {}
                    if src.get("name"):
                        src = get_connection_by_name(src["name"])
                    elif not src:
                        src = handler._resolve_conn()
                    if dst.get("name"):
                        dst = get_connection_by_name(dst["name"])
                    handler._send_json(200, {"diffs": diff_schema(src, dst, b.get("schema") or None,
                                                               b.get("table") or None)})
                    return True
    if path == "/api/schema/sync":
                    # 执行结构同步: 目标连接逐条执行前端确认过的 DDL
                    b = handler._body()
                    dst = b.get("dst") or {}
                    if dst.get("name"):
                        dst = get_connection_by_name(dst["name"])
                    handler._send_json(200, execute_schema_sync(dst, b.get("sqls") or []))
                    return True
    return False
