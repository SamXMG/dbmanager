# -*- coding: utf-8 -*-
"""dbmanager - ops 备份还原: 整库 SQL 脚本生成与逐条执行"""
import datetime

from sqlalchemy import select, text

from dbcore import get_engine
from services.core import _qi, split_sql_statements
from services.metadata import get_columns, get_pk, get_table_obj, get_tables


def backup_database(ci, schema=None):
    """生成整库备份 SQL, 返回 (sql_text, filename)"""
    db_type = (ci.get("db_type") or "mysql").lower()
    if db_type == "mongodb":
        raise ValueError("MongoDB 备份请使用官方 mongodump 工具")
    if db_type == "redis":
        raise ValueError("Redis 备份请使用官方 redis-cli BGSAVE / SAVE")
    cur_db = schema or ci.get("database") or ""
    engine = get_engine(ci)
    q = lambda n: _qi(db_type, n)
    lines = ["-- dbmanager 备份", "-- 时间: %s" % datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
             "-- 类型: %s / 库: %s" % (db_type, cur_db), ""]
    tabs = get_tables(ci)
    with engine.connect() as conn:
        for t in tabs:
            if t["type"] != "Table":
                continue
            # 只备份当前库(schema 匹配): mysql 按库名, pg 按 public, sqlite 空 schema
            t_schema = t.get("schema") or ""
            if db_type == "mysql" and cur_db and t_schema != cur_db:
                continue
            if db_type == "postgresql" and t_schema not in ("public", cur_db):
                continue
            cols = get_columns(ci, t_schema, t["name"])
            col_names = [c["name"] for c in cols]
            pk = get_pk(ci, t_schema, t["name"])
            try:
                dd = ", ".join("%s %s%s" % (q(c["name"]), c["type"],
                                            "" if c.get("nullable", True) else " NOT NULL") for c in cols)
                if pk:
                    dd += ", PRIMARY KEY (%s)" % ", ".join(q(c) for c in pk)
                lines.append("CREATE TABLE IF NOT EXISTS %s (%s);" % (q(t["name"]), dd))
            except Exception as e:
                lines.append("-- 跳过 %s 表结构(生成失败: %s)" % (t["name"], e))
                continue
            # 数据分批 INSERT
            try:
                stmt = select(get_table_obj(ci, t_schema, t["name"]))
                col_list = ", ".join(q(c) for c in col_names)
                batch = []
                for r in conn.execute(stmt).mappings():
                    vals = []
                    for cn in col_names:
                        v = r[cn]
                        if v is None:
                            vals.append("NULL")
                        elif isinstance(v, bool):
                            vals.append("1" if v else "0")
                        elif isinstance(v, (int, float)):
                            vals.append(str(v))
                        elif isinstance(v, (bytes, bytearray)):
                            # P2-3: 二进制用 X'hex' 字面量(SQLite/MySQL 语义正确, 替代 str(v) 的 b'...' 非法字面量)
                            vals.append("X'" + bytes(v).hex() + "'")
                        elif isinstance(v, (datetime.datetime, datetime.date, datetime.time)):
                            vals.append("'" + v.isoformat() + "'")
                        else:
                            vals.append("'" + str(v).replace("'", "''") + "'")
                    batch.append("(%s)" % ", ".join(vals))
                    if len(batch) >= 500:
                        lines.append("INSERT INTO %s (%s) VALUES %s;" % (q(t["name"]), col_list, ", ".join(batch)))
                        batch = []
                if batch:
                    lines.append("INSERT INTO %s (%s) VALUES %s;" % (q(t["name"]), col_list, ", ".join(batch)))
            except Exception as e:
                lines.append("-- %s 数据备份跳过: %s" % (t["name"], e))
    return "\n".join(lines), "backup_%s_%s.sql" % (db_type, datetime.datetime.now().strftime("%Y%m%d_%H%M%S"))


def restore_sql(ci, sql_text):
    """执行备份 SQL 脚本(按语句拆分逐条执行), 返回 {executed, failed}; 每条成功后提交"""
    engine = get_engine(ci)
    stmts = split_sql_statements(sql_text)
    executed, failed = [], []
    with engine.connect() as conn:
        for s in stmts:
            t = s.strip()
            # 跳过纯注释/空白语句(仅由 -, 空格, 换行组成); 带注释头的真实 SQL(如 -- 备份头 + CREATE)照常执行
            if not t or all(c in "- \t\n\r" for c in t):
                continue
            try:
                conn.execute(text(s))
                conn.commit()   # SQLite DML 需显式提交
                executed.append(s[:80])
            except Exception as e:
                failed.append({"sql": s[:200], "error": str(e)})
    return {"executed": executed, "failed": failed}


