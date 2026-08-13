# -*- coding: utf-8 -*-
"""services/core 注入防护白名单 pytest 测试(优化路线图 2.2 增量, pytest 风格)。
覆盖: safe_where_clause 字段白名单/禁分号注释、_check_default 字面量白名单攻击样本。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from services.core import _check_default, _check_type, safe_where_clause

COLS = ["id", "name", "amount"]


# ---------- safe_where_clause: 注入攻击样本必须拒绝 ----------
@pytest.mark.parametrize("where", [
    "id UNION SELECT password FROM users",   # UNION 抽取
    "1; DROP TABLE users",                    # 分号多语句
    "id--",                                   # 注释
    "admin_col=1",                            # 未知字段
    "1) UNION SELECT 1",                      # 闭合子查询
    "id /* comment */",                       # 块注释
])
def test_where_rejects_injection(where):
    with pytest.raises(ValueError):
        safe_where_clause(where, COLS)


@pytest.mark.parametrize("where,expected", [
    ("name LIKE 'a%'", "name LIKE 'a%'"),
    ("amount > 100 AND name = 'x'", "amount > 100 AND name = 'x'"),
    ("id IN (1,2,3)", "id IN (1,2,3)"),
])
def test_where_allows_legit(where, expected):
    assert safe_where_clause(where, COLS) == expected


# ---------- _check_default: DEFAULT 字面量白名单 ----------
@pytest.mark.parametrize("default", [
    "(SELECT pwd FROM users)",        # 子查询
    "1; DROP TABLE users--",          # 分号+注释
    '"col"',                          # 标识符
    "USER()",                         # 带参函数
    "current_user() || 'x'",          # 拼接
])
def test_default_rejects_injection(default):
    with pytest.raises(ValueError):
        _check_default(default)


@pytest.mark.parametrize("default,expected", [
    ("0", "0"),
    ("-1.5", "-1.5"),
    ("'abc'", "'abc'"),
    ("N'abc'", "N'abc'"),
    ("NULL", "NULL"),
    ("CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP"),
    ("GETDATE()", "GETDATE()"),
    ("", ""),
    (None, ""),
])
def test_default_allows_literals(default, expected):
    assert _check_default(default) == expected


# ---------- _check_type: 类型名白名单 ----------
@pytest.mark.parametrize("bad", [
    "INT; DROP TABLE users",
    "VARCHAR(10) -- x",
    "INT' OR '1'='1",
])
def test_type_rejects_injection(bad):
    with pytest.raises(ValueError):
        _check_type(bad)


@pytest.mark.parametrize("good", ["INT", "VARCHAR(100)", "DECIMAL(10,2)"])
def test_type_allows_legit(good):
    assert _check_type(good) == good
