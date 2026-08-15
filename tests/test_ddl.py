# -*- coding: utf-8 -*-
"""services/ddl 单测(M2-3): MongoDB/Redis 集合键操作 + 关系库方言 DDL 生成。桩 dbcore。"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock

from sqlalchemy.exc import ResourceClosedError

from db import dbcore
import services.ddl as ddl


# ---------- MongoDB ----------
def test_ddl_mongo_create(monkeypatch):
    fake_db = MagicMock()
    client = MagicMock()
    client.__getitem__.return_value = fake_db
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: client)
    r = ddl.alter_table({"db_type": "mongodb"}, "s", "t", "create_table", {})
    assert r == {"ok": True}
    fake_db.create_collection.assert_called_once_with("t")


def test_ddl_mongo_drop(monkeypatch):
    coll = MagicMock()
    fake_db = MagicMock()
    fake_db.__getitem__.return_value = coll
    client = MagicMock()
    client.__getitem__.return_value = fake_db
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: client)
    r = ddl.alter_table({"db_type": "mongodb"}, "s", "t", "drop_table", {})
    assert r == {"ok": True}
    coll.drop.assert_called_once()


def test_ddl_mongo_unsupported(monkeypatch):
    import pytest
    client = MagicMock()
    monkeypatch.setattr(dbcore, "get_mongo", lambda ci: client)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mongodb"}, "s", "t", "add_column", {"name": "c"})


# ---------- Redis ----------
def test_ddl_redis_create_string(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    r = ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                        {"type": "string", "value": "v"})
    assert r == {"ok": True}
    fake_r.set.assert_called_once_with("k", "v")


def test_ddl_redis_create_hash(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                    {"type": "hash", "value": "v"})
    fake_r.hset.assert_called_once_with("k", mapping={"v": ""})


def test_ddl_redis_create_list(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                    {"type": "list", "value": "v"})
    fake_r.rpush.assert_called_once_with("k", "v")


def test_ddl_redis_create_set(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                    {"type": "set", "value": "v"})
    fake_r.sadd.assert_called_once_with("k", "v")


def test_ddl_redis_create_zset(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                    {"type": "zset", "value": "v"})
    fake_r.zadd.assert_called_once_with("k", {"v": 0})


def test_ddl_redis_create_with_ttl(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                    {"type": "string", "value": "v", "ttl": 60})
    fake_r.expire.assert_called_once_with("k", 60)


def test_ddl_redis_create_bad_type(monkeypatch):
    import pytest
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "redis"}, "", "k", "create",
                        {"type": "bitmap", "value": "v"})


def test_ddl_redis_drop(monkeypatch):
    fake_r = MagicMock()
    fake_r.delete.return_value = 5
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    r = ddl.alter_table({"db_type": "redis"}, "", "k", "drop", {})
    assert r == {"ok": True, "affected": 5}


def test_ddl_redis_set_ttl_none(monkeypatch):
    fake_r = MagicMock()
    fake_r.ttl.return_value = 99
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    r = ddl.alter_table({"db_type": "redis"}, "", "k", "set_ttl", {})
    assert r == {"ok": True, "ttl": 99}


def test_ddl_redis_set_ttl_positive(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    r = ddl.alter_table({"db_type": "redis"}, "", "k", "set_ttl", {"ttl": 30})
    assert r == {"ok": True, "ttl": 30}
    fake_r.expire.assert_called_once_with("k", 30)


def test_ddl_redis_set_ttl_nonpositive(monkeypatch):
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    ddl.alter_table({"db_type": "redis"}, "", "k", "set_ttl", {"ttl": 0})
    fake_r.persist.assert_called_once_with("k")


def test_ddl_redis_unsupported(monkeypatch):
    import pytest
    fake_r = MagicMock()
    monkeypatch.setattr(dbcore, "get_redis", lambda ci: fake_r)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "redis"}, "", "k", "add_index", {"name": "x"})


# ---------- 关系库: 引擎构造 ----------
def _sql_engine():
    engine = MagicMock()
    conn = MagicMock()
    result = MagicMock()
    result.mappings.return_value.fetchall.return_value = []
    conn.execute.return_value = result
    engine.connect.return_value.__enter__.return_value = conn
    engine.connect.return_value.__exit__.return_value = False
    return engine, conn


def _ddls(conn):
    return [c.args[0].text for c in conn.execute.call_args_list]


# ---------- rename / truncate / clear / copy / maintain ----------
def test_ddl_rename_mysql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "mysql"}, "s", "t", "rename_table",
                        {"new_name": "t2"})
    assert r == {"ok": True, "old": "t", "new": "t2"}
    assert "RENAME TABLE `s`.`t` TO `s`.`t2`" in _ddls(conn)


def test_ddl_rename_same_name(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mysql"}, "s", "t", "rename_table",
                        {"new_name": "t"})


def test_ddl_truncate_mysql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "mysql"}, "s", "t", "truncate_table", {})
    assert r == {"ok": True, "truncated": True}
    assert "TRUNCATE TABLE `s`.`t`" in _ddls(conn)


def test_ddl_truncate_sqlite_clears_sequence(monkeypatch):
    engine, conn = _sql_engine()
    # 第二次执行(sqlite_sequence)抛错 -> 被 except 吞掉
    conn.execute.side_effect = [None, Exception("no such table")]
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "sqlite"}, "s", "t", "truncate_table", {})
    assert r["truncated"] is True


def test_ddl_clear_table(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "mysql"}, "s", "t", "clear_table", {})
    assert r == {"ok": True, "cleared": True}
    assert "DELETE FROM `s`.`t`" in _ddls(conn)


def test_ddl_copy_mysql_with_data(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "mysql"}, "s", "t", "copy_table",
                        {"new_name": "t2", "with_data": True})
    assert r["new_table"] == "t2"
    ddls = _ddls(conn)
    assert "CREATE TABLE `s`.`t2` LIKE `s`.`t`" in ddls
    assert "INSERT INTO `s`.`t2` SELECT * FROM `s`.`t`" in ddls


def test_ddl_copy_mysql_without_data(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "copy_table",
                    {"new_name": "t2", "with_data": False})
    assert "INSERT INTO" not in " ".join(_ddls(conn))


def test_ddl_copy_same_name(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mysql"}, "s", "t", "copy_table",
                        {"new_name": "t"})


def test_ddl_maintain_mysql_check(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "mysql"}, "s", "t", "maintain",
                        {"op": "check"})
    assert r["op"] == "check"
    assert "CHECK TABLE `s`.`t`" in _ddls(conn)


def test_ddl_maintain_resource_closed(monkeypatch):
    engine, conn = _sql_engine()
    conn.execute.side_effect = ResourceClosedError("no rows")
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    r = ddl.alter_table({"db_type": "mysql"}, "s", "t", "maintain",
                        {"op": "check"})
    assert r["ok"] is True
    assert r["rows"] == []  # ResourceClosedError -> 空行


# ---------- 列/索引可视化 DDL(方言) ----------
def test_ddl_add_column_mysql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "add_column",
                    {"name": "c", "type": "VARCHAR(50)", "nullable": True, "default": "0"})
    assert "ALTER TABLE `s`.`t` ADD COLUMN `c` VARCHAR(50) NULL DEFAULT 0" in _ddls(conn)


def test_ddl_add_column_mssql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mssql"}, "s", "t", "add_column",
                    {"name": "c", "type": "INT", "nullable": False})
    assert "ALTER TABLE [s].[t] ADD [c] INT NOT NULL" in _ddls(conn)


def test_ddl_add_column_postgresql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "postgresql"}, "s", "t", "add_column",
                    {"name": "c", "type": "TEXT", "nullable": False})
    assert 'ALTER TABLE "s"."t" ADD COLUMN "c" TEXT NOT NULL' in _ddls(conn)


def test_ddl_add_column_missing(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mysql"}, "s", "t", "add_column",
                        {"name": "", "type": ""})


def test_ddl_drop_column_mysql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "drop_column", {"name": "c"})
    assert "ALTER TABLE `s`.`t` DROP COLUMN `c`" in _ddls(conn)


def test_ddl_drop_column_missing(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mysql"}, "s", "t", "drop_column", {"name": ""})


def test_ddl_modify_column_mysql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "modify_column",
                    {"name": "c", "type": "INT", "nullable": False})
    assert "ALTER TABLE `s`.`t` MODIFY COLUMN `c` INT NOT NULL" in _ddls(conn)


def test_ddl_modify_column_mssql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mssql"}, "s", "t", "modify_column",
                    {"name": "c", "type": "INT", "nullable": False})
    assert "ALTER TABLE [s].[t] ALTER COLUMN [c] INT NOT NULL" in _ddls(conn)


def test_ddl_modify_column_postgresql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "postgresql"}, "s", "t", "modify_column",
                    {"name": "c", "type": "INT", "nullable": True})
    ddls = _ddls(conn)
    assert 'ALTER TABLE "s"."t" ALTER COLUMN "c" TYPE INT' in ddls
    assert 'ALTER TABLE "s"."t" ALTER COLUMN "c" DROP NOT NULL' in ddls


def test_ddl_add_index_mysql_unique(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "add_index",
                    {"name": "ix", "columns": ["a", "b"], "unique": True})
    assert "ALTER TABLE `s`.`t` ADD UNIQUE INDEX `ix` (`a`, `b`)" in _ddls(conn)


def test_ddl_add_index_mysql_no_name(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "add_index",
                    {"columns": ["a", "b"]})
    assert "ALTER TABLE `s`.`t` ADD INDEX `idx_a_b` (`a`, `b`)" in _ddls(conn)


def test_ddl_add_index_missing_columns(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mysql"}, "s", "t", "add_index",
                        {"name": "ix", "columns": []})


def test_ddl_drop_index_mysql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mysql"}, "s", "t", "drop_index", {"name": "ix"})
    assert "ALTER TABLE `s`.`t` DROP INDEX `ix`" in _ddls(conn)


def test_ddl_drop_index_mssql(monkeypatch):
    engine, conn = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    ddl.alter_table({"db_type": "mssql"}, "s", "t", "drop_index", {"name": "ix"})
    assert "DROP INDEX [ix] ON [s].[t]" in _ddls(conn)


def test_ddl_drop_index_missing(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "mysql"}, "s", "t", "drop_index", {"name": ""})


def test_ddl_sqlite_visual_ddl_unsupported(monkeypatch):
    import pytest
    engine, _ = _sql_engine()
    monkeypatch.setattr(ddl, "get_engine", lambda ci: engine)
    with pytest.raises(ValueError):
        ddl.alter_table({"db_type": "sqlite"}, "s", "t", "add_column",
                        {"name": "c", "type": "INT"})
