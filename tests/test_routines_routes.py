# -*- coding: utf-8 -*-
"""routes/routines 单元测试: 存储过程相关 GET/POST 路由 (FakeHandler 驱动, 桩 services)."""
import pytest
from unittest.mock import MagicMock

from routes import routines as rrt


class FakeHandler:
    def __init__(self, conn=None, body=None):
        self._conn_data = conn
        self._body_data = body
        self.sent = []
        self.audits = []

    def _resolve_conn(self):
        return self._conn_data

    def _body(self):
        return self._body_data or {}

    def _send_json(self, code, payload):
        self.sent.append((code, payload))
        return True

    def _audit_action(self, action, detail):
        self.audits.append((action, detail))
        return True


def _q(**kv):
    return {k: [v] for k, v in kv.items()}


def test_handle_get_routines(monkeypatch):
    monkeypatch.setattr(rrt, "get_routines", lambda conn, schema: [{"name": "p1", "type": "Procedure"}])
    h = FakeHandler(conn={"db_type": "mysql"})
    assert rrt.handle_get(h, "/api/routines", _q(schema="s1")) is True
    assert h.sent[-1][1]["routines"] == [{"name": "p1", "type": "Procedure"}]


def test_handle_get_source(monkeypatch):
    monkeypatch.setattr(rrt, "get_routine_source", lambda conn, s, n, k: "CREATE PROCEDURE p1")
    h = FakeHandler(conn={"db_type": "mysql"})
    assert rrt.handle_get(h, "/api/routine/source", _q(s="s1", name="p1", kind="Procedure")) is True
    assert h.sent[-1][1]["source"] == "CREATE PROCEDURE p1"


def test_handle_get_params(monkeypatch):
    monkeypatch.setattr(rrt, "get_routine_params", lambda conn, s, n, k: [{"name": "a", "mode": "IN", "type": "int"}])
    h = FakeHandler(conn={"db_type": "mysql"})
    assert rrt.handle_get(h, "/api/routine/params", _q(s="s1", name="p1", kind="Procedure")) is True
    assert h.sent[-1][1]["params"] == [{"name": "a", "mode": "IN", "type": "int"}]


def test_handle_get_unknown(monkeypatch):
    h = FakeHandler(conn={"db_type": "mysql"})
    assert rrt.handle_get(h, "/api/nope", _q()) is False


def test_handle_post_save(monkeypatch):
    captured = {}
    def _save(conn, s, name, kind, source):
        captured.update(conn=conn, s=s, name=name, kind=kind, source=source)
        return {"ok": True}
    monkeypatch.setattr(rrt, "save_routine", _save)
    body = {"s": "s1", "name": "p1", "kind": "Procedure", "source": "CREATE PROCEDURE p1"}
    h = FakeHandler(conn={"db_type": "mysql"}, body=body)
    assert rrt.handle_post(h, "/api/routine/save", {}) is True
    assert captured["name"] == "p1"
    assert h.sent[-1][1] == {"ok": True}
    assert h.audits[-1][0] == "routine_save"


def test_handle_post_drop(monkeypatch):
    captured = {}
    def _drop(conn, s, name, kind):
        captured.update(conn=conn, s=s, name=name, kind=kind)
        return {"ok": True}
    monkeypatch.setattr(rrt, "drop_routine", _drop)
    body = {"s": "s1", "name": "p1", "kind": "Procedure"}
    h = FakeHandler(conn={"db_type": "mysql"}, body=body)
    assert rrt.handle_post(h, "/api/routine/drop", {}) is True
    assert captured["name"] == "p1"
    assert h.audits[-1][0] == "routine_drop"


def test_handle_post_execute(monkeypatch):
    monkeypatch.setattr(rrt, "execute_routine",
                        lambda conn, s, name, kind, params: {"rows": [], "affected": 0})
    body = {"s": "s1", "name": "p1", "kind": "Procedure", "params": {"x": 1}}
    h = FakeHandler(conn={"db_type": "mysql"}, body=body)
    assert rrt.handle_post(h, "/api/routine/execute", {}) is True
    assert h.sent[-1][1] == {"rows": [], "affected": 0}


def test_handle_post_unknown(monkeypatch):
    h = FakeHandler(conn={"db_type": "mysql"}, body={})
    assert rrt.handle_post(h, "/api/nope", {}) is False
