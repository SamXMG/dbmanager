# -*- coding: utf-8 -*-
"""services/sync 单测(M2-3): sync_table / diff_schema / execute_schema_sync。
桩 services.sync 的 metadata/engine 引用, diff 用 sqlalchemy.inspect 假实现。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, String, Table

import sqlalchemy
import services.sync as sync


def _real_table():
    return Table("t", MetaData(), Column("id", Integer), Column("name", String(20)))


def _eng(rows=None, rowcount=0):
    engine = MagicMock()
    conn = MagicMock()
    res = MagicMock()
    res.mappings.return_value = rows if rows is not None else []
    res.rowcount = rowcount
    res.first.return_value = (rows[0] if rows else None)
    conn.execute.return_value = res
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    engine.begin.return_value.__enter__.return_value = conn
    engine.begin.return_value.__exit__.return_value = False
    return engine


class FakeInspector:
    def __init__(self, tables=None, cols=None, pk=None):
        self._tables = tables or []
        self._cols = cols or {}
        self._pk = pk or []

    def get_table_names(self, schema=None):
        return self._tables

    def get_columns(self, table, schema=None):
        return self._cols.get(table, [])

    def get_pk_constraint(self, table, schema=None):
        return {"constrained_columns": self._pk}


# ==================== sync_table ====================
def test_sync_table_append(monkeypatch):
    monkeypatch.setattr(sync, "get_columns",
                        lambda ci, s, t: [{"name": "id"}, {"name": "name"}])
    monkeypatch.setattr(sync, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(sync, "get_engine", lambda ci: _eng(rows=[{"id": 1, "name": "x"}]))
    r = sync.sync_table({"db_type": "mysql"}, {"db_type": "mysql"}, "s", "t", "append")
    assert r["ok"] is True and r["synced"] == 1 and r["mode"] == "append"


def test_sync_table_replace(monkeypatch):
    monkeypatch.setattr(sync, "get_columns",
                        lambda ci, s, t: [{"name": "id"}, {"name": "name"}])
    monkeypatch.setattr(sync, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(sync, "get_engine", lambda ci: _eng(rows=[{"id": 1, "name": "x"}]))
    r = sync.sync_table({"db_type": "mysql"}, {"db_type": "mysql"}, "s", "t", "replace")
    assert r["mode"] == "replace"


def test_sync_table_no_common(monkeypatch):
    import pytest
    src_ci = {"db_type": "mysql"}
    dst_ci = {"db_type": "mysql"}

    def _cols(ci, s, t):
        if ci is src_ci:
            return [{"name": "id"}]
        return [{"name": "other"}]  # 与源无交集

    monkeypatch.setattr(sync, "get_columns", _cols)
    monkeypatch.setattr(sync, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(sync, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        sync.sync_table(src_ci, dst_ci, "s", "t", "append")


def test_sync_table_missing_src(monkeypatch):
    import pytest
    monkeypatch.setattr(sync, "get_columns",
                        lambda ci, s, t: [{"name": "id"}, {"name": "name"}])
    monkeypatch.setattr(sync, "get_table_obj",
                        lambda *a, **k: (_ for _ in ()).throw(ValueError("no src")))
    monkeypatch.setattr(sync, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        sync.sync_table({"db_type": "mysql"}, {"db_type": "mysql"}, "s", "t", "append")


# ==================== diff_schema ====================
def test_diff_missing_table(monkeypatch):
    monkeypatch.setattr(sqlalchemy, "inspect",
                        lambda eng: FakeInspector(tables=["other"], cols={"other": []}))
    monkeypatch.setattr(sync, "get_engine", lambda ci: _eng())
    diffs = sync.diff_schema({"db_type": "mysql"}, {"db_type": "mysql"},
                             schema="s", table="t")
    assert diffs and diffs[0]["type"] == "缺表"


def test_diff_column_and_type_and_pk(monkeypatch):
    s_cols = [{"name": "id", "type": "INT", "nullable": False},
              {"name": "name", "type": "VARCHAR(50)", "nullable": True}]
    d_cols = [{"name": "id", "type": "INT", "nullable": False}]  # name 缺失
    insp = FakeInspector(tables=["t"], cols={"t": s_cols}, pk=["id"])
    d_insp = FakeInspector(tables=["t"], cols={"t": d_cols}, pk=[])

    def _make_eng(tag):
        engine = MagicMock()
        conn = MagicMock()
        conn._tag = tag
        engine.connect.return_value.__enter__.return_value = conn
        engine.connect.return_value.__exit__.return_value = False
        return engine

    src_eng, dst_eng = _make_eng("src"), _make_eng("dst")

    def _get_engine(ci):
        return src_eng if ci.get("tag") == "src" else dst_eng

    def _inspect(eng):
        return insp if getattr(eng, "_tag", None) == "src" else d_insp

    monkeypatch.setattr(sync, "get_engine", _get_engine)
    monkeypatch.setattr(sqlalchemy, "inspect", _inspect)
    diffs = sync.diff_schema({"db_type": "mysql", "tag": "src"},
                             {"db_type": "mysql", "tag": "dst"},
                             schema="s", table="t")
    types = {d["type"] for d in diffs}
    assert "缺列" in types
    assert "主键不同" in types


# ==================== execute_schema_sync ====================
def test_execute_schema_sync(monkeypatch):
    monkeypatch.setattr(sync, "get_engine", lambda ci: _eng())
    r = sync.execute_schema_sync({"db_type": "mysql"},
                                 ["", "/* comment */", "ALTER TABLE t ADD c INT"])
    assert r["executed"] == ["ALTER TABLE t ADD c INT"]
    assert r["failed"] == []


def test_execute_schema_sync_failure(monkeypatch):
    engine = MagicMock()
    conn = MagicMock()
    conn.execute.side_effect = Exception("boom")
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    monkeypatch.setattr(sync, "get_engine", lambda ci: engine)
    r = sync.execute_schema_sync({"db_type": "mysql"}, ["BAD SQL"])
    assert len(r["failed"]) == 1
