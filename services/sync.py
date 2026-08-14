# -*- coding: utf-8 -*-
"""dbmanager - ops 结构同步: 跨库/跨连接数据同步 + 表结构对比DDL"""
from sqlalchemy import delete, insert, select, text

from dbcore import conn_hash, get_engine
from services.core import _clear_count_cache, _col_ddl, _qi
from services.metadata import get_columns, get_table_obj


def sync_table(src, dst, schema, table, mode="append"):
    """库对库表同步: 按同名列匹配, 分批(500行)INSERT; mode=replace 先清空目标表"""
    cols_src = get_columns(src, schema, table)
    col_names = [c["name"] for c in cols_src]
    dst_cols = {c["name"] for c in get_columns(dst, schema, table)}
    common = [c for c in col_names if c in dst_cols]
    if not common:
        raise ValueError("源/目标表没有共同列")
    engine_src, engine_dst = get_engine(src), get_engine(dst)
    try:
        tsrc = get_table_obj(src, schema, table)
    except Exception:
        raise ValueError(f"源表 {schema}.{table} 不存在(检查当前连接的数据库)")
    try:
        tdst = get_table_obj(dst, schema, table)
    except Exception:
        raise ValueError(f"目标表 {schema}.{table} 不存在(检查目标连接的数据库是否正确)")
    sel = select(*[tsrc.c[c] for c in common])
    with engine_dst.connect() as dconn:
        if mode == "replace":
            dconn.execute(delete(tdst))
            dconn.commit()
        with engine_src.connect() as sconn:
            batch, total = [], 0
            for r in sconn.execute(sel).mappings():
                batch.append(dict(r))
                if len(batch) >= 500:
                    dconn.execute(insert(tdst), batch)
                    total += len(batch); batch = []
            if batch:
                dconn.execute(insert(tdst), batch)
                total += len(batch)
        dconn.commit()
    _clear_count_cache(conn_hash(dst), schema, table)
    return {"ok": True, "synced": total, "mode": mode}

def diff_schema(src_ci, dst_ci, schema=None, table=None):
    """对比两连接表结构, 返回 [{type,target,detail,sql}] —— 列出"源有而目标缺/不同"的项"""
    from sqlalchemy import inspect as sa_inspect
    dst_type = (dst_ci.get("db_type") or "mysql").lower()
    with get_engine(src_ci).connect() as sc, get_engine(dst_ci).connect() as dc:
        s_insp, d_insp = sa_inspect(sc), sa_inspect(dc)
        s_tables = [table] if table else s_insp.get_table_names(schema=schema)
        d_tables = set(d_insp.get_table_names(schema=schema))
        diffs = []
        for t in sorted(s_tables):
            if t not in d_tables:
                diffs.append({"type": "缺表", "target": t, "detail": "目标库无此表",
                              "sql": f"/* 需手动生成 {t} 的 CREATE TABLE(对比源表结构) */"})
                continue
            s_cols = {c["name"]: c for c in s_insp.get_columns(t, schema=schema)}
            d_cols = {c["name"]: c for c in d_insp.get_columns(t, schema=schema)}
            for cn in sorted(s_cols.keys() - d_cols.keys()):
                c = s_cols[cn]
                sql = f"ALTER TABLE {_qi(dst_type, t)} ADD COLUMN {_qi(dst_type, cn)} {_col_ddl(c)}"
                diffs.append({"type": "缺列", "target": f"{t}.{cn}", "detail": str(c["type"]), "sql": sql})
            for cn in sorted(s_cols.keys() & d_cols.keys()):
                sc_, dc_ = s_cols[cn], d_cols[cn]
                if str(sc_["type"]) != str(dc_["type"]):
                    if dst_type == "mysql":
                        sql = f"ALTER TABLE {_qi(dst_type, t)} MODIFY COLUMN {_qi(dst_type, cn)} {_col_ddl(sc_)}"
                    elif dst_type == "sqlite":
                        sql = f"/* SQLite 不支持 ALTER COLUMN, 需重建表: {t}.{cn} {sc_['type']} -> {dc_['type']} */"
                    else:
                        sql = f"ALTER TABLE {_qi(dst_type, t)} ALTER COLUMN {_qi(dst_type, cn)} TYPE {_col_ddl(sc_)}"
                    diffs.append({"type": "类型不同", "target": f"{t}.{cn}",
                                  "detail": f"{sc_['type']} -> {dc_['type']}", "sql": sql})
                if bool(sc_["nullable"]) != bool(dc_["nullable"]):
                    if dst_type == "mysql":
                        sql = f"ALTER TABLE {_qi(dst_type, t)} MODIFY COLUMN {_qi(dst_type, cn)} {_col_ddl(sc_)}"
                    elif dst_type == "sqlite":
                        sql = f"/* SQLite 不支持 ALTER COLUMN, 需重建表: {t}.{cn} 可空 {sc_['nullable']} -> {dc_['nullable']} */"
                    else:
                        act = "SET NOT NULL" if not sc_["nullable"] else "DROP NOT NULL"
                        sql = f"ALTER TABLE {_qi(dst_type, t)} ALTER COLUMN {_qi(dst_type, cn)} {act}"
                    diffs.append({"type": "可空不同", "target": f"{t}.{cn}",
                                  "detail": f"src可空={sc_['nullable']} dst可空={dc_['nullable']}", "sql": sql})
            s_pk = s_insp.get_pk_constraint(t, schema=schema).get("constrained_columns") or []
            d_pk = d_insp.get_pk_constraint(t, schema=schema).get("constrained_columns") or []
            if s_pk != d_pk:
                if dst_type == "mysql" and d_pk:
                    sql = ("ALTER TABLE %s DROP PRIMARY KEY, ADD PRIMARY KEY (%s)" % (
                        _qi(dst_type, t), ", ".join(_qi(dst_type, c) for c in s_pk)))
                else:
                    sql = f"/* 主键不同: src={s_pk} dst={d_pk}, 需手动调整 */"
                diffs.append({"type": "主键不同", "target": t, "detail": f"{s_pk} vs {d_pk}", "sql": sql})
        return diffs


def execute_schema_sync(dst_ci, sqls):
    """在目标连接逐条执行 DDL(注释跳过), 返回 {executed, failed}; 每条成功后提交(SQLite DML 需显式 commit)"""
    engine = get_engine(dst_ci)
    executed, failed = [], []
    with engine.connect() as conn:
        for sql in sqls:
            s = (sql or "").strip()
            if not s or s.startswith("/*"):
                continue
            try:
                conn.execute(text(s))
                conn.commit()   # DDL/DML 都显式提交, 避免连接关闭回滚
                executed.append(s)
            except Exception as e:
                failed.append({"sql": s, "error": str(e)})
    return {"executed": executed, "failed": failed}


# ------------------------------
# 备份/还原: 统一生成可执行 SQL 脚本(CREATE TABLE + INSERT 分批), 所有库通用
