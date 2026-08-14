# -*- coding: utf-8 -*-
"""routes/query 单测(M2-4): 用假 handler 驱动 handle_get/handle_post, 桩掉 ops/*。
验证路由分发、参数解析与错误分支(只读限制/缺参/越界), 不连真库。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import routes.query as rq


class FakeHandler:
    def __init__(self, body=None, conn=None, require_write=True):
        self._body_data = body if body is not None else {}
        self._conn = conn if conn is not None else {"db_type": "mysql"}
        self._require_write_flag = require_write
        self.sent = []
        self.audits = []

    def _resolve_conn(self):
        return self._conn

    def _body(self):
        return self._body_data

    def _send_json(self, code, obj):
        self.sent.append((code, obj))
        return 0

    def _require_write(self):
        return self._require_write_flag

    def _audit_action(self, action, detail):
        self.audits.append((action, detail))

    def _last(self):
        return self.sent[-1] if self.sent else (None, None)


# 桩 ops / store 中的具体函数, 返回占位结果
def _const(val):
    def _f(*a, **k):
        return val
    return _f


def _patch_ops(monkeypatch):
    stubs = {
        "get_data": {"rows": [], "total": 0, "pk": []},
        "stats_column": {"count": 1},
        "transfer_data": {"transferred": 5},
        "gen_data": {"inserted": 3},
        "explain_query": {"mode": "table"},
        "run_sql": {"ok": True, "results": []},
        "sync_table": {"ok": True},
        "mutate": {"ok": True, "affected": 1},
        "mutate_batch_delete": {"ok": True, "affected": 2},
        "commit_transaction": True,
        "rollback_transaction": True,
        "get_connection_by_name": {"db_type": "mysql", "name": "x"},
    }
    for name, val in stubs.items():
        monkeypatch.setattr(rq, name, _const(val))


# ==================== GET ====================
def test_get_data(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    q = {"s": ["db"], "t": ["tbl"], "page": ["2"], "size": ["50"],
         "where": ["x=1"], "order": ["id:desc"]}
    assert rq.handle_get(h, "/api/data", q) is True
    code, obj = h._last()
    assert code == 200 and obj["total"] == 0


def test_get_unknown_path(monkeypatch):
    h = FakeHandler()
    assert rq.handle_get(h, "/api/nope", {}) is False


# ==================== POST ====================
def test_post_stats_ok(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "db", "t": "t", "col": "age", "where": "x=1"})
    assert rq.handle_post(h, "/api/stats", {}) is True
    assert h._last()[0] == 200


def test_post_stats_missing(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "db"})
    rq.handle_post(h, "/api/stats", {})
    assert h._last()[0] == 400


def test_post_stats_bad_col(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "db", "t": "t", "col": "a;b"})
    rq.handle_post(h, "/api/stats", {})
    assert h._last()[0] == 400


def test_post_transfer(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "to_db": "d", "to_s": "s2", "to_t": "t2"})
    rq.handle_post(h, "/api/transfer", {})
    assert h._last()[0] == 200
    assert h.audits and h.audits[0][0] == "transfer"


def test_post_transfer_nondict(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body=["not", "a", "dict"])
    rq.handle_post(h, "/api/transfer", {})
    assert h._last()[0] == 400


def test_post_sql_database_switch(monkeypatch):
    captured = {}
    def _run_sql(conn, sql, limit=500, write=False):
        captured["conn"] = conn
        return {"ok": True, "results": []}
    monkeypatch.setattr(rq, "run_sql", _run_sql)
    h = FakeHandler(body={"sql": "SELECT 1", "database": "db2", "write": False})
    rq.handle_post(h, "/api/sql", {})
    assert h._last()[0] == 200
    assert captured["conn"].get("database") == "db2"


def test_post_gen_data(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "rows": 10})
    rq.handle_post(h, "/api/gen-data", {})
    assert h._last()[0] == 200


def test_post_explain(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"sql": "SELECT 1", "database": "db2"})
    rq.handle_post(h, "/api/explain", {})
    assert h._last()[0] == 200


def test_post_sql_read(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"sql": "SELECT 1", "write": False})
    rq.handle_post(h, "/api/sql", {})
    assert h._last()[0] == 200


def test_post_sql_write_readonly_conn(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"sql": "DELETE FROM t", "write": True},
                    conn={"db_type": "mysql", "mode": "read_only"})
    rq.handle_post(h, "/api/sql", {})
    assert h._last()[0] == 403


def test_post_sql_write_no_permission(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"sql": "DELETE FROM t", "write": True},
                    require_write=False)
    rq.handle_post(h, "/api/sql", {})
    # 无写权限: 不发响应, 直接 return True
    assert h.sent == []


def test_post_sql_write_ok(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"sql": "DELETE FROM t", "write": True},
                    require_write=True)
    rq.handle_post(h, "/api/sql", {})
    assert h._last()[0] == 200
    assert h.audits and h.audits[0][0] == "sql_write"


def test_post_sync_by_dict(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"src": {"db_type": "mysql"}, "dst": {"db_type": "mysql"},
                          "schema": "s", "table": "t", "mode": "append"})
    rq.handle_post(h, "/api/sync", {})
    assert h._last()[0] == 200
    assert h.audits and h.audits[0][0] == "sync"


def test_post_sync_by_name(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"src": {"name": "a"}, "dst": {"name": "b"},
                          "schema": "s", "table": "t"})
    rq.handle_post(h, "/api/sync", {})
    assert h._last()[0] == 200


def test_post_row_insert(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "values": {"x": 1}, "orig": {}})
    rq.handle_post(h, "/api/row", {})
    assert h._last()[0] == 200
    assert h.audits and h.audits[0][0] == "row_insert"


def test_post_rows_delete_ok(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "keys": [1, 2, 3]})
    rq.handle_post(h, "/api/rows/delete", {})
    assert h._last()[0] == 200


def test_post_rows_delete_empty_keys(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "keys": []})
    rq.handle_post(h, "/api/rows/delete", {})
    assert h._last()[0] == 400


def test_post_rows_delete_too_many_keys(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "keys": list(range(5001))})
    rq.handle_post(h, "/api/rows/delete", {})
    assert h._last()[0] == 400


def test_post_transaction_commit(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"tx_id": "tx1"})
    rq.handle_post(h, "/api/transaction/commit", {})
    assert h._last()[0] == 200


def test_post_transaction_rollback(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"tx_id": "tx1"})
    rq.handle_post(h, "/api/transaction/rollback", {})
    assert h._last()[0] == 200


def test_post_unknown_path(monkeypatch):
    h = FakeHandler()
    assert rq.handle_post(h, "/api/nope", {}) is False
