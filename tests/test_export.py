# -*- coding: utf-8 -*-
"""services/export 单测(M2-3): xlsx 生成/解析(纯函数) + export_data(多格式) +
export_schema_doc + import_data。桩 services.export 的 metadata/engine 引用, 用真实 Table。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, String, Table

import services.export as ex


def _real_table():
    return Table("t", MetaData(), Column("id", Integer), Column("name", String(20)))


def _eng(rows=None, rowcount=0):
    engine = MagicMock()
    conn = MagicMock()
    res = MagicMock()
    res.mappings.return_value = rows if rows is not None else []
    res.rowcount = rowcount
    conn.execute.return_value = res
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine


# ==================== 纯函数: xlsx ====================
def test_xlsx_col_letter():
    assert ex._xlsx_col_letter(0) == "A"
    assert ex._xlsx_col_letter(25) == "Z"
    assert ex._xlsx_col_letter(26) == "AA"
    assert ex._xlsx_col_letter(27) == "AB"


def test_xlsx_bytes_roundtrip():
    data = ex._xlsx_bytes(["id", "name"], [{"id": 1, "name": "x"}, {"id": 2, "name": "y"}])
    assert data[:2] == b"PK"  # zip 文件签名
    header, rows = ex.parse_xlsx_import(data)
    assert header == ["id", "name"]
    assert rows == [["1", "x"], ["2", "y"]]


def test_parse_xlsx_empty():
    data = ex._xlsx_bytes(["a"], [])
    header, rows = ex.parse_xlsx_import(data)
    assert header == ["a"] and rows == []


# ==================== export_data: 多格式 ====================
def _patch_export_meta(monkeypatch, table=None, cols=None):
    monkeypatch.setattr(ex, "get_columns",
                        lambda *a, **k: cols or [{"name": "id"}, {"name": "name"}])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: table or _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng(rows=[{"id": 1, "name": "x"}]))


def test_export_csv(monkeypatch):
    _patch_export_meta(monkeypatch)
    content, mime, fname = ex.export_data({"db_type": "mysql"}, "s", "t", "", "csv")
    assert mime == "text/csv; charset=utf-8"
    assert fname.endswith(".csv")
    assert content.startswith("\ufeff")  # BOM


def test_export_json(monkeypatch):
    import json
    _patch_export_meta(monkeypatch)
    content, mime, fname = ex.export_data({"db_type": "mysql"}, "s", "t", "", "json")
    assert mime == "application/json; charset=utf-8"
    assert json.loads(content) == [{"id": 1, "name": "x"}]


def test_export_xml(monkeypatch):
    _patch_export_meta(monkeypatch)
    content, mime, fname = ex.export_data({"db_type": "mysql"}, "s", "t", "", "xml")
    assert mime == "application/xml; charset=utf-8"
    assert "<rows>" in content and "<id>1</id>" in content


def test_export_sql(monkeypatch):
    _patch_export_meta(monkeypatch)
    content, mime, fname = ex.export_data({"db_type": "mysql"}, "s", "t", "", "sql")
    assert mime == "application/sql; charset=utf-8"
    assert "INSERT INTO" in content and "`id`" in content


def test_export_xlsx(monkeypatch):
    _patch_export_meta(monkeypatch)
    content, mime, fname = ex.export_data({"db_type": "mysql"}, "s", "t", "", "xlsx")
    assert mime == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert content[:2] == b"PK"
    assert fname.endswith(".xlsx")


# ==================== export_schema_doc ====================
def test_export_schema_doc(monkeypatch):
    monkeypatch.setattr(ex, "get_tables",
                        lambda *a, **k: [{"name": "t", "schema": "s", "type": "Table"}])
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [
        {"name": "id", "type": "INT", "nullable": False, "identity": True, "default": None},
        {"name": "name", "type": "VARCHAR", "nullable": True, "identity": False, "default": "''"},
    ])
    monkeypatch.setattr(ex, "get_pk", lambda *a, **k: ["id"])
    monkeypatch.setattr(ex, "get_indexes", lambda *a, **k: [
        {"name": "ix", "is_unique": True, "is_pk": False, "columns": "name"}])
    md = ex.export_schema_doc({"db_type": "mysql"})
    assert "# 数据字典" in md
    assert "| id |" in md


# ==================== import_data ====================
def test_import_ok(monkeypatch):
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [
        {"name": "id", "identity": False, "computed": False, "nullable": True},
        {"name": "name", "identity": False, "computed": False, "nullable": True}])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng(rowcount=5))
    r = ex.import_data({"db_type": "mysql"}, "s", "t", ["id", "name"],
                       [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}])
    assert r == {"ok": True, "affected": 5}


def test_import_empty_columns(monkeypatch):
    import pytest
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        ex.import_data({"db_type": "mysql"}, "s", "t", [], [{"id": 1}])


def test_import_empty_rows(monkeypatch):
    import pytest
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [
        {"name": "id", "identity": False, "computed": False, "nullable": True}])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        ex.import_data({"db_type": "mysql"}, "s", "t", ["id"], [])


def test_import_row_limit(monkeypatch):
    import pytest
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [
        {"name": "id", "identity": False, "computed": False, "nullable": True}])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        ex.import_data({"db_type": "mysql"}, "s", "t", ["id"], [{"id": 1}] * 5001)


def test_import_unknown_column(monkeypatch):
    import pytest
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [
        {"name": "id", "identity": False, "computed": False, "nullable": True}])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        ex.import_data({"db_type": "mysql"}, "s", "t", ["nope"], [{"nope": 1}])


def test_import_all_identity(monkeypatch):
    import pytest
    monkeypatch.setattr(ex, "get_columns", lambda *a, **k: [
        {"name": "id", "identity": True, "computed": False, "nullable": True}])
    monkeypatch.setattr(ex, "get_table_obj", lambda *a, **k: _real_table())
    monkeypatch.setattr(ex, "get_engine", lambda ci: _eng())
    with pytest.raises(ValueError):
        ex.import_data({"db_type": "mysql"}, "s", "t", ["id"], [{"id": 1}])
