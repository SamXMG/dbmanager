# -*- coding: utf-8 -*-
"""审计表保留上限清理(优化路线图 0.1)回归测试:
audit_log 超 MAX_AUDIT_ROWS 后自动删除最旧记录, 防无限增长。
用法: python tests/test_audit.py
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 数据层隔离: import sqlitedb 前把 DBM_DB_FILE 指到临时库, 防污染真实 dbmanager.db
_TMP = tempfile.mkdtemp(prefix="dbm_audit_")
os.environ["DBM_DB_FILE"] = os.path.join(_TMP, "dbmanager.db")

import sqlitedb  # noqa: E402

FAIL = []


def check(name, cond, extra=""):
    """pytest 兼容(2.2): 断言即失败标记, 同时保留 CLI 打印输出"""
    if cond:
        print("  ✓", name)
    else:
        print("  ✗", name, extra)
    assert cond, "%s %s" % (name, extra)


def main():
    # 调小上限与降频阈值便于测试(仅本次进程生效)
    sqlitedb.MAX_AUDIT_ROWS = 5
    sqlitedb._AUDIT_PRUNE_EVERY = 1

    # 清空既有审计(隔离库, 无历史)
    for r in sqlitedb.audit_query(limit=1000):
        pass  # 空库
    import sqlite3
    c = sqlite3.connect(sqlitedb.db_file())
    c.execute("DELETE FROM audit_log")
    c.commit(); c.close()

    # 写入 12 条 -> 每次写入触发清理, 最终应保留最近 5 条(id 最大)
    for i in range(12):
        sqlitedb.audit_add("127.0.0.1", "test_prune", "row_%d" % i, "tester")

    rows = sqlitedb.audit_query(limit=100)
    check("超上限后保留 MAX_AUDIT_ROWS 条", len(rows) == 5, "实际 %d" % len(rows))
    ids = sorted(r["id"] for r in rows)
    check("保留的是最旧的连续段", ids == list(range(max(ids) - 4, max(ids) + 1)),
          "ids=%s" % ids)
    check("最旧记录已删除", all("row_0" not in str(r.get("detail")) for r in rows))

    # 未超上限不删除
    for r in sqlitedb.audit_query(limit=1000):
        pass
    c = sqlite3.connect(sqlitedb.db_file())
    c.execute("DELETE FROM audit_log")
    c.commit(); c.close()
    for i in range(3):
        sqlitedb.audit_add("127.0.0.1", "test_prune", "small_%d" % i, "tester")
    rows2 = sqlitedb.audit_query(limit=100)
    check("未超上限全部保留", len(rows2) == 3, "实际 %d" % len(rows2))

    print()
    if FAIL:
        print("审计清理测试 FAIL: %d 项 -> %s" % (len(FAIL), FAIL))
        sys.exit(1)
    print("审计清理测试全部通过 ✓")


if __name__ == "__main__":
    main()
