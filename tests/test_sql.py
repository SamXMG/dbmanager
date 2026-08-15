# -*- coding: utf-8 -*-
"""services/sql 单测(M2-3): run_sql 只读校验/写模式事务/EXPLAIN 多方言。桩 dbcore.get_engine。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

from db import dbcore
import services.sql as sql


# ---------- run_sql: 引擎构造 ----------
def _read_engine():
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    result.returns_rows = True
    result.keys.return_value = ["id"]
    result.mappings.return_value.fetchmany.return_value = [{"id": 1}, {"id": 2}]
    conn.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine, conn


def _write_engine():
    engine = MagicMock()
    conn = MagicMock()
    tx = MagicMock()
    conn.begin.return_value = tx
    result = MagicMock()
    result.returns_rows = False
    result.rowcount = 1
    conn.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine, conn, tx


# ---------- run_sql: 非 SQL 库拒绝 ----------
def test_run_sql_mongodb_rejected():
    import pytest
    with pytest.raises(ValueError):
        sql.run_sql({"db_type": "mongodb"}, "SELECT 1")


def test_run_sql_redis_rejected():
    import pytest
    with pytest.raises(ValueError):
        sql.run_sql({"db_type": "redis"}, "SELECT 1")


def test_run_sql_empty_rejected():
    import pytest
    with pytest.raises(ValueError):
        sql.run_sql({"db_type": "mysql"}, "   ")


# ---------- run_sql: 只读模式预校验 ----------
def test_run_sql_blocked_statement():
    import pytest
    with pytest.raises(ValueError) as e:
        sql.run_sql({"db_type": "mysql"}, "INSERT INTO t VALUES (1)")
    assert "INSERT" in str(e.value)


def test_run_sql_non_readonly_rejected():
    import pytest
    with pytest.raises(ValueError) as e:
        sql.run_sql({"db_type": "mysql"}, "UPDATE t SET x=1")
    assert "仅支持" in str(e.value)


def test_run_sql_select_into_outfile_rejected():
    import pytest
    with pytest.raises(ValueError) as e:
        sql.run_sql({"db_type": "mysql"}, "SELECT * FROM t INTO OUTFILE '/tmp/x'")
    assert "SELECT INTO" in str(e.value)


def test_run_sql_select_into_var_allowed(monkeypatch):
    engine, conn = _read_engine()
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.run_sql({"db_type": "mysql"}, "SELECT * FROM t INTO @x")
    assert r["readonly"] is True
    assert r["ok"] is True


# ---------- run_sql: 只读执行 + 自动 LIMIT ----------
def test_run_sql_readonly_executes(monkeypatch):
    engine, conn = _read_engine()
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.run_sql({"db_type": "mysql"}, "SELECT id FROM t")
    assert r["readonly"] is True
    assert r["results"][0]["total"] == 2
    # 无 LIMIT 的 SELECT 自动追加 LIMIT 501(默认 limit 500 -> 501)
    stmt = conn.execute.call_args.args[0].text
    assert "LIMIT 501" in stmt


def test_run_sql_readonly_show_explain_desc(monkeypatch):
    engine, conn = _read_engine()
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    for s in ("SHOW TABLES", "EXPLAIN SELECT 1", "DESC t"):
        r = sql.run_sql({"db_type": "mysql"}, s)
        assert r["ok"] is True


def test_run_sql_multiple_statements(monkeypatch):
    engine, conn = _read_engine()
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.run_sql({"db_type": "mysql"}, "SELECT 1; SELECT 2")
    assert len(r["results"]) == 2


def test_run_sql_limit_clamp(monkeypatch):
    engine, conn = _read_engine()
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    sql.run_sql({"db_type": "mysql"}, "SELECT id FROM t", limit=99999)
    assert "LIMIT 5001" in conn.execute.call_args.args[0].text
    # limit 0 -> 夹到 1 -> LIMIT 2
    sql.run_sql({"db_type": "mysql"}, "SELECT id FROM t", limit=0)
    assert "LIMIT 2" in conn.execute.call_args.args[0].text


# ---------- run_sql: 写模式事务 ----------
def test_run_sql_write_mode(monkeypatch):
    engine, conn, tx = _write_engine()
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.run_sql({"db_type": "mysql"}, "INSERT INTO t VALUES (1)", write=True)
    assert r["readonly"] is False
    assert r["ok"] is True
    tx.commit.assert_called_once()


def test_run_sql_write_mode_rollback(monkeypatch):
    import pytest
    engine, conn, tx = _write_engine()
    conn.execute.side_effect = Exception("boom")
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    with pytest.raises(Exception):
        sql.run_sql({"db_type": "mysql"}, "INSERT INTO t VALUES (1)", write=True)
    tx.rollback.assert_called_once()


# ---------- explain_query ----------
def _explain_engine(result, side_effect=None):
    conn = MagicMock()
    if side_effect is not None:
        conn.execute.side_effect = side_effect
    else:
        conn.execute.return_value = result
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine, conn


def test_explain_mysql(monkeypatch):
    result = MagicMock()
    result.keys.return_value = ["id", "select_type"]
    result.mappings.return_value = [{"id": 1, "select_type": "SIMPLE"}]
    engine, _ = _explain_engine(result)
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.explain_query({"db_type": "mysql"}, "SELECT 1")
    assert r["mode"] == "table"
    assert r["rows"] == [{"id": 1, "select_type": "SIMPLE"}]


def test_explain_postgresql(monkeypatch):
    plan = [{
        "Node Type": "Seq Scan", "Relation Name": "t", "Plan Rows": 10,
        "Total Cost": 3.5, "Filter": "x > 1",
        "Plans": [{"Node Type": "Index Scan", "Relation Name": "i",
                   "Plan Rows": 1, "Total Cost": 1.0, "Filter": None, "Plans": []}],
    }]
    result = MagicMock()
    result.scalar.return_value = plan
    engine, _ = _explain_engine(result)
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.explain_query({"db_type": "postgresql"}, "SELECT 1")
    assert r["mode"] == "tree"
    # tree 模式以 plan 树承载节点, rows 为空、total 为 0
    assert r["total"] == 0
    assert r["rows"] == []
    # 验证 PG plan 归一化: 根节点 Seq Scan, 子节点 Index Scan
    assert r["plan"]["operation"] == "Seq Scan"
    assert r["plan"]["children"][0]["operation"] == "Index Scan"


def test_explain_mssql(monkeypatch):
    on, off = MagicMock(), MagicMock()
    sres = MagicMock()
    sres.mappings.return_value.fetchmany.return_value = [{"StmtText": "x"}]
    engine, conn = _explain_engine(None, side_effect=[on, sres, off])
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.explain_query({"db_type": "mssql"}, "SELECT 1")
    assert r["mode"] == "text"
    assert r["rows"] == [{"StmtText": "x"}]
    # SET SHOWPLAN_ALL ON / OFF 都执行过
    calls = [c.args[0].text for c in conn.execute.call_args_list]
    assert any("SHOWPLAN_ALL ON" in c for c in calls)
    assert any("SHOWPLAN_ALL OFF" in c for c in calls)


def test_explain_oracle(monkeypatch):
    ep = MagicMock()
    sel = MagicMock()
    sel.mappings.return_value.fetchmany.return_value = [
        {"PLAN_TABLE_OUTPUT": "line1"}, {"PLAN_TABLE_OUTPUT": "line2"}]
    engine, _ = _explain_engine(None, side_effect=[ep, sel])
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.explain_query({"db_type": "oracle"}, "SELECT 1")
    assert r["mode"] == "text"
    assert r["rows"] == [{"执行计划": "line1"}, {"执行计划": "line2"}]


def test_explain_sqlite(monkeypatch):
    result = MagicMock()
    result.keys.return_value = ["id", "detail"]
    result.mappings.return_value = [{"id": 0, "detail": "SCAN t"}]
    engine, _ = _explain_engine(result)
    monkeypatch.setattr(sql, "get_engine", lambda ci: engine)
    r = sql.explain_query({"db_type": "sqlite"}, "SELECT 1")
    assert r["mode"] == "table"
    assert r["rows"] == [{"id": 0, "detail": "SCAN t"}]


def test_explain_nosql_rejected():
    import pytest
    with pytest.raises(ValueError):
        sql.explain_query({"db_type": "redis"}, "SELECT 1")


def test_explain_empty_rejected():
    import pytest
    with pytest.raises(ValueError):
        sql.explain_query({"db_type": "mysql"}, "   ")
