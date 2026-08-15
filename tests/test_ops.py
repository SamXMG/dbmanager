# -*- coding: utf-8 -*-
"""ops 关键路径单测: 注入防护/语句拆分/方言引用/只读校验/备份还原往返
运行: python tests/test_ops.py  (unittest, 与 smoke_test.py 同风格)
"""
import os
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config  # noqa: E402
# P0-3 SQLite 路径沙箱: 测试库位于系统临时目录(绝对路径, 在 cwd/DATA_ROOT 之外),
# 仅测试进程内将临时目录加入允许根, 不弱化生产默认(cwd + DATA_ROOT)。
config.SQLITE_ALLOW_ROOTS = [tempfile.gettempdir()]

from ops import (  # noqa: E402
    _qi, backup_database, restore_sql, run_sql, safe_where_clause, split_sql_statements,
)


def _mk_db(path):
    c = sqlite3.connect(path)
    c.execute("CREATE TABLE emp (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, salary REAL, hire DATE)")
    c.execute("INSERT INTO emp (name, salary, hire) VALUES ('张三', 8000, '2020-01-01'), ('李四', 6000, '2021-06-15')")
    c.commit()
    c.close()


class TestSafeWhere(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(safe_where_clause("name like '%a%'", ["name", "id"]), "name like '%a%'")

    def test_comment_injection(self):
        for bad in ["1=1 -- drop", "1=1 /* x */", "1=1; drop table emp"]:
            with self.assertRaises(ValueError):
                safe_where_clause(bad, ["name", "id"])

    def test_invalid_column(self):
        with self.assertRaises(ValueError):
            safe_where_clause("secret_col = 1", ["name", "id"])

    def test_empty(self):
        self.assertEqual(safe_where_clause("", ["name"]), "")


class TestSplitSql(unittest.TestCase):
    def test_multiple(self):
        parts = split_sql_statements("SELECT 1; SELECT 2;\n\nSELECT 3")
        self.assertEqual([p.strip() for p in parts], ["SELECT 1", "SELECT 2", "SELECT 3"])

    def test_semicolon_in_string(self):
        parts = split_sql_statements("SELECT 'a;b' AS x; SELECT 'c' AS y")
        self.assertEqual(len(parts), 2)

    def test_empty_filtered(self):
        parts = split_sql_statements(";;SELECT 1;;")
        self.assertEqual([p.strip() for p in parts], ["SELECT 1"])


class TestQi(unittest.TestCase):
    def test_dialects(self):
        self.assertEqual(_qi("mssql", "PoJc"), "[PoJc]")
        self.assertEqual(_qi("mssql", "a]b"), "[a]]b]")
        self.assertEqual(_qi("mysql", "a`b"), "`a``b`")
        self.assertEqual(_qi("postgresql", 'a"b'), '"a""b"')
        self.assertEqual(_qi("sqlite", "t1"), '"t1"')
        self.assertEqual(_qi("oracle", "tab"), '"tab"')


class TestRunSqlReadonly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.mkdtemp()
        cls.db = os.path.join(cls._tmp, "t.db")
        _mk_db(cls.db)
        cls.ci = {"db_type": "sqlite", "database": cls.db, "pwd": ""}

    @classmethod
    def tearDownClass(cls):
        try:
            import shutil
            shutil.rmtree(cls._tmp, ignore_errors=True)
        except Exception:
            pass

    def test_select_ok(self):
        r = run_sql(self.ci, "SELECT name FROM emp")
        self.assertTrue(r["readonly"])
        self.assertEqual(r["results"][0]["total"], 2)

    def test_dml_blocked(self):
        for sql in ["INSERT INTO emp (name) VALUES ('x')", "DELETE FROM emp", "UPDATE emp SET name='x'", "DROP TABLE emp"]:
            with self.assertRaises(ValueError):
                run_sql(self.ci, sql)

    def test_select_into_blocked(self):
        with self.assertRaises(ValueError):
            run_sql(self.ci, "SELECT * INTO emp2 FROM emp")
        with self.assertRaises(ValueError):
            run_sql(self.ci, "SELECT * INTO OUTFILE '/tmp/x' FROM emp")

    def test_show_explain_ok(self):
        # 校验层放行(不保证执行成功); sqlite 上 EXPLAIN 可执行
        r = run_sql(self.ci, "EXPLAIN SELECT * FROM emp")
        self.assertTrue(r["readonly"])


class TestBackupRestore(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        # 释放引擎连接池, 便于清理临时文件(否则 Windows 上文件被占用)
        try:
            from core.config import ENGINE_CACHE
            for k, e in list(ENGINE_CACHE.items()):
                try:
                    e.dispose()
                except Exception:
                    pass
            ENGINE_CACHE.clear()
        except Exception:
            pass

    def test_roundtrip(self):
        with tempfile.TemporaryDirectory() as td:
            src = os.path.join(td, "src.db")
            dst = os.path.join(td, "dst.db")
            _mk_db(src)
            ci = {"db_type": "sqlite", "database": src, "pwd": ""}
            backup = backup_database(ci)
            sql_text = backup[0] if isinstance(backup, tuple) else backup
            self.assertIn("CREATE TABLE", sql_text)
            self.assertIn("张三", sql_text)
            # 还原到空库
            sqlite3.connect(dst).close()
            ci2 = {"db_type": "sqlite", "database": dst, "pwd": ""}
            r = restore_sql(ci2, sql_text)
            self.assertEqual(r["failed"], [], r["failed"])
            self.assertTrue(len(r["executed"]) > 0)
            c = sqlite3.connect(dst)
            cnt = c.execute("SELECT COUNT(*) FROM emp").fetchone()[0]
            names = [x[0] for x in c.execute("SELECT name FROM emp ORDER BY id")]
            c.close()
            self.assertEqual(cnt, 2)
            self.assertEqual(names, ["张三", "李四"])
            # 释放引擎连接池(Windows 下文件被占用无法删除)
            from core.config import ENGINE_CACHE
            for k, e in list(ENGINE_CACHE.items()):
                try:
                    e.dispose()
                except Exception:
                    pass
            ENGINE_CACHE.clear()


if __name__ == "__main__":
    unittest.main(verbosity=2)
