# -*- coding: utf-8 -*-
"""services/nosql 单测(M2-2): Mongo/Redis 文档与 KV 形态转换、查询安全校验。无真库。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

import services.nosql as nosql

try:
    from bson import ObjectId
    _HAS_BSON = True
except Exception:
    _HAS_BSON = False


# ---------- _mongo_doc_to_row ----------
def test_mongo_doc_to_row_basic():
    doc = {"_id": "abc", "name": "张三", "nested": {"k": 1}, "lst": [1, 2]}
    row = nosql._mongo_doc_to_row(doc)
    assert row["_id"] == "abc"
    assert row["name"] == "张三"
    assert row["nested"] == '{"k": 1}'
    assert row["lst"] == '[1, 2]'


def test_mongo_doc_to_row_no_id():
    row = nosql._mongo_doc_to_row({"a": 1, "b": "x"})
    assert row == {"a": 1, "b": "x"}


# ---------- _mongo_cols ----------
def test_mongo_cols_union_with_id_first():
    coll = MagicMock()
    coll.find.return_value = iter([{"_id": 1, "a": 1}, {"b": 2}])
    db = MagicMock()
    db.__getitem__.return_value = coll
    client = MagicMock()
    client.__getitem__.return_value = db
    cols = nosql._mongo_cols(client, "db", "c")
    assert cols == [{"name": "_id", "type": "mixed"},
                    {"name": "a", "type": "mixed"},
                    {"name": "b", "type": "mixed"}]


def test_mongo_cols_find_error_returns_empty():
    coll = MagicMock()
    coll.find.side_effect = Exception("boom")
    db = MagicMock()
    db.__getitem__.return_value = coll
    client = MagicMock()
    client.__getitem__.return_value = db
    assert nosql._mongo_cols(client, "db", "c") == []


# ---------- _mongo_oid ----------
def test_mongo_oid():
    if _HAS_BSON:
        r = nosql._mongo_oid("507f1f77bcf86cd799439011")
        assert isinstance(r, ObjectId)
        # 非 hex 字符串 -> ObjectId 抛错, 原样返回
        assert nosql._mongo_oid("not-a-hex") == "not-a-hex"
    else:
        assert nosql._mongo_oid("abc") == "abc"


# ---------- _redis_type_label ----------
def test_redis_type_label():
    assert nosql._redis_type_label("string") == "String"
    assert nosql._redis_type_label("hash") == "Hash"
    assert nosql._redis_type_label("list") == "List"
    assert nosql._redis_type_label("set") == "Set"
    assert nosql._redis_type_label("zset") == "ZSet"
    assert nosql._redis_type_label("none") == "Key"
    assert nosql._redis_type_label("") == "Key"
    assert nosql._redis_type_label("unknown") == "Key"


# ---------- _redis_rows ----------
def test_redis_rows_string():
    r = MagicMock()
    r.type.return_value = "string"
    r.get.return_value = "v"
    cols, rows, total = nosql._redis_rows(r, "k")
    assert cols == [{"name": "value"}]
    assert rows == [{"value": "v"}]
    assert total == 1


def test_redis_rows_hash():
    r = MagicMock()
    r.type.return_value = "hash"
    r.hgetall.return_value = {"f": "v"}
    cols, rows, total = nosql._redis_rows(r, "k")
    assert cols == [{"name": "field"}, {"name": "value"}]
    assert rows == [{"field": "f", "value": "v"}]
    assert total == 1


def test_redis_rows_list():
    r = MagicMock()
    r.type.return_value = "list"
    r.lrange.return_value = ["a", "b"]
    r.llen.return_value = 2
    cols, rows, total = nosql._redis_rows(r, "k")
    assert rows == [{"index": 0, "value": "a"}, {"index": 1, "value": "b"}]
    assert total == 2


def test_redis_rows_set():
    r = MagicMock()
    r.type.return_value = "set"
    r.smembers.return_value = {"b", "a"}
    r.scard.return_value = 2
    cols, rows, total = nosql._redis_rows(r, "k")
    assert rows == [{"value": "a"}, {"value": "b"}]  # sorted
    assert total == 2


def test_redis_rows_zset():
    r = MagicMock()
    r.type.return_value = "zset"
    r.zrange.return_value = [("m", 1.0)]
    r.zcard.return_value = 1
    cols, rows, total = nosql._redis_rows(r, "k")
    assert cols == [{"name": "member"}, {"name": "score"}]
    assert rows == [{"member": "m", "score": 1.0}]
    assert total == 1


def test_redis_rows_unknown():
    r = MagicMock()
    r.type.return_value = "none"
    cols, rows, total = nosql._redis_rows(r, "k")
    assert rows == [{"value": "(空)"}]
    assert total == 0


# ---------- _parse_mongo_filter ----------
def test_parse_mongo_filter_empty():
    assert nosql._parse_mongo_filter("") == {}
    assert nosql._parse_mongo_filter("   ") == {}


def test_parse_mongo_filter_valid():
    assert nosql._parse_mongo_filter('{"age": {"$gt": 30}}') == {"age": {"$gt": 30}}


def test_parse_mongo_filter_non_json():
    import pytest
    with pytest.raises(ValueError):
        nosql._parse_mongo_filter("age > 30")


def test_parse_mongo_filter_non_object():
    import pytest
    with pytest.raises(ValueError):
        nosql._parse_mongo_filter("[1,2,3]")


def test_parse_mongo_filter_blocked_op():
    import pytest
    with pytest.raises(ValueError):
        nosql._parse_mongo_filter('{"$where": "this.x == 1"}')


# ---------- _reject_mongo_ops ----------
def test_reject_mongo_ops_clean():
    nosql._reject_mongo_ops({"a": 1, "b": [{"c": 2}]})  # 不抛


def test_reject_mongo_ops_nested_blocked():
    import pytest
    with pytest.raises(ValueError):
        nosql._reject_mongo_ops({"a": {"$function": "x"}})


def test_reject_mongo_ops_depth_limit():
    # 构造超深嵌套, 靠 depth>12 截断, 不应无限递归
    deep = {}
    cur = deep
    for _ in range(20):
        nxt = {}
        cur["k"] = nxt
        cur = nxt
    nosql._reject_mongo_ops(deep)  # 不抛
