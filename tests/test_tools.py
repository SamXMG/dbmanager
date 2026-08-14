# -*- coding: utf-8 -*-
"""services/tools 单测(M2-3): stats_column / transfer_data / gen_data。
桩 services.tools 的 metadata/engine/Table 引用与 sqlalchemy.inspect。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, String, Table

import sqlalchemy
import services.tools as tools


class FakeInspector:
    def __init__(self, pk=None):
        self._pk = pk or []

    def get_pk_constraint(self, table, schema=None):
        return {"constrained_columns": self._pk}


def _real_table(cols):
    meta = MetaData()
    return Table("t", meta, *cols)


def _stats_engine():
    engine = MagicMock()
    conn = MagicMock()
    res = MagicMock()
    # COUNT 与 SUM 两次查询都走 .mappings().first(); 一行同时含两类字段即可
    res.mappings.return_value.first.return_value = {
        "cnt": 5, "mn": 1, "mx": 10, "sm": 100, "av": 20}
    conn.execute.return_value = res
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine


# ==================== stats_column ====================
def test_stats_column_numeric(monkeypatch):
    monkeypatch.setattr(tools, "get_columns", lambda *a, **k: [
        {"name": "id", "type": "INT"}, {"name": "name", "type": "VARCHAR"}])
    monkeypatch.setattr(tools, "get_engine", lambda ci: _stats_engine())
    r = tools.stats_column({"db_type": "mysql"}, "s", "t", "id")
    assert r["count"] == 5 and r["min"] == 1 and r["max"] == 10
    assert r["sum"] == 100 and r["avg"] == 20


def test_stats_column_non_numeric(monkeypatch):
    monkeypatch.setattr(tools, "get_columns", lambda *a, **k: [
        {"name": "name", "type": "VARCHAR"}])
    engine = MagicMock()
    conn = MagicMock()
    res = MagicMock()
    res.mappings.return_value.first.return_value = {"cnt": 2, "mn": "a", "mx": "z"}
    conn.execute.return_value = res
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    monkeypatch.setattr(tools, "get_engine", lambda ci: engine)
    r = tools.stats_column({"db_type": "mysql"}, "s", "t", "name")
    assert r["count"] == 2 and "sum" not in r


def test_stats_column_nosql(monkeypatch):
    import pytest
    with pytest.raises(ValueError):
        tools.stats_column({"db_type": "redis"}, "s", "t", "x")


# ==================== transfer_data ====================
def test_transfer_happy(monkeypatch):
    def _table_factory(table, *a, **k):
        if table == "t":
            return _real_table([Column("id", Integer), Column("name", String)])
        return _real_table([Column("id", Integer), Column("name", String)])
    engine = MagicMock()
    sconn = MagicMock()
    result = MagicMock()
    result.fetchmany.side_effect = [[("1", "x"), ("2", "y")], []]  # 第一批数据, 第二批空 -> 退出循环
    sconn.execution_options.return_value.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = sconn
    engine.connect.return_value.__exit__.return_value = False
    dconn = MagicMock()
    engine.begin.return_value.__enter__.return_value = dconn
    engine.begin.return_value.__exit__.return_value = False
    monkeypatch.setattr(tools, "get_engine", lambda ci: engine)
    monkeypatch.setattr(tools, "Table", _table_factory)
    monkeypatch.setattr(sqlalchemy, "inspect", lambda eng: FakeInspector())
    r = tools.transfer_data({"db_type": "mysql"}, "s", "t", "db2", "s2", "t2")
    assert r["ok"] is True and r["transferred"] == 2


def test_transfer_nosql(monkeypatch):
    import pytest
    with pytest.raises(ValueError):
        tools.transfer_data({"db_type": "redis"}, "s", "t", "", "s2", "t2")


def test_transfer_missing_table(monkeypatch):
    import pytest
    with pytest.raises(ValueError):
        tools.transfer_data({"db_type": "mysql"}, "s", "", "", "s2", "t2")


def test_transfer_no_common(monkeypatch):
    import pytest
    def _table_factory(table, *a, **k):
        if table == "t":
            return _real_table([Column("id", Integer)])
        return _real_table([Column("other", Integer)])  # 与源无公共列
    monkeypatch.setattr(tools, "get_engine", lambda ci: MagicMock())
    monkeypatch.setattr(tools, "Table", _table_factory)
    monkeypatch.setattr(sqlalchemy, "inspect", lambda eng: FakeInspector())
    with pytest.raises(ValueError):
        tools.transfer_data({"db_type": "mysql"}, "s", "t", "db2", "s2", "t2")


# ==================== gen_data ====================
def test_gen_data_happy(monkeypatch):
    monkeypatch.setattr(tools, "get_columns", lambda *a, **k: [
        {"name": "id", "type": "INT", "identity": False, "is_pk": False},
        {"name": "name", "type": "VARCHAR", "identity": False, "is_pk": False}])
    engine = MagicMock()
    dconn = MagicMock()
    engine.begin.return_value.__enter__.return_value = dconn
    engine.begin.return_value.__exit__.return_value = False
    monkeypatch.setattr(tools, "get_engine", lambda ci: engine)
    monkeypatch.setattr(tools, "Table",
                        lambda table, *a, **k: _real_table([Column("id", Integer), Column("name", String)]))
    r = tools.gen_data({"db_type": "mysql"}, "s", "t", 3)
    assert r["ok"] is True and r["inserted"] == 3 and r["columns"] == 2


def test_gen_data_nosql(monkeypatch):
    import pytest
    with pytest.raises(ValueError):
        tools.gen_data({"db_type": "mongodb"}, "s", "t", 3)


def test_gen_data_bad_rows(monkeypatch):
    import pytest
    monkeypatch.setattr(tools, "get_columns", lambda *a, **k: [
        {"name": "id", "type": "INT", "identity": False, "is_pk": False}])
    monkeypatch.setattr(tools, "get_engine", lambda ci: MagicMock())
    monkeypatch.setattr(tools, "Table",
                        lambda table, *a, **k: _real_table([Column("id", Integer)]))
    with pytest.raises(ValueError):
        tools.gen_data({"db_type": "mysql"}, "s", "t", 0)


def test_gen_data_all_identity(monkeypatch):
    import pytest
    monkeypatch.setattr(tools, "get_columns", lambda *a, **k: [
        {"name": "id", "type": "INT", "identity": True, "is_pk": True}])
    monkeypatch.setattr(tools, "get_engine", lambda ci: MagicMock())
    monkeypatch.setattr(tools, "Table",
                        lambda table, *a, **k: _real_table([Column("id", Integer)]))
    with pytest.raises(ValueError):
        tools.gen_data({"db_type": "mysql"}, "s", "t", 3)
