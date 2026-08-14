# -*- coding: utf-8 -*-
"""dbmanager - routes.query: 查询与数据: 分页浏览/SQL控制台/行增改删/事务/统计/造数/同步"""



from ops import (
    commit_transaction, explain_query,
    gen_data, get_data,
    mutate, mutate_batch_delete, rollback_transaction, run_sql,
    stats_column, sync_table, transfer_data,
)
from store import (
    get_connection_by_name,
)


def handle_get(handler, path, q):
    """GET 路由: 已处理返回 True, 否则 False"""
    if path == "/api/data":
                    conn = handler._resolve_conn()
                    handler._send_json(200, get_data(conn, q.get("s", [""])[0], q.get("t", [""])[0],
                                                  q.get("page", ["1"])[0],
                                                  q.get("size", ["100"])[0],
                                                  q.get("where", [""])[0],
                                                  q.get("order", [""])[0]))
                    return True
    return False

def handle_post(handler, path, q):
    """POST 路由: 已处理返回 True, 否则 False"""
    if path == "/api/stats":
                    # 列统计: COUNT/MIN/MAX + 数值列 SUM/AVG
                    conn = handler._resolve_conn()
                    b = handler._body()
                    s = (b.get("s") or "") if isinstance(b, dict) else ""
                    t2 = (b.get("t") or "") if isinstance(b, dict) else ""
                    col = (b.get("col") or "") if isinstance(b, dict) else ""
                    where = (b.get("where") or "") if isinstance(b, dict) else ""
                    if not t2 or not col:
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    import re as _re
                    if not _re.match(r"^[A-Za-z0-9_\u4e00-\u9fff]+$", col):
                        handler._send_json(400, {"error": "非法列名"})
                        return True
                    handler._send_json(200, stats_column(conn, s, t2, col, where))
                    return True
    if path == "/api/transfer":
                    # 数据级同步: 源表数据流式传输到目标表(同连接/跨库, 写操作)
                    conn = handler._resolve_conn()
                    b = handler._body()
                    if not isinstance(b, dict):
                        handler._send_json(400, {"error": "参数错误"})
                        return True
                    d = transfer_data(conn, b.get("s", ""), b.get("t", ""),
                                      b.get("to_db", ""), b.get("to_s", ""), b.get("to_t", ""))
                    handler._send_json(200, d)
                    handler._audit_action("transfer",
                                       "%s.%s -> %s.%s (%d 行)" % (b.get("s", ""), b.get("t", ""),
                                                                    b.get("to_db", ""), b.get("to_t", ""),
                                                                    d.get("transferred", 0)))
                    return True
    if path == "/api/gen-data":
                    # 生成测试数据(写操作, 仅 write 角色)
                    conn = handler._resolve_conn()
                    b = handler._body()
                    s = (b.get("s") or "") if isinstance(b, dict) else ""
                    t2 = (b.get("t") or "") if isinstance(b, dict) else ""
                    rows = int((b.get("rows") or 100)) if isinstance(b, dict) else 100
                    handler._send_json(200, gen_data(conn, s, t2, rows))
                    return True
    if path == "/api/explain":
                    # 执行计划: EXPLAIN sql 的可视化数据
                    b = handler._body()
                    conn = handler._resolve_conn()
                    if b.get("database"):
                        conn = dict(conn)
                        conn["database"] = b["database"]
                    handler._send_json(200, explain_query(conn, b.get("sql", "")))
                    return True
    if path == "/api/sql":
                    b = handler._body()
                    conn = handler._resolve_conn()
                    if b.get("database"):
                        # 连接内选库: 仅本次请求临时切库(换引擎走新库连接), 不改变会话
                        conn = dict(conn)
                        conn["database"] = b["database"]
                    write = bool(b.get("write"))
                    if write and conn.get("mode") == "read_only":
                        handler._send_json(403, {"error": "该连接已标记为只读(生产库保护), 禁止写操作"})
                        return True
                    if write and not handler._require_write():
                        return True  # read 角色仅可执行只读 SQL, 写模式需 write/admin
                    d = run_sql(conn, b.get("sql", ""), b.get("limit", 500), write)
                    handler._send_json(200, d)
                    if write:
                        handler._audit_action( "sql_write",
                               "[%s] %s" % (conn.get("database", ""),
                                            (b.get("sql") or "")[:200].replace("\n", " ")))
                    return True
    if path == "/api/sync":
                    b = handler._body()
                    src = b.get("src") or {}
                    dst = b.get("dst") or {}
                    if src.get("name"):
                        src = get_connection_by_name(src["name"])
                    if dst.get("name"):
                        dst = get_connection_by_name(dst["name"])
                    d = sync_table(src, dst, b.get("schema"), b.get("table"),
                                   b.get("mode", "append"))
                    handler._send_json(200, d)
                    handler._audit_action( "sync",
                           "%s.%s -> %s (%s)" % (b.get("schema", ""), b.get("table", ""),
                                                 dst.get("database", ""), b.get("mode", "append")))
                    return True
    if path == "/api/row":
                    conn = handler._resolve_conn()
                    b = handler._body()
                    use_tx = b.get("transaction", False)
                    d = mutate(conn, "POST", b["s"], b["t"], b, use_tx, b.get("tx_id", ""))
                    handler._send_json(200, d)
                    handler._audit_action( "row_insert", "%s.%s" % (b["s"], b["t"]))
                    return True
    if path == "/api/rows/delete":
                    # 批量删除(P1-9): keys=主键值数组, 单请求删除多行(前端原 N 次串行 DELETE /api/row)
                    conn = handler._resolve_conn()
                    b = handler._body()
                    keys = b.get("keys") or []
                    if not keys or len(keys) > 5000:
                        handler._send_json(400, {"error": "keys 需为 1-5000 条主键数组"})
                        return True
                    use_tx = b.get("transaction", False)
                    d = mutate_batch_delete(conn, b["s"], b["t"], keys, use_tx, b.get("tx_id", ""))
                    handler._send_json(200, d)
                    handler._audit_action( "row_delete_batch", "%s.%s x%d" % (b["s"], b["t"], len(keys)))
                    return True
    if path == "/api/transaction/commit":
                    conn = handler._resolve_conn()
                    b = handler._body()
                    commit_transaction(conn, b.get("tx_id", ""))
                    handler._send_json(200, {"ok": True})
                    return True
    if path == "/api/transaction/rollback":
                    conn = handler._resolve_conn()
                    b = handler._body()
                    rollback_transaction(conn, b.get("tx_id", ""))
                    handler._send_json(200, {"ok": True})
                    return True
    return False
