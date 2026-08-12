# -*- coding: utf-8 -*-
"""explain_query MSSQL 分支: 三批次执行顺序 + finally 关闭验证"""
import os
import sys, types
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch
from ops import explain_query

executed = []

class FakeResult:
    def __init__(self, rows):
        self._rows = rows
    def mappings(self):
        return self
    def fetchmany(self, n):
        return [dict(r) for r in self._rows]

class FakeConn:
    def execute(self, stmt):
        t = str(stmt)
        executed.append(t)
        if t == "SELECT TOP 10 * FROM Po2":
            return FakeResult([{"StmtText": "|--Table Scan", "StmtID": 1}])
        return FakeResult([])

class FakeEngine:
    def connect(self):
        return _ctx(self)

class _ctx:
    def __init__(self, eng):
        self._eng = eng
    def __enter__(self):
        self.conn = FakeConn()
        return self.conn
    def __exit__(self, *a):
        return False

ci = {"db_type": "mssql", "server": "x", "database": "y", "uid": "u", "pwd": "p"}

with patch('services.sql.get_engine', return_value=FakeEngine()):
    r = explain_query(ci, "SELECT TOP 10 * FROM Po2;")
    print('结果行数:', r['total'], '| mode:', r['mode'])
    print('执行序列:', executed)
    assert executed == ["SET SHOWPLAN_ALL ON", "SELECT TOP 10 * FROM Po2", "SET SHOWPLAN_ALL OFF"], '执行顺序错误'
    assert r['total'] == 1 and r['rows'][0]['StmtText'] == '|--Table Scan', '计划行解析错误'
    print('PASS 正常路径: ON -> SELECT -> OFF 顺序正确, 计划行解析正确')

# 异常路径: SELECT 抛错时 OFF 仍执行
executed.clear()
class BoomConn(FakeConn):
    def execute(self, stmt):
        t = str(stmt)
        executed.append(t)
        if t.startswith("SELECT"):
            raise RuntimeError("SQL 错误")
        return FakeResult([])
class BoomEngine:
    def connect(self):
        return _ctx2(self)
class _ctx2:
    def __init__(self, eng): pass
    def __enter__(self):
        self.conn = BoomConn()
        return self.conn
    def __exit__(self, *a): return False

with patch('services.sql.get_engine', return_value=BoomEngine()):
    try:
        explain_query(ci, "SELECT * FROM nope")
        print('FAIL 应抛出异常')
    except RuntimeError:
        print('执行序列(异常路径):', executed)
        assert executed == ["SET SHOWPLAN_ALL ON", "SELECT * FROM nope", "SET SHOWPLAN_ALL OFF"], 'finally 未执行 OFF'
        print('PASS 异常路径: SELECT 失败后 OFF 仍执行(finally 兜底)')

print('\n===== 全部通过 =====')
