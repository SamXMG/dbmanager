# -*- coding: utf-8 -*-
"""services/routines 单元测试: 存储过程/函数/触发器 列表/源码/参数/保存/删除/执行 (多方言, mock)."""
import pytest
from unittest.mock import MagicMock

from services import routines as rt


class _Maps:
    """模拟 sqlalchemy .mappings() 结果: 可迭代 + first/fetchall/fetchmany."""

    def __init__(self, rows):
        self.rows = list(rows)

    def __iter__(self):
        return iter(self.rows)

    def first(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows

    def fetchmany(self, n=None):
        return self.rows


def _result(rows=None, scalar=None, keys=None, rowcount=0, returns_rows=None):
    res = _Maps(rows) if rows is not None else None
    r = MagicMock()
    if res is not None:
        r.mappings.return_value = res
    else:
        r.mappings.return_value = _Maps([])
    r.scalar.return_value = scalar
    if keys is not None:
        r.keys.return_value = keys
    elif rows:
        first = rows[0]
        r.keys.return_value = [list(first.keys())[0]] if isinstance(first, dict) else []
    else:
        r.keys.return_value = []
    r.returns_rows = bool(rows) if returns_rows is None else returns_rows
    r.rowcount = rowcount
    return r


def _make_engine():
    """返回 (eng, conn), conn 为 with 协议内绑定的连接 mock."""
    eng = MagicMock()
    conn = MagicMock()
    eng.connect.return_value.__enter__.return_value = conn
    eng.connect.return_value.__exit__.return_value = False
    return eng, conn


@pytest.fixture
def _patch_engine(monkeypatch):
    eng, conn = _make_engine()
    monkeypatch.setattr(rt, "get_engine", lambda ci: eng)
    return eng, conn


# ---------- get_routines ----------

def test_get_routines_mysql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(rows=[{"ROUTINE_SCHEMA": "db1", "ROUTINE_NAME": "p1", "ROUTINE_TYPE": "PROCEDURE"},
                      {"ROUTINE_SCHEMA": "db1", "ROUTINE_NAME": "f1", "ROUTINE_TYPE": "FUNCTION"}]),
        _result(rows=[{"Trigger": "t1"}]),
    ]
    out = rt.get_routines({"db_type": "mysql", "database": "db1"})
    assert {"schema": "db1", "name": "p1", "type": "Procedure"} in out
    assert {"schema": "db1", "name": "f1", "type": "Function"} in out
    assert {"schema": "db1", "name": "t1", "type": "Trigger"} in out


def test_get_routines_mysql_trigger_error(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(rows=[{"ROUTINE_SCHEMA": "db1", "ROUTINE_NAME": "p1", "ROUTINE_TYPE": "PROCEDURE"}]),
        Exception("no triggers"),
    ]
    out = rt.get_routines({"db_type": "mysql", "database": "db1"})
    # trigger 分支异常被吞, 仍返回 procedure
    assert out == [{"schema": "db1", "name": "p1", "type": "Procedure"}]


def test_get_routines_postgresql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(rows=[{"schema": "public", "name": "p1", "type": "Procedure"},
                      {"schema": "public", "name": "f1", "type": "Function"}]),
    ]
    out = rt.get_routines({"db_type": "postgresql"})
    assert {"schema": "public", "name": "p1", "type": "Procedure"} in out
    assert {"schema": "public", "name": "f1", "type": "Function"} in out


def test_get_routines_mssql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(rows=[{"schema": "dbo", "name": "p1", "type": "P"},
                      {"schema": "dbo", "name": "f1", "type": "FN"},
                      {"schema": "dbo", "name": "x1", "type": "X"}]),  # X 映射为 None 被跳过
        _result(rows=[{"schema": "dbo", "name": "t1"}]),
    ]
    out = rt.get_routines({"db_type": "mssql"})
    types = {o["name"]: o["type"] for o in out}
    assert types["p1"] == "Procedure"
    assert types["f1"] == "Function"
    assert "x1" not in types
    assert {"schema": "dbo", "name": "t1", "type": "Trigger"} in out


def test_get_routines_oracle(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(rows=[{"schema": "SCOTT", "name": "p1", "type": "Procedure"},
                      {"schema": "SCOTT", "name": "f1", "type": "Function"}]),
        _result(rows=[{"schema": "SCOTT", "name": "t1", "type": "Trigger"}]),
    ]
    out = rt.get_routines({"db_type": "oracle"})
    assert {"schema": "SCOTT", "name": "p1", "type": "Procedure"} in out
    assert {"schema": "SCOTT", "name": "t1", "type": "Trigger"} in out


def test_get_routines_engine_error(monkeypatch):
    def _boom(ci):
        raise RuntimeError("connect fail")
    monkeypatch.setattr(rt, "get_engine", _boom)
    assert rt.get_routines({"db_type": "mysql"}) == []


# ---------- get_routine_source ----------

def test_get_routine_source_mysql_procedure(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[{"Create Procedure": "CREATE PROCEDURE p1 ..."}])
    assert rt.get_routine_source({"db_type": "mysql"}, "db1", "p1", "Procedure") == "CREATE PROCEDURE p1 ..."


def test_get_routine_source_mysql_function(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[{"Create Function": "CREATE FUNCTION f1 ..."}])
    assert rt.get_routine_source({"db_type": "mysql"}, "db1", "f1", "Function") == "CREATE FUNCTION f1 ..."


def test_get_routine_source_mysql_trigger(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[{"SQL Original Statement": "CREATE TRIGGER t1 ..."}])
    assert rt.get_routine_source({"db_type": "mysql"}, "db1", "t1", "Trigger") == "CREATE TRIGGER t1 ..."


def test_get_routine_source_mysql_none(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[None])  # mappings().first() -> None
    assert rt.get_routine_source({"db_type": "mysql"}, "db1", "p1", "Procedure") == ""


def test_get_routine_source_postgresql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(scalar=12345),
        _result(scalar="CREATE FUNCTION p1() ..."),
    ]
    assert rt.get_routine_source({"db_type": "postgresql"}, "public", "p1", "Procedure") == "CREATE FUNCTION p1() ..."


def test_get_routine_source_postgresql_no_oid(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [_result(scalar=None), _result(scalar="x")]
    assert rt.get_routine_source({"db_type": "postgresql"}, "public", "p1", "Procedure") == ""


def test_get_routine_source_mssql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(scalar=999),
        _result(scalar="CREATE PROCEDURE p1 ..."),
    ]
    assert rt.get_routine_source({"db_type": "mssql"}, "dbo", "p1", "Procedure") == "CREATE PROCEDURE p1 ..."


def test_get_routine_source_oracle(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(scalar="CREATE PROCEDURE p1 ...")
    assert rt.get_routine_source({"db_type": "oracle"}, "SCOTT", "p1", "Procedure") == "CREATE PROCEDURE p1 ..."


def test_get_routine_source_oracle_trigger(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(scalar="CREATE TRIGGER t1 ...")
    assert rt.get_routine_source({"db_type": "oracle"}, "SCOTT", "t1", "Trigger") == "CREATE TRIGGER t1 ..."


# ---------- get_routine_params ----------

def test_get_routine_params_mysql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[
        {"PARAMETER_NAME": "a", "PARAMETER_MODE": "IN", "DATA_TYPE": "int", "ORDINAL_POSITION": 1},
        {"PARAMETER_NAME": "b", "PARAMETER_MODE": "OUT", "DATA_TYPE": "varchar", "ORDINAL_POSITION": 2},
        {"PARAMETER_NAME": None, "PARAMETER_MODE": "IN", "DATA_TYPE": "int", "ORDINAL_POSITION": 0},  # 跳过
    ])
    out = rt.get_routine_params({"db_type": "mysql", "database": "db1"}, "db1", "p1", "Procedure")
    assert {"name": "a", "mode": "IN", "type": "int"} in out
    assert {"name": "b", "mode": "OUT", "type": "varchar"} in out
    assert len(out) == 2


def test_get_routine_params_postgresql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(scalar=7),
        _result(scalar="arg1 integer, OUT x text, INOUT y numeric"),
    ]
    out = rt.get_routine_params({"db_type": "postgresql"}, "public", "p1", "Function")
    names = {p["name"]: p for p in out}
    assert names["arg1"] == {"name": "arg1", "mode": "IN", "type": "integer"}
    assert names["x"] == {"name": "x", "mode": "OUT", "type": "text"}
    assert names["y"] == {"name": "y", "mode": "INOUT", "type": "numeric"}


def test_get_routine_params_postgresql_no_oid(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [_result(scalar=None), _result(scalar="x")]
    assert rt.get_routine_params({"db_type": "postgresql"}, "public", "p1", "Function") == []


def test_get_routine_params_mssql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.side_effect = [
        _result(scalar=555),
        _result(rows=[
            {"name": "a", "is_output": False, "dtype": "int"},
            {"name": "b", "is_output": True, "dtype": "varchar"},
        ]),
    ]
    out = rt.get_routine_params({"db_type": "mssql"}, "dbo", "p1", "Procedure")
    assert {"name": "@a", "mode": "IN", "type": "int"} in out
    assert {"name": "@b", "mode": "OUT", "type": "varchar"} in out


def test_get_routine_params_engine_error(monkeypatch):
    def _boom(ci):
        raise RuntimeError("connect fail")
    monkeypatch.setattr(rt, "get_engine", _boom)
    assert rt.get_routine_params({"db_type": "mysql"}, "db1", "p1", "Procedure") == []


# ---------- save_routine ----------

def test_save_routine_empty_raises(_patch_engine):
    with pytest.raises(ValueError):
        rt.save_routine({"db_type": "mysql"}, "db1", "p1", "Procedure", "")


def test_save_routine_mysql(_patch_engine):
    eng, conn = _patch_engine
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur
    cur.__iter__.return_value = iter([None])
    eng.raw_connection.return_value = raw
    out = rt.save_routine({"db_type": "mysql"}, "db1", "p1", "Procedure", "CREATE PROCEDURE p1() BEGIN END")
    assert out == {"ok": True}
    assert cur.execute.called


def test_save_routine_mysql_strip_delimiter(_patch_engine):
    eng, conn = _patch_engine
    raw = MagicMock()
    cur = MagicMock()
    raw.cursor.return_value = cur
    cur.__iter__.return_value = iter([None])
    eng.raw_connection.return_value = raw
    src = "DELIMITER $$\nCREATE PROCEDURE p1() BEGIN END$$\nDELIMITER ;"
    out = rt.save_routine({"db_type": "mysql"}, "db1", "p1", "Procedure", src)
    assert out == {"ok": True}
    # 传给驱动执行的源码不应含 DELIMITER
    sent = cur.execute.call_args[0][0]
    assert "DELIMITER" not in sent


def test_save_routine_postgresql(_patch_engine):
    _, conn = _patch_engine
    out = rt.save_routine({"db_type": "postgresql"}, "public", "p1", "Procedure", "CREATE PROCEDURE p1() AS $$ BEGIN END $$")
    assert out == {"ok": True}
    assert conn.execute.called


def test_save_routine_mssql(_patch_engine):
    _, conn = _patch_engine
    out = rt.save_routine({"db_type": "mssql"}, "dbo", "p1", "Procedure", "CREATE PROCEDURE p1 AS BEGIN END")
    assert out == {"ok": True}
    assert conn.execute.called


# ---------- drop_routine ----------

def test_drop_routine_mysql(_patch_engine):
    _, conn = _patch_engine
    for kind in ("Procedure", "Function", "Trigger"):
        rt.drop_routine({"db_type": "mysql"}, "db1", "p1", kind)
    assert conn.execute.call_count == 3


def test_drop_routine_postgresql(_patch_engine):
    _, conn = _patch_engine
    rt.drop_routine({"db_type": "postgresql"}, "public", "p1", "Trigger")
    rt.drop_routine({"db_type": "postgresql"}, "public", "p1", "Function")
    assert conn.execute.call_count == 2


def test_drop_routine_mssql(_patch_engine):
    _, conn = _patch_engine
    rt.drop_routine({"db_type": "mssql"}, "dbo", "p1", "Procedure")
    rt.drop_routine({"db_type": "mssql"}, "dbo", "p1", "Function")
    assert conn.execute.call_count == 2


# ---------- execute_routine ----------

def test_execute_routine_mysql_function_rows(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[{"result": 42}], keys=["result"])
    out = rt.execute_routine({"db_type": "mysql"}, "db1", "f1", "Function", {"x": 1})
    assert out["columns"] == [{"name": "result"}]
    assert out["rows"] == [{"result": 42}]
    assert out["affected"] is None


def test_execute_routine_mysql_procedure_no_rows(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(returns_rows=False, rowcount=3)
    out = rt.execute_routine({"db_type": "mysql"}, "db1", "p1", "Procedure", {})
    assert out["rows"] == []
    assert out["affected"] == 3


def test_execute_routine_postgresql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[{"result": "ok"}], keys=["result"])
    out = rt.execute_routine({"db_type": "postgresql"}, "public", "p1", "Function", {"x": 1})
    assert out["rows"] == [{"result": "ok"}]


def test_execute_routine_mssql(_patch_engine):
    _, conn = _patch_engine
    conn.execute.return_value = _result(rows=[{"result": "ok"}], keys=["result"])
    out = rt.execute_routine({"db_type": "mssql"}, "dbo", "p1", "Procedure", {"x": 1})
    assert out["rows"] == [{"result": "ok"}]


def test_execute_routine_unsupported_raises(_patch_engine):
    with pytest.raises(ValueError):
        rt.execute_routine({"db_type": "sqlite"}, "db1", "p1", "Procedure", {})
