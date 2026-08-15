# -*- coding: utf-8 -*-
"""services/metadata 单测(M2-2): 库/表/列/索引/主键/关系/ER/权限(含 NoSQL 分支)。
桩 services.metadata.inspect / get_engine 与 dbcore.get_mongo/get_redis。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import MagicMock

from sqlalchemy import Integer, Numeric, String

from db import dbcore
import services.core as core
import services.metadata as meta


@pytest.fixture(autouse=True)
def _clear_meta_cache():
    core.META_CACHE.clear()
    yield
    core.META_CACHE.clear()


@pytest.fixture(autouse=True)
def _patch_get_engine(monkeypatch):
    # get_tables/get_columns/... 先 get_engine(ci) 再 inspect(engine); 默认桩掉真连接,
    # 具体测试可再用 monkeypatch 覆盖为带返回行的 _fake_engine
    monkeypatch.setattr(meta, "get_engine", lambda ci: MagicMock())


# ---------- 假 Inspector: 统一 SQL 反射接口 ----------
class FakeInspector:
    def __init__(self, schema_names=None, tables=None, views=None,
                 columns=None, pks=None, indexes=None, fks=None):
        self._schema_names = schema_names or []
        self._tables = tables or []
        self._views = views or []
        self._columns = columns or []
        self._pks = pks or {}
        self._indexes = indexes or []
        self._fks = fks or []

    def get_schema_names(self):
        return self._schema_names

    def get_table_names(self, schema=None):
        return self._tables

    def get_view_names(self, schema=None):
        return self._views

    def get_columns(self, table, schema=None):
        return self._columns

    def get_pk_constraint(self, table, schema=None):
        return self._pks

    def get_indexes(self, table, schema=None):
        return self._indexes

    def get_foreign_keys(self, table, schema=None):
        return self._fks


def _patch_inspect(monkeypatch, insp):
    monkeypatch.setattr(meta, "inspect", lambda engine: insp)


def _fake_engine(rows=None):
    engine = MagicMock()
    conn = MagicMock()
    res = MagicMock()
    res.fetchall.return_value = rows if rows is not None else []
    conn.execute.return_value = res
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine


COLUMNS = [
    {"name": "id", "type": Integer(), "nullable": False, "autoincrement": True,
     "identity": False, "computed": False, "default": None},
    {"name": "name", "type": String(50), "nullable": True, "autoincrement": False,
     "identity": False, "computed": False, "default": "''"},
    {"name": "amt", "type": Numeric(10, 2), "nullable": True, "autoincrement": False,
     "identity": False, "computed": False, "default": None},
]


# ==================== get_databases ====================
def test_get_databases_sqlite():
    assert meta.get_databases({"db_type": "sqlite"}) == []


def test_get_databases_mongodb(monkeypatch):
    client = MagicMock()
    client.list_database_names.return_value = ["admin", "local", "mydb"]
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: client)
    assert meta.get_databases({"db_type": "mongodb"}) == ["mydb"]


def test_get_databases_redis(monkeypatch):
    r = MagicMock()
    r.select.return_value = True
    r.dbsize.return_value = 1
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: r)
    out = meta.get_databases({"db_type": "redis"})
    assert "db0" in out and len(out) == 16


def test_get_databases_mysql(monkeypatch):
    engine = _fake_engine([("s1",), ("s2",)])
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    assert meta.get_databases({"db_type": "mysql"}) == ["s1", "s2"]


def test_get_databases_mssql(monkeypatch):
    # SQL 已按 database_id>4 过滤系统库, mock 直接给过滤后结果
    engine = _fake_engine([("app",)])
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    assert meta.get_databases({"db_type": "mssql"}) == ["app"]


def test_get_databases_postgresql(monkeypatch):
    engine = _fake_engine([("app",)])
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    assert meta.get_databases({"db_type": "postgresql"}) == ["app"]


def test_get_databases_oracle(monkeypatch):
    engine = _fake_engine([("APP",)])
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    assert meta.get_databases({"db_type": "oracle"}) == ["APP"]


# ==================== get_tables ====================
@pytest.mark.parametrize("db_type,schema_names,expected", [
    ("sqlite", [], [("t1", "Table", ""), ("v1", "View", "")]),
    ("mysql", ["information_schema", "myschema"], [("t1", "Table", "myschema"), ("v1", "View", "myschema")]),
    ("postgresql", ["pg_catalog", "public"], [("t1", "Table", "public"), ("v1", "View", "public")]),
    ("mssql", ["sys", "dbo"], [("t1", "Table", "dbo"), ("v1", "View", "dbo")]),
    ("oracle", ["SYS", "APP"], [("t1", "Table", "APP"), ("v1", "View", "APP")]),
])
def test_get_tables_sql(monkeypatch, db_type, schema_names, expected):
    insp = FakeInspector(schema_names=schema_names, tables=["t1"], views=["v1"])
    _patch_inspect(monkeypatch, insp)
    out = meta.get_tables({"db_type": db_type})
    assert [(o["name"], o["type"], o["schema"]) for o in out] == expected


def test_get_tables_mongodb(monkeypatch):
    client = MagicMock()
    client.list_database_names.return_value = ["admin", "mydb"]
    client.__getitem__.return_value.list_collection_names.return_value = ["c1"]
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: client)
    out = meta.get_tables({"db_type": "mongodb"})
    assert out == [{"schema": "mydb", "name": "c1", "type": "Collection"}]


def test_get_tables_redis(monkeypatch):
    r = MagicMock()
    r.scan.return_value = (0, [b"k1"])
    r.type.return_value = "string"
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: r)
    out = meta.get_tables({"db_type": "redis"})
    assert out[0]["name"] == b"k1"
    assert out[0]["type"] == "String"


# ==================== get_columns ====================
def test_get_columns(monkeypatch):
    insp = FakeInspector(columns=COLUMNS)
    _patch_inspect(monkeypatch, insp)
    cols = meta.get_columns({"db_type": "mysql"}, "s", "t")
    assert cols[0]["name"] == "id"
    assert cols[0]["type"] == "INTEGER" or "INT" in cols[0]["type"].upper()
    assert cols[0]["identity"] is True
    assert cols[1]["max_length"] == 50
    assert cols[2]["precision"] == 10 and cols[2]["scale"] == 2


# ==================== get_pk ====================
def test_get_pk_mongodb():
    assert meta.get_pk({"db_type": "mongodb"}, "s", "t") == ["_id"]


def test_get_pk_sql(monkeypatch):
    insp = FakeInspector(pks={"constrained_columns": ["id", "tenant"]})
    _patch_inspect(monkeypatch, insp)
    assert meta.get_pk({"db_type": "mysql"}, "s", "t") == ["id", "tenant"]


def test_get_pk_empty(monkeypatch):
    insp = FakeInspector(pks=None)
    _patch_inspect(monkeypatch, insp)
    assert meta.get_pk({"db_type": "mysql"}, "s", "t") == []


# ==================== get_indexes ====================
def test_get_indexes_mongodb(monkeypatch):
    coll = MagicMock()
    coll.list_indexes.return_value = iter(
        [{"name": "i1", "key": {"a": 1}, "unique": True}])
    client = MagicMock()
    client.__getitem__.return_value.__getitem__.return_value = coll
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: client)
    out = meta.get_indexes({"db_type": "mongodb"}, "s", "t")
    assert out[0]["name"] == "i1"
    assert out[0]["columns"] == ["a"]
    assert out[0]["unique"] is True


def test_get_indexes_sql(monkeypatch):
    insp = FakeInspector(indexes=[
        {"name": "ix", "primary_key": False, "unique": True, "column_names": ["a", "b"]}])
    _patch_inspect(monkeypatch, insp)
    out = meta.get_indexes({"db_type": "mysql"}, "s", "t")
    assert out[0]["is_unique"] is True
    assert out[0]["columns"] == "a, b"


# ==================== get_table_obj ====================
def test_get_table_obj(monkeypatch):
    fake_tbl = MagicMock()
    monkeypatch.setattr(meta, "get_engine", lambda ci: MagicMock())
    monkeypatch.setattr(meta, "MetaData", lambda: MagicMock())
    monkeypatch.setattr(meta, "Table", lambda *a, **k: fake_tbl)
    assert meta.get_table_obj({"db_type": "mysql"}, "s", "t") is fake_tbl


# ==================== get_relations ====================
def test_get_relations_nosql():
    assert meta.get_relations({"db_type": "mongodb"}, "s", "t") == []
    assert meta.get_relations({"db_type": "redis"}, "s", "t") == []


def test_get_relations_out_and_in(monkeypatch):
    insp = FakeInspector(
        fks=[{"name": "fk_out", "constrained_columns": ["x"],
              "referred_table": "ref", "referred_schema": "rs"}],
        tables=["other"])
    # 让 other 表的外键指回中心表, 覆盖 in 方向
    insp._fks_by_table = {}
    def get_fks(table, schema=None):
        if table == "other":
            return [{"name": "fk_in", "constrained_columns": ["y"],
                     "referred_table": "t", "referred_schema": "s"}]
        return insp._fks
    insp.get_foreign_keys = get_fks
    _patch_inspect(monkeypatch, insp)
    rels = meta.get_relations({"db_type": "mysql"}, "s", "t")
    directions = {r["direction"] for r in rels}
    assert "out" in directions and "in" in directions


# ==================== get_er_data ====================
def test_get_er_data(monkeypatch):
    insp = FakeInspector(
        columns=COLUMNS,
        pks={"constrained_columns": ["id"]},
        fks=[{"name": "fk_out", "constrained_columns": ["x"],
              "referred_table": "ref", "referred_schema": "rs"}])
    _patch_inspect(monkeypatch, insp)
    data = meta.get_er_data({"db_type": "mysql"}, "s", "t")
    assert any(t["name"] == "t" for t in data["tables"])
    assert any(t["name"] == "ref" for t in data["tables"])
    assert len(data["relations"]) >= 1


# ==================== get_users_privs ====================
def test_get_users_privs_sqlite():
    r = meta.get_users_privs({"db_type": "sqlite"})
    assert r["supported"] is False
    assert r["logins"] == []


def test_get_users_privs_mssql(monkeypatch):
    engine = _fake_engine()
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    r = meta.get_users_privs({"db_type": "mssql"})
    assert r["supported"] is True


def test_get_users_privs_mysql(monkeypatch):
    engine = _fake_engine()
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    r = meta.get_users_privs({"db_type": "mysql"})
    assert r["supported"] is True


def test_get_users_privs_postgresql(monkeypatch):
    engine = _fake_engine()
    monkeypatch.setattr(meta, "get_engine", lambda ci: engine)
    r = meta.get_users_privs({"db_type": "postgresql"})
    assert r["supported"] is True
