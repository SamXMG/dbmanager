# -*- coding: utf-8 -*-
"""dbmanager - ops 元数据: 库/表/列/索引/主键/关系/用户权限(60s缓存)"""
from sqlalchemy import MetaData, Table, inspect, text

from db.dbcore import conn_hash, get_engine
from services.core import _meta_get, _meta_key, _meta_set
from services.nosql import _redis_type_label


def get_databases(ci: dict):
    """列出可访问的数据库(用于"加载库列表")；SQLite 不适用返回空"""
    t = ci["db_type"]
    if t == "sqlite":
        return []
    if t == "mongodb":
        from db.dbcore import get_mongo
        skip = {"admin", "local", "config"}
        return [d for d in get_mongo(ci).list_database_names() if d not in skip]
    if t == "redis":
        # Redis 库编号 0-15, 仅返回非空库(降低扫描成本)
        from db.dbcore import get_redis
        r = get_redis(ci)
        out = []
        for db in range(16):
            try:
                if r.select(db) and r.dbsize():
                    out.append("db%d" % db)
            except Exception:
                continue
        try:
            r.select(0)
        except Exception:
            pass
        return out or ["db0"]
    key = _meta_key("dbs", conn_hash(ci))
    hit = _meta_get(key)
    if hit is not None:
        return hit
    engine = get_engine(ci)
    with engine.connect() as conn:
        if t == "mssql":
            rows = conn.execute(text("SELECT name FROM sys.databases WHERE database_id>4 ORDER BY name")).fetchall()
        elif t == "mysql":
            rows = conn.execute(text("SELECT schema_name FROM information_schema.schemata "
                                     "WHERE schema_name NOT IN ('information_schema','mysql','performance_schema','sys') "
                                     "ORDER BY 1")).fetchall()
        elif t == "postgresql":
            rows = conn.execute(text("SELECT datname FROM pg_database WHERE datistemplate=false ORDER BY 1")).fetchall()
        elif t == "oracle":
            # Oracle 无独立 database 概念: 列出可访问用户 schema(排除系统维护账号)
            rows = conn.execute(text(
                "SELECT username FROM all_users WHERE oracle_maintained='N' "
                "AND username NOT IN ('SYSTEM','SYS','XDB','OUTLN','DBSNMP','ORACLE_OCM','WMSYS') "
                "ORDER BY 1")).fetchall()
        else:
            return []
    result = [r[0] for r in rows]
    _meta_set(key, result)
    return result

def get_tables(ci: dict):
    key = _meta_key("tables", conn_hash(ci))
    hit = _meta_get(key)
    if hit is not None:
        return hit
    if ci["db_type"] == "mongodb":
        from db.dbcore import get_mongo
        client = get_mongo(ci)
        skip = {"admin", "local", "config"}
        out = []
        for db in client.list_database_names():
            if db in skip:
                continue
            for coll in client[db].list_collection_names():
                out.append({"schema": db, "name": coll, "type": "Collection"})
        result = sorted(out, key=lambda x: (x["schema"], x["name"]))
        _meta_set(key, result)
        return result
    if ci["db_type"] == "redis":
        # Redis: 键即"表"(scan 游标迭代, 不阻塞); 上限 5000 键防超大库卡顿
        from db.dbcore import get_redis
        r = get_redis(ci)
        out = []
        cur = 0
        while len(out) < 5000:
            cur, keys = r.scan(cur, count=200)
            for k in keys:
                out.append({"schema": "db0", "name": k, "type": _redis_type_label(r.type(k))})
            if cur == 0:
                break
        result = sorted(out[:5000], key=lambda x: x["name"].lower())
        _meta_set(key, result)
        return result
    engine = get_engine(ci)
    insp = inspect(engine)
    t = ci["db_type"]
    out = []
    if t == "sqlite":
        for nm in insp.get_table_names(schema="main"):
            out.append({"schema": "", "name": nm, "type": "Table"})
        for nm in insp.get_view_names(schema="main"):
            out.append({"schema": "", "name": nm, "type": "View"})
    elif t == "mysql":
        # 连接内多库: 总是遍历所有非系统 schema(不再受连接时 database 字段限制)
        schemas = [s for s in insp.get_schema_names()
                   if s not in ("information_schema", "mysql", "performance_schema", "sys")]
        for sch in schemas:
            for nm in insp.get_table_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "Table"})
            for nm in insp.get_view_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "View"})
    elif t == "postgresql":
        # 连接内多库: 遍历所有非系统 schema(public 之外的自建 schema 也显示)
        schemas = [s for s in insp.get_schema_names()
                   if s not in ("pg_catalog", "information_schema", "pg_toast",
                                "pg_toast_temp_1", "pg_temp_1")]
        for sch in schemas:
            for nm in insp.get_table_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "Table"})
            for nm in insp.get_view_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "View"})
    elif t == "mssql":
        skip = {"sys", "INFORMATION_SCHEMA", "guest", "db_owner", "db_accessadmin",
                "db_securityadmin", "db_ddladmin", "db_backupoperator", "db_datareader",
                "db_datawriter", "db_denydatareader", "db_denydatawriter"}
        for sch in [s for s in insp.get_schema_names() if s not in skip]:
            for nm in insp.get_table_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "Table"})
            for nm in insp.get_view_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "View"})
    elif t == "oracle":
        # Oracle schema = 用户; 排除系统内置账号, 用户表在各用户 schema 下
        skip = {s.upper() for s in (
            "SYS", "SYSTEM", "XDB", "OUTLN", "DBSNMP", "ORACLE_OCM", "WMSYS",
            "APPQOSSYS", "GSMADMIN_INTERNAL", "AUDSYS", "CTXSYS", "MDSYS",
            "LBACSYS", "DVSYS", "ORDDATA", "ORDPLUGINS", "SI_INFORMTN_SCHEMA")}
        for sch in [s for s in insp.get_schema_names() if s.upper() not in skip]:
            for nm in insp.get_table_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "Table"})
            for nm in insp.get_view_names(schema=sch):
                out.append({"schema": sch, "name": nm, "type": "View"})
    result = sorted(out, key=lambda x: (x["schema"], x["name"]))
    _meta_set(key, result)
    return result


# ------------------------------
# 存储过程/函数/触发器: 列表/源码/保存(重建)/删除/执行
def get_columns(ci: dict, schema: str, table: str):
    key = _meta_key("cols", conn_hash(ci), schema, table)
    hit = _meta_get(key)
    if hit is not None:
        return hit
    engine = get_engine(ci)
    raw = inspect(engine).get_columns(table, schema=schema or None)
    cols = []
    for c in raw:
        typ = c["type"]
        cols.append({"name": c["name"],
                     "type": str(typ),
                     "nullable": bool(c["nullable"]),
                     "identity": bool(c.get("autoincrement")) or bool(c.get("identity")),
                     "computed": bool(c.get("computed")),
                     "max_length": getattr(typ, "length", None),
                     "precision": getattr(typ, "precision", None),
                     "scale": getattr(typ, "scale", None),
                     "default": str(c["default"]) if c.get("default") is not None else None,
                     })
    _meta_set(key, cols)
    return cols

def get_pk(ci: dict, schema: str, table: str):
    if (ci.get("db_type") or "") == "mongodb":
        return ["_id"]  # 文档定位统一用 _id
    key = _meta_key("pk", conn_hash(ci), schema, table)
    hit = _meta_get(key)
    if hit is not None:
        return hit
    pk = inspect(get_engine(ci)).get_pk_constraint(table, schema=schema or None)
    result = (pk.get("constrained_columns") or []) if pk else []
    _meta_set(key, result)
    return result

def get_indexes(ci: dict, schema: str, table: str):
    if (ci.get("db_type") or "") == "mongodb":
        from db.dbcore import get_mongo
        coll = get_mongo(ci)[schema][table]
        out = []
        for i in coll.list_indexes():
            out.append({"name": i.get("name") or "",
                        "type": "INDEX",
                        "is_pk": False,
                        "columns": list((i.get("key") or {}).keys()),
                        "unique": bool(i.get("unique")),
                        "definition": str(i.get("key"))})
        return out
    key = _meta_key("idx", conn_hash(ci), schema, table)
    hit = _meta_get(key)
    if hit is not None:
        return hit
    idxs = inspect(get_engine(ci)).get_indexes(table, schema=schema or None)
    result = [{"name": i["name"],
               "type": "INDEX",
               "is_pk": bool(i.get("primary_key", False)),
               "is_unique": bool(i.get("unique", False)),
               "columns": ", ".join(i.get("column_names", [])),
               } for i in idxs]
    _meta_set(key, result)
    return result

def get_table_obj(ci: dict, schema: str, table: str) -> Table:
    """反射得到真实表对象(列引用按方言自动加引号)"""
    engine = get_engine(ci)
    meta = MetaData()
    return Table(table, meta, schema=schema or None, autoload_with=engine)

def get_relations(ci, schema, table):
    """当前表的外键关系(出方向)与反向引用(入方向, 全库扫描)"""
    if (ci.get("db_type") or "") in ("mongodb", "redis"):
        return []  # 无外键概念
    engine = get_engine(ci)
    insp = inspect(engine)
    out = []
    for fk in insp.get_foreign_keys(table, schema=schema or None):
        out.append({
            "name": fk.get("name") or "",
            "direction": "out",
            "columns": fk.get("constrained_columns") or [],
            "referred_schema": fk.get("referred_schema") or schema or "",
            "referred_table": fk.get("referred_table") or "",
            "referred_columns": fk.get("referred_columns") or [],
        })
    # 入方向: 全库扫描成本高, 限当前 schema 内
    try:
        schemas = [schema or ""] if schema else [s for s in insp.get_schema_names()]
        for sch in schemas[:5]:  # 限制扫描范围, 防大库卡顿
            for tname in insp.get_table_names(schema=sch):
                if tname == table:
                    continue
                try:
                    for fk in insp.get_foreign_keys(tname, schema=sch):
                        if (fk.get("referred_table") == table
                                and (fk.get("referred_schema") or sch) == (schema or sch)):
                            out.append({
                                "name": fk.get("name") or "",
                                "direction": "in",
                                "columns": fk.get("constrained_columns") or [],
                                "referred_schema": sch,
                                "referred_table": tname,
                                "referred_columns": fk.get("referred_columns") or [],
                            })
                except Exception:
                    continue
    except Exception:
        pass
    return out


def get_er_data(ci, schema, table):
    """ER 图数据: 中心表 + 直接外键关联表的结构与关系(邻接图, 避免全库大图)"""
    rels = get_relations(ci, schema, table)
    tables = {}
    def ensure(sch, tname):
        if not tname:
            return
        key = (sch or "") + "." + tname
        if key not in tables:
            try:
                cols = get_columns(ci, sch, tname)
                pk = get_pk(ci, sch, tname)
            except Exception:
                cols, pk = [], []
            tables[key] = {"schema": sch or "", "name": tname, "columns": cols, "pk": pk}
    ensure(schema, table)
    relations = []
    for r in rels:
        if r["direction"] == "out":
            ensure(r["referred_schema"], r["referred_table"])
            relations.append({"from_schema": schema or "", "from_table": table,
                              "from_columns": r.get("columns") or [],
                              "to_schema": r.get("referred_schema") or "",
                              "to_table": r.get("referred_table") or "",
                              "to_columns": r.get("referred_columns") or [],
                              "name": r.get("name") or ""})
        else:
            # in 方向: referred_table 是引用方(含外键指向中心表)
            ensure(r.get("schema") or schema, r.get("referred_table"))
            relations.append({"from_schema": r.get("schema") or "",
                              "from_table": r.get("referred_table") or "",
                              "from_columns": r.get("referred_columns") or [],
                              "to_schema": schema or "",
                              "to_table": table,
                              "to_columns": r.get("columns") or [],
                              "name": r.get("name") or ""})
    return {"tables": list(tables.values()), "relations": relations}


def get_users_privs(ci: dict):
    """用户与权限(只读): 登录/用户/角色/权限列表, 按方言查询; SQLite 不支持返回空"""
    t = ci.get("db_type", "").lower()
    if t == "sqlite":
        return {"supported": False, "logins": [], "users": [], "roles": [], "permissions": []}
    engine = get_engine(ci)
    out = {"supported": True, "logins": [], "users": [], "roles": [], "permissions": []}
    try:
        with engine.connect() as conn:
            if t == "mssql":
                # 服务器级登录
                try:
                    rows = conn.execute(text(
                        "SELECT name, is_disabled, type_desc, create_date "
                        "FROM sys.server_principals "
                        "WHERE type IN ('S','U','G') AND name NOT LIKE '##%' "
                        "ORDER BY name")).fetchall()
                    out["logins"] = [{"name": r[0], "disabled": bool(r[1]),
                                      "type": r[2], "created": str(r[3])[:10]} for r in rows]
                except Exception:
                    pass
                # 当前库的用户
                try:
                    rows = conn.execute(text(
                        "SELECT dp.name, dp.type_desc, dp.default_schema_name, "
                        "sp.name AS login_name "
                        "FROM sys.database_principals dp "
                        "LEFT JOIN sys.server_principals sp ON dp.sid = sp.sid "
                        "WHERE dp.type IN ('S','U','G') AND dp.name NOT LIKE '##%' "
                        "ORDER BY dp.name")).fetchall()
                    out["users"] = [{"name": r[0], "type": r[1],
                                     "default_schema": r[2] or "", "login": r[3] or ""}
                                    for r in rows]
                except Exception:
                    pass
                # 数据库角色
                try:
                    rows = conn.execute(text(
                        "SELECT rp.name AS role, mp.name AS member "
                        "FROM sys.database_role_members rm "
                        "JOIN sys.database_principals rp ON rm.role_principal_id = rp.principal_id "
                        "JOIN sys.database_principals mp ON rm.member_principal_id = mp.principal_id "
                        "ORDER BY rp.name, mp.name")).fetchall()
                    out["roles"] = [{"role": r[0], "member": r[1]} for r in rows]
                except Exception:
                    pass
                # 库级权限(非系统对象的显式权限)
                try:
                    rows = conn.execute(text(
                        "SELECT p.class_desc, p.permission_name, p.state_desc, "
                        "USER_NAME(p.grantee_principal_id) AS grantee, "
                        "COALESCE(OBJECT_NAME(p.major_id), p.major_id) AS obj "
                        "FROM sys.database_permissions p "
                        "WHERE p.class <> 0 "
                        "ORDER BY grantee, p.permission_name")).fetchall()
                    out["permissions"] = [{"class": r[0], "permission": r[1], "state": r[2],
                                           "grantee": r[3], "object": str(r[4] or "")}
                                          for r in rows[:500]]
                except Exception:
                    pass
            elif t == "mysql":
                # 用户列表 (mysql.user 可读时)
                try:
                    rows = conn.execute(text(
                        "SELECT User, Host, authentication_string <> '' AS has_pwd "
                        "FROM mysql.user ORDER BY User, Host")).fetchall()
                    out["logins"] = [{"name": r[0], "host": r[1], "has_pwd": bool(r[2])}
                                     for r in rows]
                except Exception:
                    pass
                # 权限: 当前用户可见的 grants
                try:
                    rows = conn.execute(text("SHOW GRANTS")).fetchall()
                    out["permissions"] = [{"grant": str(r[0])} for r in rows]
                except Exception:
                    pass
            elif t == "postgresql":
                try:
                    rows = conn.execute(text(
                        "SELECT rolname, rolsuper, rolcreatedb, rolcanlogin, "
                        "rolreplication, rolvaliduntil IS NULL AS never_expire "
                        "FROM pg_roles ORDER BY rolname")).fetchall()
                    out["logins"] = [{"name": r[0], "super": bool(r[1]), "createdb": bool(r[2]),
                                      "can_login": bool(r[3]), "replication": bool(r[4]),
                                      "expires": "never" if r[5] else "yes"}
                                     for r in rows]
                except Exception:
                    pass
                # 角色成员
                try:
                    rows = conn.execute(text(
                        "SELECT r.rolname AS role, m.rolname AS member "
                        "FROM pg_auth_members am "
                        "JOIN pg_roles r ON am.roleid = r.oid "
                        "JOIN pg_roles m ON am.member = m.oid "
                        "ORDER BY r.rolname, m.rolname")).fetchall()
                    out["roles"] = [{"role": r[0], "member": r[1]} for r in rows]
                except Exception:
                    pass
                # 库级权限
                try:
                    rows = conn.execute(text(
                        "SELECT grantee, privilege_type, table_schema, table_name "
                        "FROM information_schema.role_table_grants "
                        "ORDER BY grantee, table_name LIMIT 500")).fetchall()
                    out["permissions"] = [{"grantee": r[0], "permission": r[1],
                                           "schema": r[2], "object": r[3]} for r in rows]
                except Exception:
                    pass
    except Exception:
        pass  # 权限不足时返回空列表, 前端显示"无权限查看"
    return out

