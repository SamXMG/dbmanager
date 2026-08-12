# -*- coding: utf-8 -*-
"""dbmanager - ops 数据工具: 跨库传输/统计/测试数据生成"""
import random

from sqlalchemy import MetaData, Table, inspect, select, text

from dbcore import get_engine
from services.core import _qi
from services.metadata import get_columns


def transfer_data(ci, from_schema, from_table, to_db, to_schema, to_table, batch=500):
    """数据级同步: 源表全部数据流式读取 → 批量插入目标表(同连接或跨库)。
    列按同名交集传输; 目标自增主键跳过由数据库生成; 目标表需已存在。"""
    if (ci.get("db_type") or "") in ("mongodb", "redis"):
        raise ValueError("该数据库类型不支持数据传输")
    t = (ci.get("db_type") or "mysql").lower()
    if not from_table or not to_table:
        raise ValueError("源表与目标表不能为空")
    # 目标库: 跨库时重建引擎; 目标 schema 按方言推断(MySQL=库, MSSQL=dbo, SQLite=main, PG=public)
    if not to_schema:
        if t in ("mysql", "mariadb", "oceanbase", "tidb"):
            to_schema = to_db
        elif t == "mssql":
            to_schema = "dbo"
        elif t == "sqlite":
            to_schema = "main"
        else:
            to_schema = "public"
    dst_ci = dict(ci)
    # SQLite 的 database 即文件路径, to_db 传目标文件即可跨库; 其余库传库名
    if to_db and t not in ("mongodb", "redis"):
        dst_ci["database"] = to_db
    src_engine = get_engine(ci)
    dst_engine = get_engine(dst_ci)
    meta = MetaData()
    src = Table(from_table, meta, autoload_with=src_engine, schema=from_schema or None)
    dst = Table(to_table, meta, autoload_with=dst_engine, schema=to_schema or None)
    # 同名列交集
    src_names = {c.name for c in src.columns}
    common = [c.name for c in dst.columns if c.name in src_names]
    if not common:
        raise ValueError("源表与目标表无公共列")
    # 目标自增主键跳过(由数据库生成)
    dst_pk = []
    try:
        insp = inspect(dst_engine)
        pk = insp.get_pk_constraint(to_table, schema=to_schema or None) or {}
        dst_pk = pk.get("constrained_columns") or []
    except Exception:
        dst_pk = []
    cols_to_insert = [n for n in common if not (n in dst_pk and any(
        c.name == n and c.autoincrement for c in dst.columns))]
    if not cols_to_insert:
        raise ValueError("目标表无可插入列")
    sel_cols = [src.columns[n] for n in cols_to_insert]
    total = 0
    with src_engine.connect() as sconn:
        result = sconn.execution_options(stream_results=True).execute(select(*sel_cols))
        while True:
            chunk = result.fetchmany(batch)
            if not chunk:
                break
            rows = [dict(zip(cols_to_insert, r)) for r in chunk]
            with dst_engine.begin() as dconn:
                dconn.execute(dst.insert(), rows)
            total += len(rows)
    return {"ok": True, "transferred": total, "columns": cols_to_insert}


def stats_column(ci, schema, table, col, where=""):
    """列统计: COUNT + MIN/MAX(通用) + SUM/AVG(数值列)"""
    if (ci.get("db_type") or "") in ("mongodb", "redis"):
        raise ValueError("该数据库类型不支持列统计")
    t = (ci.get("db_type") or "mysql").lower()
    # 按列类型判断是否数值(避免 SQLite 对文本 SUM 静默返回 0)
    ctype = ""
    try:
        ctype = next((c.get("type", "") for c in get_columns(ci, schema, table) if c.get("name") == col), "")
    except Exception:
        pass
    is_num = any(k in str(ctype).upper() for k in ("INT", "DECIMAL", "NUMERIC", "FLOAT", "REAL", "DOUBLE", "MONEY", "NUM"))
    q = _qi(t, col)
    full = ((_qi(t, schema) + ".") if schema else "") + _qi(t, table)
    w = (" WHERE " + where.strip()) if (where or "").strip() else ""
    with get_engine(ci).connect() as conn:
        row = conn.execute(text("SELECT COUNT(*) AS cnt, MIN(%s) AS mn, MAX(%s) AS mx FROM %s%s" % (q, q, full, w))).mappings().first()
    r = {"count": row["cnt"], "min": row["mn"], "max": row["mx"]}
    if is_num:
        try:  # 数值列 SUM/AVG
            with get_engine(ci).connect() as conn:
                row2 = conn.execute(text("SELECT SUM(%s) AS sm, AVG(%s) AS av FROM %s%s" % (q, q, full, w))).mappings().first()
            r["sum"] = row2["sm"]
            r["avg"] = row2["av"]
        except Exception:
            pass
    return r


def gen_data(ci, schema, table, rows):
    """按列类型生成随机测试数据并批量插入(自增/主键整数/只读列跳过)"""
    if (ci.get("db_type") or "") in ("mongodb", "redis"):
        raise ValueError("该数据库类型不支持生成测试数据")
    if not rows or rows < 1 or rows > 50000:
        raise ValueError("行数需在 1-50000 之间")
    cols = get_columns(ci, schema, table)
    usable = [c for c in cols
              if not c.get("identity")
              and not (c.get("is_pk") and "INT" in (c.get("type") or "").upper())]
    if not usable:
        raise ValueError("所有列都是自增/主键/只读列, 无法生成数据")

    def gen_val(col):
        typ = (col.get("type") or "").upper()
        if "INT" in typ or typ in ("BIGINT", "SMALLINT", "TINYINT"):
            return random.randint(1, 99999)
        if any(k in typ for k in ("DECIMAL", "NUMERIC", "FLOAT", "REAL", "DOUBLE")):
            return round(random.uniform(0, 100000), 2)
        if "DATE" in typ:
            import datetime as _dt
            return _dt.date(random.randint(2015, 2026), random.randint(1, 12), random.randint(1, 28))
        if "TIME" in typ:
            return "%02d:%02d:%02d" % (random.randint(0, 23), random.randint(0, 59), random.randint(0, 59))
        if "BOOL" in typ or typ == "BIT":
            return 1 if random.random() > 0.5 else 0
        if any(k in typ for k in ("TEXT", "CHAR", "CLOB", "JSON", "UUID", "GUID")):
            return "测试" + "".join(random.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(random.randint(2, 12)))
        if any(k in typ for k in ("BINARY", "BLOB")):
            return ""
        return "test" + str(random.randint(1, 99999))

    values = [{c["name"]: gen_val(c) for c in usable} for _ in range(rows)]
    engine = get_engine(ci)
    meta = MetaData()
    tbl = Table(table, meta, autoload_with=engine, schema=schema or None)
    with engine.begin() as conn:
        conn.execute(tbl.insert(), values)
    return {"ok": True, "inserted": len(values), "columns": len(usable)}


