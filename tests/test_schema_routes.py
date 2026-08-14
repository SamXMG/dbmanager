# -*- coding: utf-8 -*-
"""routes/schema 单测(M2-4): 用假 handler 驱动 handle_get/handle_post, 桩掉 ops/*。
覆盖表/列/索引/关系/ER/权限/改表/结构对比与同步路由。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import routes.schema as rs


class FakeHandler:
    def __init__(self, body=None, conn=None):
        self._body_data = body if body is not None else {}
        self._conn = conn if conn is not None else {"db_type": "mysql"}
        self.sent = []
        self.audits = []

    def _resolve_conn(self):
        return self._conn

    def _body(self):
        return self._body_data

    def _send_json(self, code, obj):
        self.sent.append((code, obj))
        return 0

    def _filter_tables(self, tables):
        return tables

    def _audit_action(self, action, detail):
        self.audits.append((action, detail))

    def _last(self):
        return self.sent[-1] if self.sent else (None, None)


def _const(val):
    def _f(*a, **k):
        return val
    return _f


def _patch_ops(monkeypatch):
    stubs = {
        "get_tables": [{"name": "t", "type": "Table", "schema": "s"}],
        "get_columns": [{"name": "id", "type": "INT"}],
        "get_indexes": [{"name": "ix"}],
        "get_er_data": {"tables": [], "relations": []},
        "get_relations": [{"direction": "out"}],
        "get_users_privs": {"supported": True, "logins": []},
        "get_routines": [{"name": "p1", "type": "PROCEDURE"}],
        "alter_table": {"ok": True},
        "diff_schema": [{"type": "add"}],
        "execute_schema_sync": {"ok": True, "applied": 1},
        "get_connection_by_name": {"db_type": "mysql", "name": "x"},
    }
    for name, val in stubs.items():
        monkeypatch.setattr(rs, name, _const(val))


# ==================== GET ====================
def test_get_tables(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    assert rs.handle_get(h, "/api/tables", {}) is True
    assert h._last()[0] == 200


def test_get_columns(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    assert rs.handle_get(h, "/api/columns", {"s": ["s"], "t": ["t"]}) is True
    assert h._last()[0] == 200


def test_get_indexes(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    assert rs.handle_get(h, "/api/indexes", {"s": ["s"], "t": ["t"]}) is True
    assert h._last()[0] == 200


def test_get_er(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    assert rs.handle_get(h, "/api/er", {"s": ["s"], "t": ["t"]}) is True
    assert h._last()[0] == 200


def test_get_relations(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    assert rs.handle_get(h, "/api/relations", {"s": ["s"], "t": ["t"]}) is True
    assert h._last()[0] == 200


def test_get_db_users(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler()
    assert rs.handle_get(h, "/api/db-users", {}) is True
    assert h._last()[0] == 200


def test_get_unknown(monkeypatch):
    h = FakeHandler()
    assert rs.handle_get(h, "/api/nope", {}) is False


# ==================== POST ====================
def test_post_objects(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"database": "db2"})
    assert rs.handle_post(h, "/api/objects", {}) is True
    assert h._last()[0] == 200


def test_post_alter(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"s": "s", "t": "t", "action": "add_column",
                          "payload": {"name": "c"}, "tx_id": ""})
    assert rs.handle_post(h, "/api/alter", {}) is True
    assert h._last()[0] == 200
    assert h.audits and h.audits[0][0] == "alter"


def test_post_schema_diff_default_src(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"dst": {"name": "x"}, "schema": "s", "table": "t"})
    assert rs.handle_post(h, "/api/schema/diff", {}) is True
    assert h._last()[0] == 200


def test_post_schema_diff_by_name(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"src": {"name": "x"}, "dst": {"name": "y"}})
    assert rs.handle_post(h, "/api/schema/diff", {}) is True
    assert h._last()[0] == 200


def test_post_schema_sync(monkeypatch):
    _patch_ops(monkeypatch)
    h = FakeHandler(body={"dst": {"name": "x"}, "sqls": ["ALTER TABLE t ADD c INT"]})
    assert rs.handle_post(h, "/api/schema/sync", {}) is True
    assert h._last()[0] == 200


def test_post_unknown(monkeypatch):
    h = FakeHandler()
    assert rs.handle_post(h, "/api/nope", {}) is False
