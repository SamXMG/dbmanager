# -*- coding: utf-8 -*-
"""dbmanager - ops 改表: 列/索引可视化 DDL(MySQL/MSSQL/PG方言) + NoSQL集合键操作"""
from sqlalchemy import text
from sqlalchemy.exc import ResourceClosedError

from db.dbcore import conn_hash, get_engine
from services.core import META_CACHE, _check_default, _check_type, _clear_count_cache, _qi


def alter_table(ci, schema, table, action, payload, tx_key=""):
    """DDL 向导: add/drop/modify column, add/drop index(按 MySQL/MSSQL/PG 方言)"""
    t = (ci.get("db_type") or "mysql").lower()
    if t == "mongodb":
        from db.dbcore import get_mongo
        coll_db = get_mongo(ci)[schema]
        if action in ("create_table", "create"):
            coll_db.create_collection(table)
            return {"ok": True}
        if action in ("drop_table", "drop"):
            coll_db[table].drop()
            return {"ok": True}
        raise ValueError("MongoDB 仅支持创建/删除集合")
    if t == "redis":
        from db.dbcore import get_redis
        r = get_redis(ci)
        if action == "create":
            p = payload or {}
            ktype = (p.get("type") or "string").lower()
            val = str(p.get("value", ""))
            if ktype == "string":
                r.set(table, val)
            elif ktype == "hash":
                r.hset(table, mapping={val: ""})
            elif ktype == "list":
                r.rpush(table, val)
            elif ktype == "set":
                r.sadd(table, val)
            elif ktype == "zset":
                r.zadd(table, {val: 0})
            else:
                raise ValueError("不支持的类型: " + ktype)
            if p.get("ttl"):
                r.expire(table, int(p["ttl"]))
            return {"ok": True}
        if action == "drop":
            return {"ok": True, "affected": r.delete(table)}
        if action == "set_ttl":
            ttl = (payload or {}).get("ttl")
            if ttl is None:
                return {"ok": True, "ttl": r.ttl(table)}
            if int(ttl) > 0:
                r.expire(table, int(ttl))
            else:
                r.persist(table)
            return {"ok": True, "ttl": int(ttl)}
        raise ValueError("Redis 仅支持 创建键/删除键/设置TTL")

    # ---- 新增操作(对齐 Navicat 右键): rename/truncate/clear/copy/maintain ----
    new = (payload.get("new_name") or "").strip()
    full = ((_qi(t, schema) + ".") if schema else "") + _qi(t, table)
    nfull = ((_qi(t, schema) + ".") if schema else "") + _qi(t, new)
    if action in ("rename_table", "truncate_table", "clear_table", "copy_table", "maintain"):
        with get_engine(ci).connect() as conn:
            if action == "rename_table":
                if not new or new == table:
                    raise ValueError("请输入不同的新表名")
                nfull = ((_qi(t, schema) + ".") if schema else "") + _qi(t, new)
                if t == "mysql":
                    conn.execute(text(f"RENAME TABLE {full} TO {nfull}"))
                elif t == "mssql":
                    # sp_rename 参数是字符串('schema.obj'), 转义单引号防注入
                    e = lambda s_: str(s_).replace("'", "''")
                    conn.execute(text(f"EXEC sp_rename '{e(schema)}.{e(table)}', '{e(schema)}.{e(new)}'"))
                else:  # postgresql / sqlite
                    conn.execute(text(f"ALTER TABLE {full} RENAME TO {new}"))
                _clear_count_cache(conn_hash(ci), schema, table)
                return {"ok": True, "old": table, "new": new}
            if action == "truncate_table":  # 重置自增(SQLite 无 TRUNCATE)
                if t == "sqlite":
                    conn.execute(text(f"DELETE FROM {full}"))
                    try:  # sqlite_sequence 仅当表有 AUTOINCREMENT 列时存在
                        conn.execute(text("DELETE FROM sqlite_sequence WHERE name=:n"), {"n": table})
                    except Exception:
                        pass
                else:
                    conn.execute(text(f"TRUNCATE TABLE {full}"))
                _clear_count_cache(conn_hash(ci), schema, table)
                return {"ok": True, "truncated": True}
            if action == "clear_table":  # 不重置自增
                conn.execute(text(f"DELETE FROM {full}"))
                _clear_count_cache(conn_hash(ci), schema, table)
                return {"ok": True, "cleared": True}
            if action == "copy_table":
                if not new or new == table:
                    raise ValueError("请输入不同的新表名")
                nfull = ((_qi(t, schema) + ".") if schema else "") + _qi(t, new)
                with_data = bool(payload.get("with_data", True))
                if t == "mysql":
                    conn.execute(text(f"CREATE TABLE {nfull} LIKE {full}"))
                    if with_data:
                        conn.execute(text(f"INSERT INTO {nfull} SELECT * FROM {full}"))
                elif t == "mssql":
                    if with_data:
                        conn.execute(text(f"SELECT * INTO {nfull} FROM {full}"))
                    else:
                        conn.execute(text(f"SELECT * INTO {nfull} FROM {full} WHERE 1=0"))
                elif t == "sqlite":
                    if with_data:
                        conn.execute(text(f"CREATE TABLE {nfull} AS SELECT * FROM {full}"))
                    else:
                        conn.execute(text(f"CREATE TABLE {nfull} AS SELECT * FROM {full} WHERE 0"))
                else:  # postgresql
                    conn.execute(text(f"CREATE TABLE {nfull} (LIKE {full} INCLUDING ALL)"))
                    if with_data:
                        conn.execute(text(f"INSERT INTO {nfull} SELECT * FROM {full}"))
                _clear_count_cache(conn_hash(ci), schema, new)
                return {"ok": True, "new_table": new, "with_data": with_data}
            if action == "maintain":
                op = (payload.get("op") or "check").lower()
                ddl = {
                    "mysql": {
                        "check": f"CHECK TABLE {full}", "optimize": f"OPTIMIZE TABLE {full}",
                        "repair": f"REPAIR TABLE {full}", "analyze": f"ANALYZE TABLE {full}",
                    },
                    "postgresql": {"check": f"VACUUM (VERBOSE) {full}", "optimize": f"VACUUM ANALYZE {full}",
                                   "analyze": f"ANALYZE {full}", "repair": f"VACUUM FULL {full}"},
                    "sqlite": {"check": f"PRAGMA integrity_check({full})", "optimize": "VACUUM",
                               "analyze": f"ANALYZE {full}", "repair": "VACUUM"},
                    "mssql": {"check": f"DBCC CHECKTABLE('{str(schema).replace(chr(39), chr(39)*2)}.{str(table).replace(chr(39), chr(39)*2)}')",
                              "optimize": f"ALTER INDEX ALL ON {full} REBUILD",
                              "analyze": f"UPDATE STATISTICS {full}", "repair": "DBCC CHECKDB"},
                }[t][op]
                try:  # VACUUM/CHECK TABLE 等无返回行的 DDL
                    rows = conn.execute(text(ddl)).mappings().fetchall()
                except ResourceClosedError:
                    rows = []
                return {"ok": True, "op": op, "rows": [dict(r) for r in rows]}

    if t == "sqlite":
        raise ValueError("SQLite 暂不支持可视化 DDL 编辑(可改用 SQL 控制台执行 ALTER TABLE)")
    full = ((_qi(t, schema) + ".") if schema else "") + _qi(t, table)
    stmts = []
    if action == "add_column":
        name = (payload.get("name") or "").strip()
        typ = _check_type(payload.get("type", ""))
        if not name or not typ:
            raise ValueError("请填写列名与类型")
        nullable = bool(payload.get("nullable", True))
        default = payload.get("default")
        default = _check_default(default) if default not in (None, "") else ""
        if t == "mysql":
            ddl = f"ALTER TABLE {full} ADD COLUMN {_qi(t,name)} {typ} {'NULL' if nullable else 'NOT NULL'}"
            if default: ddl += f" DEFAULT {default}"
            stmts.append(ddl)
        elif t == "mssql":
            ddl = f"ALTER TABLE {full} ADD {_qi(t,name)} {typ} {'NULL' if nullable else 'NOT NULL'}"
            if default: ddl += f" CONSTRAINT DF_{name[:20]} DEFAULT {default}"
            stmts.append(ddl)
        else:
            ddl = f"ALTER TABLE {full} ADD COLUMN {_qi(t,name)} {typ}"
            if default: ddl += f" DEFAULT {default}"
            if not nullable: ddl += " NOT NULL"
            stmts.append(ddl)
    elif action == "drop_column":
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("缺少列名")
        stmts.append(f"ALTER TABLE {full} DROP COLUMN {_qi(t,name)}")
    elif action == "modify_column":
        name = (payload.get("name") or "").strip()
        typ = _check_type(payload.get("type", ""))
        nullable = bool(payload.get("nullable", True))
        if not name or not typ:
            raise ValueError("请填写列名与类型")
        if t == "mysql":
            stmts.append(f"ALTER TABLE {full} MODIFY COLUMN {_qi(t,name)} {typ} {'NULL' if nullable else 'NOT NULL'}")
        elif t == "mssql":
            stmts.append(f"ALTER TABLE {full} ALTER COLUMN {_qi(t,name)} {typ} {'NULL' if nullable else 'NOT NULL'}")
        else:
            stmts.append(f"ALTER TABLE {full} ALTER COLUMN {_qi(t,name)} TYPE {typ}")
            stmts.append(f"ALTER TABLE {full} ALTER COLUMN {_qi(t,name)} {'DROP' if nullable else 'SET'} NOT NULL")
    elif action == "add_index":
        name = (payload.get("name") or "").strip() or ("idx_" + "_".join(payload.get("columns") or []))
        cols = payload.get("columns") or []
        if not cols:
            raise ValueError("索引至少需要一列")
        cols_sql = ", ".join(_qi(t, c) for c in cols)
        unique = "UNIQUE " if payload.get("unique") else ""
        if t == "mysql":
            stmts.append(f"ALTER TABLE {full} ADD {unique}INDEX {_qi(t,name)} ({cols_sql})")
        else:
            stmts.append(f"CREATE {unique}INDEX {_qi(t,name)} ON {full} ({cols_sql})")
    elif action == "drop_index":
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValueError("缺少索引名")
        if t == "mysql":
            stmts.append(f"ALTER TABLE {full} DROP INDEX {_qi(t,name)}")
        elif t == "mssql":
            stmts.append(f"DROP INDEX {_qi(t,name)} ON {full}")
        else:
            stmts.append(f"DROP INDEX {_qi(t,name)}")
    else:
        raise ValueError(f"不支持的操作: {action}")
    engine = get_engine(ci)
    with engine.connect() as conn:
        for s in stmts:
            conn.execute(text(s))
        conn.commit()
    META_CACHE.clear()  # DDL 变更后清元数据缓存
    return {"ok": True, "ddl": stmts}

