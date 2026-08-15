# -*- coding: utf-8 -*-
"""跨方言核心路径证据: 复用 DB Manager 自身数据访问层跑通 MySQL/PostgreSQL。

目的
----
证明 dbmanager 自带的连接/查询/元数据代码能跨方言工作, 而非另写一套裸 driver。
复用的内部函数(均来自应用自身代码, 非测试内联实现):
  - dbcore.get_engine(ci)         dbcore.py:203   建引擎 + SELECT 1 连通性自检
  - services.sql.run_sql(...)     services/sql.py:10  走 get_engine 执行 SQL
  - services.metadata.get_tables  services/metadata.py:61  方言感知的表清单反射
  - services.metadata.get_columns services/metadata.py:149 列元数据反射

对每个可用库跑通 4 类核心路径:
  ① 连接建立  ② 简单查询(SELECT VERSION())  ③ 读取 schema(列)  ④ 基础 DDL(建表+删表)

环境复现(本地起库并设变量; 任一未设则该库用例 pytest.skip, 不影响默认 SQLite CI):
  docker run -d --name dbm-mysql -e MYSQL_ROOT_PASSWORD=root \
    -e MYSQL_DATABASE=dbm_test -e MYSQL_USER=dbm -e MYSQL_PASSWORD=dbm \
    -p 3306:3306 mysql:8
  docker run -d --name dbm-pg -e POSTGRES_DB=dbm_test \
    -e POSTGRES_USER=dbm -e POSTGRES_PASSWORD=dbm -p 5432:5432 postgres:16

  export DBM_TEST_MYSQL_URL="mysql+pymysql://dbm:dbm@127.0.0.1:3306/dbm_test"
  export DBM_TEST_PG_URL="postgresql://dbm:dbm@127.0.0.1:5432/dbm_test"

  pytest tests/multidb_core.py -v

说明: 环境变量里的 URL 仅用于取连接参数; dbcore.build_url 会按 DB Manager 既定
驱动重建连接串(MySQL -> mysql+pymysql, PostgreSQL -> postgresql+pg8000), 因此测的是
应用真实路径。库用户名/库名需与 docker 命令一致。
"""
import os
import sys

# 让 tests/ 下的模块能 import 仓库根的导出(dbcore / config / services.*)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from db.dbcore import get_engine                       # dbcore.py:203
from services.sql import run_sql                    # services/sql.py:10
from services.metadata import get_tables, get_columns  # metadata.py:61 / :149

MYSQL_URL = os.environ.get("DBM_TEST_MYSQL_URL")
PG_URL = os.environ.get("DBM_TEST_PG_URL")

PROBE = "dbm_core_probe"
_DEFAULT_PORT = {"mysql": 3306, "postgresql": 5432}


def _ci_from_url(url):
    """把 SQLAlchemy 风格 URL 解析为 DB Manager 的连接信息 dict(ci)。
    只取驱动类型作 db_type, 真正驱动由 dbcore.build_url 决定(重建连接串)。"""
    u = make_url(url)
    db_type = u.drivername.split("+")[0].lower()
    if db_type not in ("mysql", "postgresql"):
        raise ValueError("本测试仅覆盖 mysql / postgresql, 收到: %s" % u.drivername)
    return {
        "db_type": db_type,
        "server": u.host or "localhost",
        "port": u.port or _DEFAULT_PORT[db_type],
        "uid": u.username or "",
        "pwd": u.password or "",
        "database": u.database or "",
    }


def _run_core_paths(ci, db_type):
    """对单个库跑通 4 类核心路径, 断言用标准 pytest assert。

    ① 连接建立: get_engine 内部已 SELECT 1 自检, 返回 Engine 即成功。
    ② 简单查询: run_sql 走 get_engine 执行 SELECT VERSION()。
    ③④ 基础 DDL + schema 读取: 建探针表 -> 反射列 -> 删表(幂等, finally 兜底)。
    """
    # ① 连接建立
    engine = get_engine(ci)
    assert isinstance(engine, Engine), "get_engine 未返回 SQLAlchemy Engine"
    assert engine is not None

    # ② 简单查询(取版本)。VERSION() 在 MySQL/PG 均可用, 无需方言分支。
    r = run_sql(ci, "SELECT VERSION() AS v", write=False)
    assert r.get("ok") is True, "SELECT VERSION() 执行失败: %r" % r
    sel = r["results"][0]
    assert sel["rows"], "版本查询无返回行"
    assert "v" in sel["rows"][0], "版本查询缺少列 v"

    # ③ + ④ 基础 DDL(建表)与 schema 读取(列反射)。类型 INT/VARCHAR 两库通用, 最小分支。
    ddl_create = (
        "CREATE TABLE IF NOT EXISTS %s (id INT PRIMARY KEY, name VARCHAR(64))" % PROBE
    )
    run_sql(ci, ddl_create, write=True)

    try:
        # ③ 读取 schema: 表清单中应包含探针表
        tables = get_tables(ci)
        assert isinstance(tables, list), "get_tables 返回非列表"
        names = {t["name"] for t in tables}
        assert PROBE in names, "建表后 get_tables 未列出 %s, 实际: %r" % (PROBE, list(names)[:20])

        # ③ 读取 schema: 列反射应包含 id / name
        schema = next((t.get("schema") for t in tables if t["name"] == PROBE), None)
        cols = get_columns(ci, schema, PROBE)
        assert isinstance(cols, list) and cols, "get_columns 未返回列"
        col_names = {c["name"] for c in cols}
        assert {"id", "name"} <= col_names, "列反射缺失, 实际: %r" % col_names
    finally:
        # ④ / 清理: 删表(幂等)
        run_sql(ci, "DROP TABLE IF EXISTS %s" % PROBE, write=True)


@pytest.mark.skipif(MYSQL_URL is None, reason="DBM_TEST_MYSQL_URL 未设置, 跳过 MySQL 用例")
def test_mysql_core():
    _run_core_paths(_ci_from_url(MYSQL_URL), "mysql")


@pytest.mark.skipif(PG_URL is None, reason="DBM_TEST_PG_URL 未设置, 跳过 PostgreSQL 用例")
def test_postgresql_core():
    _run_core_paths(_ci_from_url(PG_URL), "postgresql")
