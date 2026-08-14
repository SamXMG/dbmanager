# -*- coding: utf-8 -*-
"""services/data 单测(M2-3): 用 mock 桩掉 dbcore/metadata/nosql, 覆盖
get_data(SQL/Mongo/Redis)、mutate(SQL/Mongo/Redis 增改删)、
mutate_batch_delete、commit/rollback_transaction。不连真库。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, String, Table

import dbcore
import services.data


COLS = [
    {"name": "id", "type": "INT", "nullable": False, "max_length": None,
     "identity": True, "computed": False},
    {"name": "name", "type": "VARCHAR", "nullable": True, "max_length": 50,
     "identity": False, "computed": False},
]
PK = ["id"]

# 真实 Table: SQLAlchemy 的 insert/update/delete/select 不接受 MagicMock 当表
_TMETA = MetaData()
TBL = Table("t", _TMETA,
            Column("id", Integer, primary_key=True),
            Column("name", String(50)))


def _make_engine():
    engine = MagicMock()
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = 42
    conn.execute.return_value.rowcount = 1
    conn.execute.return_value.mappings.return_value = [{"id": 1, "name": "x"}]
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine, conn


def _patch_meta(monkeypatch):
    monkeypatch.setattr(services.data, "get_columns", lambda *a, **k: COLS)
    monkeypatch.setattr(services.data, "get_pk", lambda *a, **k: PK)
    monkeypatch.setattr(services.data, "get_table_obj", lambda *a, **k: TBL)


# ---------------- get_data: SQL 路径 ----------------
def test_get_data_sql_basic(monkeypatch):
    engine, _ = _make_engine()
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    r = services.data.get_data(ci, "s", "t", 1, 100, "", "name:asc")
    assert r["total"] == 42
    assert r["rows"] == [{"id": 1, "name": "x"}]
    assert r["pk"] == PK


def test_get_data_sql_count_cache_hit(monkeypatch):
    engine, conn = _make_engine()
    # 第一次 count 返回 42 并缓存; 第二次直接走缓存, 不再调用 scalar
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    services.data.get_data(ci, "s", "t", 1, 100, "name='a'", "")
    conn.execute.return_value.scalar.return_value = 999  # 若再查会变大, 但应命中缓存
    r2 = services.data.get_data(ci, "s", "t", 1, 100, "name='a'", "")
    assert r2["total"] == 42  # 命中缓存, 非 999


def test_get_data_sql_where_and_order(monkeypatch):
    engine, _ = _make_engine()
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "postgresql"}
    r = services.data.get_data(ci, "s", "t", 2, 50, "name='a'", "id:desc")
    assert r["page"] == 2 and r["size"] == 50


# ---------------- get_data: MongoDB 路径 ----------------
def test_get_data_mongo(monkeypatch):
    fake_coll = MagicMock()
    fake_coll.count_documents.return_value = 5
    fake_coll.find.return_value.skip.return_value.limit.return_value = [{"_id": "a", "x": 1}]
    fake_client = MagicMock()
    fake_client.__getitem__.return_value.__getitem__.return_value = fake_coll
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: fake_client)
    monkeypatch.setattr(services.data, "_parse_mongo_filter", lambda w: {})
    monkeypatch.setattr(services.data, "_mongo_cols",
                        lambda *a, **k: [{"name": "_id"}, {"name": "x"}])
    monkeypatch.setattr(services.data, "_mongo_doc_to_row",
                        lambda doc: {"_id": str(doc.get("_id")), "x": doc.get("x")})
    ci = {"db_type": "mongodb"}
    r = services.data.get_data(ci, "s", "t", 1, 10, "", "")
    assert r["total"] == 5 and r["db_type"] == "mongodb"
    assert r["rows"] == [{"_id": "a", "x": 1}]


# ---------------- get_data: Redis 路径 ----------------
def test_get_data_redis(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    monkeypatch.setattr(services.data, "_redis_rows",
                        lambda r, table, size: ([{"name": "_id"}, {"name": "v"}],
                                                [{"_id": "k", "v": "1"}], 1))
    ci = {"db_type": "redis"}
    r = services.data.get_data(ci, "", "t", 1, 100, "", "")
    assert r["db_type"] == "redis" and r["total"] == 1


# ---------------- mutate: SQL 增/改/删 ----------------
def test_mutate_sql_post(monkeypatch):
    engine, conn = _make_engine()
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    r = services.data.mutate(ci, "POST", "s", "t",
                             {"values": {"name": "hello"}, "orig": {}})
    assert r["ok"] is True and r["affected"] == conn.execute.return_value.rowcount


def test_mutate_sql_put(monkeypatch):
    engine, _ = _make_engine()
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    r = services.data.mutate(ci, "PUT", "s", "t",
                             {"values": {"name": "x"}, "orig": {"id": 1}})
    assert r["ok"] is True


def test_mutate_sql_delete(monkeypatch):
    engine, _ = _make_engine()
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    r = services.data.mutate(ci, "DELETE", "s", "t",
                             {"values": {}, "orig": {"id": 1}})
    assert r["ok"] is True


def test_mutate_sql_post_empty_raises(monkeypatch):
    monkeypatch.setattr(services.data, "get_engine", lambda ci: MagicMock())
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    import pytest
    with pytest.raises(ValueError):
        services.data.mutate({"db_type": "mysql"}, "POST", "s", "t",
                              {"values": {"id": 1}, "orig": {}})  # id 是 identity, 被排除后无字段


def test_mutate_tx_path(monkeypatch):
    fake_conn = MagicMock()
    monkeypatch.setattr(services.data, "get_connection",
                        lambda ci, use_tx=False, tx_key="": fake_conn)
    monkeypatch.setattr(services.data, "get_engine", lambda ci: MagicMock())
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    r = services.data.mutate(ci, "POST", "s", "t",
                             {"values": {"name": "y"}, "orig": {}},
                             use_tx=True, tx_key="tx1")
    assert r["ok"] is True


# ---------------- mutate: MongoDB ----------------
def test_mutate_mongo_post(monkeypatch):
    fake_coll = MagicMock()
    fake_coll.insert_one.return_value.inserted_id = "abc"
    fake_client = MagicMock()
    fake_client.__getitem__.return_value.__getitem__.return_value = fake_coll
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: fake_client)
    ci = {"db_type": "mongodb"}
    r = services.data.mutate(ci, "POST", "s", "t",
                             {"values": {"x": 1}, "orig": {}})
    assert r["affected"] == 1 and r["inserted_id"] == "abc"


def test_mutate_mongo_delete(monkeypatch):
    fake_coll = MagicMock()
    fake_coll.delete_many.return_value.deleted_count = 3
    fake_client = MagicMock()
    fake_client.__getitem__.return_value.__getitem__.return_value = fake_coll
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: fake_client)
    monkeypatch.setattr(services.data, "_mongo_oid", lambda v: v)
    ci = {"db_type": "mongodb"}
    r = services.data.mutate(ci, "DELETE", "s", "t",
                             {"values": {}, "orig": {"_id": "a"}})
    assert r["affected"] == 3


# ---------------- mutate: Redis ----------------
def test_mutate_redis_string_put(monkeypatch):
    fake_r = MagicMock()
    fake_r.type.return_value = "string"
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ci = {"db_type": "redis"}
    r = services.data.mutate(ci, "PUT", "", "t",
                             {"values": {"value": "v"}, "orig": {}})
    assert r["affected"] == 1
    fake_r.set.assert_called_once()


def test_mutate_redis_delete(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ci = {"db_type": "redis"}
    r = services.data.mutate(ci, "DELETE", "", "t", {"values": {}, "orig": {}})
    assert r["affected"] == fake_r.delete.return_value


# ---------------- mutate_batch_delete ----------------
def test_mutate_batch_delete_sql(monkeypatch):
    engine, conn = _make_engine()
    monkeypatch.setattr(services.data, "get_engine", lambda ci: engine)
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    _patch_meta(monkeypatch)
    ci = {"db_type": "mysql"}
    r = services.data.mutate_batch_delete(ci, "s", "t", [{"id": 1}, {"id": 2}])
    assert r["ok"] is True and r["affected"] == conn.execute.return_value.rowcount * 2


def test_mutate_batch_delete_mongo(monkeypatch):
    fake_coll = MagicMock()
    fake_coll.delete_many.return_value.deleted_count = 2
    fake_client = MagicMock()
    fake_client.__getitem__.return_value.__getitem__.return_value = fake_coll
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: fake_client)
    monkeypatch.setattr(services.data, "_mongo_oid", lambda v: v)
    ci = {"db_type": "mongodb"}
    r = services.data.mutate_batch_delete(ci, "s", "t", [{"_id": "a"}, {"_id": "b"}])
    assert r["affected"] == 2


def test_mutate_batch_delete_redis(monkeypatch):
    fake_r = MagicMock()
    fake_r.delete.return_value = 1
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ci = {"db_type": "redis"}
    r = services.data.mutate_batch_delete(ci, "", "t", [{"name": "k1"}, {"name": "k2"}])
    assert r["affected"] == 2


# ---------------- commit / rollback transaction ----------------
def test_commit_transaction(monkeypatch):
    fake_conn = MagicMock()
    monkeypatch.setattr(services.data, "TX_CONN", {("K", "tx9"): (fake_conn, None)})
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    assert services.data.commit_transaction({"db_type": "x"}, "tx9") is True
    fake_conn.commit.assert_called_once()
    fake_conn.close.assert_called_once()


def test_rollback_transaction(monkeypatch):
    fake_conn = MagicMock()
    monkeypatch.setattr(services.data, "TX_CONN", {("K", "tx9"): (fake_conn, None)})
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    assert services.data.rollback_transaction({"db_type": "x"}, "tx9") is True
    fake_conn.rollback.assert_called_once()


def test_commit_transaction_missing(monkeypatch):
    monkeypatch.setattr(services.data, "TX_CONN", {})
    monkeypatch.setattr(services.data, "conn_hash", lambda ci: "K")
    assert services.data.commit_transaction({"db_type": "x"}, "nope") is False
