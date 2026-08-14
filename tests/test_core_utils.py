# -*- coding: utf-8 -*-
"""services/core 纯工具函数单测(M2-2): escape_identifier / py_to_json /
split_sql_statements / _qi / _col_ddl / 元数据缓存。无 DB 依赖、无副作用。"""
import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services.core import (
    _clear_count_cache, _col_ddl, _meta_get, _meta_key, _meta_set,
    _qi, escape_identifier, py_to_json, split_sql_statements,
)


# ---------- escape_identifier: ] 转义防注入 ----------
@pytest.mark.parametrize("s,expected", [
    ("plain", "plain"),
    ("a]b", "a]]b"),
    ("", ""),
    ("col]]", "col]]]]"),
])
def test_escape_identifier(s, expected):
    assert escape_identifier(s) == expected


# ---------- py_to_json: 类型归并 ----------
def test_py_to_json_none():
    assert py_to_json(None) is None

def test_py_to_json_scalars():
    assert py_to_json(42) == 42
    assert py_to_json(3.14) == 3.14
    assert py_to_json("x") == "x"
    assert py_to_json(True) is True

def test_py_to_json_bytes():
    assert py_to_json(b"hello") == "hello"
    assert py_to_json(bytearray(b"x")) == "x"

def test_py_to_json_datetime():
    dt = datetime.datetime(2026, 1, 2, 3, 4, 5)
    assert py_to_json(dt) == "2026-01-02T03:04:05"

def test_py_to_json_fallback_to_str():
    assert py_to_json([1, 2]) == "[1, 2]"
    assert py_to_json({"a": 1}) == "{'a': 1}"


# ---------- split_sql_statements: 跳过字符串/注释内的分号 ----------
@pytest.mark.parametrize("sql,expected", [
    ("SELECT 1; SELECT 2", ["SELECT 1", "SELECT 2"]),
    ("SELECT 1;SELECT 2;SELECT 3", ["SELECT 1", "SELECT 2", "SELECT 3"]),
    ("SELECT ';' FROM t", ["SELECT ';' FROM t"]),
    ("SELECT 'it''s' FROM t", ["SELECT 'it''s' FROM t"]),
    ("SELECT 1 -- x; y", ["SELECT 1 -- x; y"]),
    ("/* a; b */ SELECT 1", ["/* a; b */ SELECT 1"]),
    ("SELECT 1;", ["SELECT 1"]),
    ("", []),
    ("   ", []),
])
def test_split_sql_statements(sql, expected):
    assert split_sql_statements(sql) == expected


# ---------- _qi: 按方言引用标识符 ----------
@pytest.mark.parametrize("dtype,name,expected", [
    ("mssql", "col", "[col]"),
    ("mssql", "a]b", "[a]]b]"),
    ("mysql", "col", "`col`"),
    ("mysql", "a`b", "`a``b`"),
    ("postgresql", "col", '"col"'),
    ("sqlite", "col", '"col"'),
])
def test_qi(dtype, name, expected):
    assert _qi(dtype, name) == expected


# ---------- _col_ddl: 列定义(类型 + 可空) ----------
@pytest.mark.parametrize("col,override,expected", [
    ({"type": "INT", "nullable": True}, None, "INT NULL"),
    ({"type": "INT", "nullable": False}, None, "INT NOT NULL"),
    ({"type": "VARCHAR(50)", "nullable": True}, False, "VARCHAR(50) NOT NULL"),
])
def test_col_ddl(col, override, expected):
    if override is None:
        assert _col_ddl(col) == expected
    else:
        assert _col_ddl(col, nullable_override=override) == expected


# ---------- 元数据缓存: get/set/缺失/失效清除 ----------
def test_meta_get_missing():
    assert _meta_get("__absent_key__") is None

def test_meta_set_get():
    _meta_set("__k1__", 123)
    assert _meta_get("__k1__") == 123
    _meta_set("__k1__", None)  # 清除
    assert _meta_get("__k1__") is None

def test_clear_count_cache_removes_only_matching():
    tgt = _meta_key("cnt", "h", "s", "t", "x")
    other = _meta_key("cnt", "h", "s", "other", "x")
    _meta_set(tgt, 5)
    _meta_set(other, 9)
    _clear_count_cache("h", "s", "t")
    assert _meta_get(tgt) is None
    assert _meta_get(other) == 9  # 不同表不受影响
