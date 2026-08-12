# -*- coding: utf-8 -*-
"""dbmanager - routes.routines: 存储过程: 列表/源码/参数/保存重建/删除/执行"""
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
    if path == "/api/routines":
                    # 存储过程/函数/触发器列表
                    conn = handler._resolve_conn()
                    schema = q.get("schema", [""])[0] or None
                    handler._send_json(200, {"routines": get_routines(conn, schema)})
                    return True
    if path == "/api/routine/source":
                    conn = handler._resolve_conn()
                    src = get_routine_source(conn, q.get("s", [""])[0], q.get("name", [""])[0],
                                             q.get("kind", ["Procedure"])[0])
                    handler._send_json(200, {"source": src})
                    return True
    if path == "/api/routine/params":
                    conn = handler._resolve_conn()
                    ps = get_routine_params(conn, q.get("s", [""])[0], q.get("name", [""])[0],
                                            q.get("kind", ["Procedure"])[0])
                    handler._send_json(200, {"params": ps})
                    return True
    return False

def handle_post(handler, path, q):
    """POST 路由: 已处理返回 True, 否则 False"""
    if path == "/api/routine/save":
                    b = handler._body()
                    conn = handler._resolve_conn()
                    d = save_routine(conn, b.get("s"), b.get("name"), b.get("kind", "Procedure"), b.get("source", ""))
                    handler._send_json(200, d)
                    handler._audit_action( "routine_save", "%s.%s %s" % (b.get("s", ""), b.get("name", ""), b.get("kind", "")))
                    return True
    if path == "/api/routine/drop":
                    b = handler._body()
                    conn = handler._resolve_conn()
                    d = drop_routine(conn, b.get("s"), b.get("name"), b.get("kind", "Procedure"))
                    handler._send_json(200, d)
                    handler._audit_action( "routine_drop", "%s.%s %s" % (b.get("s", ""), b.get("name", ""), b.get("kind", "")))
                    return True
    if path == "/api/routine/execute":
                    b = handler._body()
                    conn = handler._resolve_conn()
                    handler._send_json(200, execute_routine(conn, b.get("s"), b.get("name"),
                                                         b.get("kind", "Procedure"), b.get("params") or {}))
                    return True
    return False
