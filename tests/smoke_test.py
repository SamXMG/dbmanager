# -*- coding: utf-8 -*-
"""dbmanager 冒烟测试: 用临时目录 + SQLite 覆盖核心路径(连接/加密/表/分页/CRUD/只读SQL/导出/注入防护)。
运行: python tests/smoke_test.py   (需已安装 requirements.txt)
说明: 测试不会改动项目目录内的 connections.json / 密钥文件(连接存储与密钥写入临时目录)。
"""
import os
import sys
import tempfile
import unittest

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE)

import config
# P0-3 SQLite 路径沙箱: 测试库位于系统临时目录(绝对路径, 在 cwd/DATA_ROOT 之外),
# 仅测试进程内将临时目录加入允许根, 不弱化生产默认(cwd + DATA_ROOT)。
config.SQLITE_ALLOW_ROOTS = [tempfile.gettempdir()]
import crypto
from crypto import decrypt_pwd, encrypt_pwd
from dbcore import create_engine, get_engine, text
from ops import (
    export_data, export_schema_doc, get_columns, get_data, get_pk,
    get_tables, mutate, run_sql, safe_where_clause,
)
from store import (
    delete_connection, get_connection_by_name, list_connections, save_connection,
)

SQLITE_DB = os.path.join(tempfile.mkdtemp(), "smoke.db")


def make_ci():
    return {"db_type": "sqlite", "database": SQLITE_DB}


def _ddl():
    return ("CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL, age INTEGER, email TEXT)")


def _seed():
    return ("INSERT INTO users (name, age, email) VALUES "
            "('Alice', 20, 'a@x.com'), ('Bob', 30, 'b@x.com'), "
            "('Carol', 40, 'c@x.com'), ('Dan', 50, 'd@x.com')")


class TestCrypto(unittest.TestCase):
    """密码加密/解密往返(存储层不落明文)"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._old_base = config.BASE_DIR
        config.BASE_DIR = self._tmp

    def tearDown(self):
        config.BASE_DIR = self._old_base

    def test_dpapi_roundtrip(self):
        if not crypto._use_dpapi():
            self.skipTest("非 Windows 环境")
        blob = encrypt_pwd("s3cret@密码")
        self.assertTrue(blob.startswith("v2:"))
        self.assertNotIn("s3cret", blob)
        self.assertEqual(decrypt_pwd(blob), "s3cret@密码")

    def test_aes_roundtrip(self):
        old = crypto._use_dpapi
        crypto._use_dpapi = lambda: False  # 强制 AES-GCM 分支
        try:
            blob = encrypt_pwd("aes-pass")
            self.assertFalse(blob.startswith("v2:"))
            self.assertNotIn("aes-pass", blob)
            self.assertEqual(decrypt_pwd(blob), "aes-pass")
        finally:
            crypto._use_dpapi = old

    def test_empty(self):
        self.assertEqual(decrypt_pwd(""), "")
        self.assertEqual(encrypt_pwd(""), "")


class TestConnStore(unittest.TestCase):
    """连接保存/列出/读取/删除"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._old_base = config.BASE_DIR
        config.BASE_DIR = self._tmp

    def tearDown(self):
        config.BASE_DIR = self._old_base

    def test_save_list_get_delete(self):
        save_connection({"name": "t", "db_type": "sqlite",
                             "database": SQLITE_DB, "pwd": ""})
        lst = list_connections()
        self.assertEqual(len(lst), 1)
        self.assertNotIn("pwd", lst[0])          # 列表绝不带密码
        rec = get_connection_by_name("t")
        self.assertEqual(rec["database"], SQLITE_DB)
        delete_connection("t")
        self.assertEqual(list_connections(), [])

    def test_bad_type_rejected(self):
        with self.assertRaises(ValueError):
            save_connection({"name": "x", "db_type": "nosuchdb"})


class TestSqlite(unittest.TestCase):
    """核心数据链路: 元数据/分页/CRUD/只读SQL/导出/注入防护"""

    @classmethod
    def setUpClass(cls):
        cls.ci = make_ci()
        eng = create_engine("sqlite:///" + SQLITE_DB)
        with eng.begin() as c:
            c.execute(text(_ddl()))
            c.execute(text(_seed()))
        cls.eng = eng

    @classmethod
    def tearDownClass(cls):
        cls.eng.dispose()
        try:
            os.remove(SQLITE_DB)
        except OSError:
            pass

    def test_metadata(self):
        tabs = get_tables(self.ci)
        names = {t["name"] for t in tabs}
        self.assertIn("users", names)
        cols = {c["name"] for c in get_columns(self.ci, "", "users")}
        self.assertTrue({"id", "name", "age", "email"} <= cols)
        self.assertEqual(get_pk(self.ci, "", "users"), ["id"])

    def test_paging_and_where(self):
        d = get_data(self.ci, "", "users", 1, 2, "", "")
        self.assertEqual(d["total"], 4)
        self.assertEqual(len(d["rows"]), 2)
        d2 = get_data(self.ci, "", "users", 2, 2, "", "")
        self.assertEqual(d2["rows"][0]["id"], 3)   # 按主键排序分页
        d3 = get_data(self.ci, "", "users", 1, 10, "age > 25", "")
        self.assertEqual(d3["total"], 3)

    def test_mutate_and_count_invalidation(self):
        r = mutate(self.ci, "POST", "", "users",
                       {"values": {"name": "Zoe", "age": 99, "email": "z@x.com"}})
        self.assertTrue(r["ok"])
        d = get_data(self.ci, "", "users", 1, 10, "", "")
        self.assertEqual(d["total"], 5)            # count 缓存已失效
        new_id = d["rows"][-1]["id"]
        r = mutate(self.ci, "PUT", "", "users",
                       {"orig": {"id": new_id}, "values": {"age": 100}})
        self.assertTrue(r["ok"])
        d = get_data(self.ci, "", "users", 1, 10, "id = %d" % new_id, "")
        self.assertEqual(d["rows"][0]["age"], 100)
        r = mutate(self.ci, "DELETE", "", "users", {"orig": {"id": new_id}})
        self.assertTrue(r["ok"])
        d = get_data(self.ci, "", "users", 1, 10, "", "")
        self.assertEqual(d["total"], 4)

    def test_run_sql_readonly(self):
        r = run_sql(self.ci, "SELECT id, name FROM users ORDER BY id")
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["total"], 4)
        with self.assertRaises(ValueError):
            run_sql(self.ci, "DELETE FROM users")        # 写语句被拒
        with self.assertRaises(ValueError):
            run_sql(self.ci, "SELECT 1; DROP TABLE users")  # 含写语句整批被拒

    def test_run_sql_multi_statements(self):
        # 一条输入多条 SQL -> 每条结果独立返回(前端各占一个 tab)
        r = run_sql(self.ci, "SELECT 1 AS a; SELECT 2 AS b, 'x' AS c")
        self.assertTrue(r["ok"])
        self.assertEqual(len(r["results"]), 2)
        self.assertEqual(r["results"][0]["rows"][0]["a"], 1)
        self.assertEqual(r["results"][1]["rows"][0]["b"], 2)
        self.assertEqual(r["results"][1]["rows"][0]["c"], "x")

    def test_run_sql_semicolon_in_string(self):
        # 字符串/注释内的分号不能被当作语句分隔
        r = run_sql(self.ci, "SELECT 'a;b' AS v -- 分号在注释里; 不影响")
        self.assertEqual(len(r["results"]), 1)
        self.assertEqual(r["results"][0]["rows"][0]["v"], "a;b")

    def test_run_sql_write_mode(self):
        # 写模式: INSERT 成功且数据可见
        r = run_sql(self.ci,
                        "INSERT INTO users (name, age, email) VALUES ('写模式测试', 1, 'w@x.com')",
                        write=True)
        self.assertTrue(r["ok"])
        self.assertFalse(r["readonly"])
        self.assertEqual(r["results"][0]["affected"], 1)
        q = run_sql(self.ci, "SELECT COUNT(*) AS n FROM users WHERE name='写模式测试'")
        self.assertEqual(q["results"][0]["rows"][0]["n"], 1)

    def test_run_sql_write_rollback(self):
        # 写模式整批事务: 第二条失败 -> 第一条回滚(不产生半执行状态)
        with self.assertRaises(Exception):
            run_sql(self.ci,
                        "INSERT INTO users (name) VALUES ('回滚测试'); INSERT INTO 不存在的表 (x) VALUES (1)",
                        write=True)
        q = run_sql(self.ci, "SELECT COUNT(*) AS n FROM users WHERE name='回滚测试'")
        self.assertEqual(q["results"][0]["rows"][0]["n"], 0)

    def test_run_sql_large_result_truncated(self):
        # 1200 行: 服务端必须截断, 不能全量物化进内存
        eng = get_engine(self.ci)
        with eng.begin() as c:
            c.execute(text("CREATE TABLE big (id INTEGER)"))
            c.execute(text("INSERT INTO big (id) VALUES " +
                               ",".join("(%d)" % i for i in range(1200))))
        r = run_sql(self.ci, "SELECT * FROM big", limit=500)
        self.assertTrue(r["results"][0]["truncated"])
        self.assertEqual(len(r["results"][0]["rows"]), 500)

    def test_run_sql_auto_limit(self):
        # 未写 LIMIT 的 SELECT 会被服务端自动追加 LIMIT(结果仍正确)
        r = run_sql(self.ci, "SELECT name FROM users")
        self.assertTrue(r["ok"])
        self.assertEqual(r["results"][0]["total"], 4)

    def test_export(self):
        content, ctype, fn = export_data(self.ci, "", "users", "")
        self.assertIn("name", content)
        self.assertIn("csv", ctype)
        j, _jtype, _jfn = export_data(self.ci, "", "users", "", fmt="json")
        self.assertIn('"name"', j)
        md = export_schema_doc(self.ci)
        self.assertIn("users", md)
        self.assertIn("数据字典", md)

    def test_safe_where_rejects_injection(self):
        with self.assertRaises(ValueError):
            safe_where_clause("id=1; DROP TABLE users", ["id"])
        with self.assertRaises(ValueError):
            safe_where_clause("id=1 -- x", ["id"])
        with self.assertRaises(ValueError):
            safe_where_clause("unknown_col=1", ["id"])
        self.assertEqual(safe_where_clause("age > 25", ["id", "age"]), "age > 25")


if __name__ == "__main__":
    unittest.main(verbosity=2)
