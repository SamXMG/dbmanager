# -*- coding: utf-8 -*-
"""dbmanager - routes.files: 文件: 导入导出/备份还原"""
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
    if path == "/api/export":
                    conn = handler._resolve_conn()
                    content, ctype, filename = export_data(conn, q.get("s", [""])[0], q.get("t", [""])[0],
                                                           q.get("where", [""])[0],
                                                           q.get("fmt", ["csv"])[0])
                    handler.send_response(200)
                    handler.send_header("Content-Type", ctype)
                    handler.send_header("Content-Disposition",
                                     'attachment; filename="%s"' % filename)
                    origin = handler.headers.get("Origin")
                    if origin and handler._origin_allowed(origin):
                        handler.send_header("Access-Control-Allow-Origin", origin)
                    handler.end_headers()
                    # xlsx 为二进制 bytes, 其余为 str
                    handler.wfile.write(content if isinstance(content, bytes) else content.encode("utf-8"))
                    return True
    if path == "/api/export/schema":
                    conn = handler._resolve_conn()
                    table = q.get("table", [""])[0] or None
                    md = export_schema_doc(conn, table)
                    filename = (table or "data_dictionary") + ".md"
                    handler.send_response(200)
                    handler.send_header("Content-Type", "text/markdown; charset=utf-8")
                    handler.send_header("Content-Disposition",
                                     'attachment; filename="%s"' % filename)
                    origin = handler.headers.get("Origin")
                    if origin and handler._origin_allowed(origin):
                        handler.send_header("Access-Control-Allow-Origin", origin)
                    handler.end_headers()
                    handler.wfile.write(md.encode("utf-8"))
                    return True
    if path == "/api/backup":
                    # 整库备份: 生成 CREATE TABLE + INSERT 的 SQL 脚本下载
                    conn = handler._resolve_conn()
                    schema = q.get("schema", [""])[0] or None
                    content, filename = backup_database(conn, schema)
                    handler.send_response(200)
                    handler.send_header("Content-Type", "application/sql; charset=utf-8")
                    handler.send_header("Content-Disposition",
                                     'attachment; filename="%s"' % filename)
                    origin = handler.headers.get("Origin")
                    if origin and handler._origin_allowed(origin):
                        handler.send_header("Access-Control-Allow-Origin", origin)
                    handler.end_headers()
                    handler.wfile.write(content.encode("utf-8"))
                    handler._audit_action( "backup", "%s (%d 字符)" % (conn.get("database", ""), len(content)))
                    return True
    return False

def handle_post(handler, path, q):
    """POST 路由: 已处理返回 True, 否则 False"""
    if path == "/api/export/sql":
                    # SQL 查询结果导出: POST {columns:[{name}], rows:[{...}]} -> xlsx 下载
                    b = handler._body()
                    cols = [c.get("name", "col%d" % i) for i, c in enumerate(b.get("columns") or [])]
                    rows = b.get("rows") or []
                    content = _xlsx_bytes(cols, rows)
                    handler.send_response(200)
                    handler.send_header("Content-Type",
                                     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                    handler.send_header("Content-Disposition",
                                     'attachment; filename="query_result.xlsx"')
                    origin = handler.headers.get("Origin")
                    if origin and handler._origin_allowed(origin):
                        handler.send_header("Access-Control-Allow-Origin", origin)
                    handler.end_headers()
                    handler.wfile.write(content)
                    return True
    if path == "/api/import/xlsx":
                    # 解析 xlsx 文件(原始二进制 body) -> {header, rows}, 供前端列映射后走 /api/import
                    n = int(handler.headers.get("Content-Length", 0))
                    if n > 100 * 1024 * 1024:   # P2-2: 请求体硬上限, 防内存耗尽 DoS
                        handler._send_json(413, {"error": "请求体超过大小上限(100MB)"})
                        return True
                    raw = handler.rfile.read(n) if n else b""
                    try:
                        header, rows = parse_xlsx_import(raw)
                        handler._send_json(200, {"header": header, "rows": rows})
                    except Exception as e:
                        handler._send_json(400, {"error": str(e)})
                    return True
    if path == "/api/restore":
                    # 还原: 执行上传的备份 SQL 脚本(危险操作, 前端已确认)
                    b = handler._body()
                    conn = handler._resolve_conn()
                    d = restore_sql(conn, b.get("sql", ""))
                    handler._send_json(200, d)
                    handler._audit_action( "restore",
                           "%s (成功%d/失败%d)" % (conn.get("database", ""),
                                                  len(d.get("executed") or []), len(d.get("failed") or [])))
                    return True
    if path == "/api/import":
                    b = handler._body()
                    conn = handler._resolve_conn()
                    d = import_data(conn, b.get("s"), b.get("t"),
                                    b.get("columns") or [], b.get("rows") or [],
                                    b.get("transaction", False), b.get("tx_id", ""))
                    handler._send_json(200, d)
                    handler._audit_action( "import",
                           "%s.%s %d 行" % (b.get("s", ""), b.get("t", ""), len(b.get("rows") or [])))
                    return True
    return False
