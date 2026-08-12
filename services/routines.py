# -*- coding: utf-8 -*-
"""dbmanager - ops 存储过程/函数/触发器: 列表/源码/保存重建/删除/执行"""
from sqlalchemy import text

from dbcore import get_engine
from services.core import _qi

def get_routines(ci, schema=None):
    """列出存储过程/函数/触发器, 返回 [{schema,name,type: Procedure|Function|Trigger}]"""
    t = (ci.get("db_type") or "mysql").lower()
    out = []
    try:
        with get_engine(ci).connect() as conn:
            if t == "mysql":
                sch = schema or ci.get("database") or ""
                rows = conn.execute(text(
                    "SELECT ROUTINE_SCHEMA, ROUTINE_NAME, ROUTINE_TYPE "
                    "FROM information_schema.ROUTINES WHERE ROUTINE_SCHEMA = :s").bindparams(s=sch)).mappings()
                for r in rows:
                    out.append({"schema": r["ROUTINE_SCHEMA"], "name": r["ROUTINE_NAME"],
                                "type": "Procedure" if r["ROUTINE_TYPE"] == "PROCEDURE" else "Function"})
                try:
                    trows = conn.execute(text("SHOW TRIGGERS")).mappings()
                    for r in trows:
                        out.append({"schema": sch, "name": r["Trigger"], "type": "Trigger"})
                except Exception:
                    pass
            elif t == "postgresql":
                rows = conn.execute(text(
                    "SELECT n.nspname AS \"schema\", p.proname AS name, "
                    "CASE p.prokind WHEN 'p' THEN 'Procedure' ELSE 'Function' END AS type "
                    "FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE n.nspname NOT IN ('pg_catalog','information_schema') "
                    "AND p.prokind IN ('p','f')")).mappings()
                for r in rows:
                    out.append({"schema": r["schema"], "name": r["name"], "type": r["type"]})
            elif t == "mssql":
                rows = conn.execute(text(
                    "SELECT SCHEMA_NAME(schema_id) AS [schema], name, type FROM sys.objects "
                    "WHERE type IN ('P','FN','IF','TF')")).mappings()
                for r in rows:
                    tp = {'P': 'Procedure', 'FN': 'Function', 'IF': 'Function', 'TF': 'Function'}.get(r["type"])
                    if tp:
                        out.append({"schema": r["schema"], "name": r["name"], "type": tp})
                try:
                    trows = conn.execute(text(
                        "SELECT SCHEMA_NAME(schema_id) AS [schema], name FROM sys.objects "
                        "WHERE type='TR'")).mappings()
                    for r in trows:
                        out.append({"schema": r["schema"], "name": r["name"], "type": "Trigger"})
                except Exception:
                    pass
            elif t == "oracle":
                rows = conn.execute(text(
                    "SELECT owner AS schema, object_name AS name, "
                    "CASE object_type WHEN 'PROCEDURE' THEN 'Procedure' ELSE 'Function' END AS type "
                    "FROM all_procedures WHERE object_type IN ('PROCEDURE','FUNCTION') "
                    "AND owner NOT IN ('SYS','SYSTEM')")).mappings()
                for r in rows:
                    out.append({"schema": r["schema"], "name": r["name"], "type": r["type"]})
                try:
                    trows = conn.execute(text(
                        "SELECT owner AS schema, trigger_name AS name, 'Trigger' AS type "
                        "FROM all_triggers WHERE owner NOT IN ('SYS','SYSTEM') "
                        "AND status='ENABLED'")).mappings()
                    for r in trows:
                        out.append({"schema": r["schema"], "name": r["name"], "type": "Trigger"})
                except Exception:
                    pass
    except Exception:
        pass
    return out


def get_routine_source(ci, schema, name, kind):
    """获取对象源码文本"""
    t = (ci.get("db_type") or "mysql").lower()
    with get_engine(ci).connect() as conn:
        if t == "mysql":
            if kind == "Trigger":
                r = conn.execute(text("SHOW CREATE TRIGGER `%s`" % str(name).replace("`", "``"))).mappings().first()
                if not r:
                    return ""
                return r.get("SQL Original Statement") or r.get("Create Trigger") or ""
            kw = "PROCEDURE" if kind == "Procedure" else "FUNCTION"
            r = conn.execute(text("SHOW CREATE %s `%s`" % (kw, str(name).replace("`", "``")))).mappings().first()
            if not r:
                return ""
            return r.get("Create %s" % kw.title()) or r.get("SQL Original Statement") or ""
        elif t == "postgresql":
            oid = conn.execute(text(
                "SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE p.proname = :n AND n.nspname = :s").bindparams(n=name, s=schema or "public")).scalar()
            if oid:
                return conn.execute(text("SELECT pg_get_functiondef(:oid)").bindparams(oid=oid)).scalar() or ""
        elif t == "mssql":
            oid = conn.execute(text("SELECT OBJECT_ID(:n)").bindparams(n="%s.%s" % (schema or "dbo", name))).scalar()
            if oid:
                return conn.execute(text("SELECT OBJECT_DEFINITION(:oid)").bindparams(oid=oid)).scalar() or ""
        elif t == "oracle":
            if kind == "Trigger":
                r = conn.execute(text(
                    "SELECT dbms_metadata.get_ddl('TRIGGER', :n, :s) AS ddl FROM dual"
                ).bindparams(n=name, s=schema or None)).scalar()
                return r or ""
            obj_type = "PROCEDURE" if kind == "Procedure" else "FUNCTION"
            r = conn.execute(text(
                "SELECT dbms_metadata.get_ddl(:t, :n, :s) AS ddl FROM dual"
            ).bindparams(t=obj_type, n=name, s=schema or None)).scalar()
            return r or ""
    return ""


def get_routine_params(ci, schema, name, kind):
    """解析对象参数列表, 返回 [{name,mode,type}] (MySQL/PG; MSSQL 基础支持)"""
    t = (ci.get("db_type") or "mysql").lower()
    params = []
    try:
        with get_engine(ci).connect() as conn:
            if t == "mysql":
                sch = schema or ci.get("database") or ""
                rows = conn.execute(text(
                    "SELECT PARAMETER_NAME, PARAMETER_MODE, DATA_TYPE, ORDINAL_POSITION "
                    "FROM information_schema.PARAMETERS "
                    "WHERE SPECIFIC_SCHEMA = :s AND SPECIFIC_NAME = :n "
                    "ORDER BY ORDINAL_POSITION").bindparams(s=sch, n=name)).mappings()
                for r in rows:
                    if r["PARAMETER_NAME"]:
                        params.append({"name": r["PARAMETER_NAME"], "mode": (r["PARAMETER_MODE"] or "IN"),
                                       "type": r["DATA_TYPE"] or ""})
            elif t == "postgresql":
                oid = conn.execute(text(
                    "SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace "
                    "WHERE p.proname = :n AND n.nspname = :s").bindparams(n=name, s=schema or "public")).scalar()
                if oid:
                    args = conn.execute(text("SELECT pg_get_function_arguments(:oid)").bindparams(oid=oid)).scalar() or ""
                    # 形如: arg1 integer, arg2 text 或 OUT x integer, INOUT y text
                    for part in args.split(","):
                        part = part.strip()
                        if not part:
                            continue
                        toks = part.split()
                        mode = "IN"
                        if toks and toks[0].upper() in ("IN", "OUT", "INOUT", "VARIADIC"):
                            mode = toks.pop(0).upper()
                        if toks and len(toks) >= 2 and toks[0].upper() == "OUT":
                            mode = "OUT"; toks = toks[1:]
                        if len(toks) >= 2:
                            params.append({"name": toks[0], "mode": mode, "type": " ".join(toks[1:])})
            elif t == "mssql":
                oid = conn.execute(text("SELECT OBJECT_ID(:n)").bindparams(n="%s.%s" % (schema or "dbo", name))).scalar()
                if oid:
                    rows = conn.execute(text(
                        "SELECT p.name, p.is_output, t.name AS dtype FROM sys.parameters p "
                        "JOIN sys.types t ON t.user_type_id = p.user_type_id "
                        "WHERE p.object_id = :oid ORDER BY p.parameter_id").bindparams(oid=oid)).mappings()
                    for r in rows:
                        params.append({"name": "@" + r["name"], "mode": "OUT" if r["is_output"] else "IN",
                                       "type": r["dtype"] or ""})
    except Exception:
        pass
    return params


def save_routine(ci, schema, name, kind, source):
    """保存(重建)对象: MySQL DROP+CREATE(multi), PG/MSSQL 直接执行源码"""
    t = (ci.get("db_type") or "mysql").lower()
    src = (source or "").strip()
    if not src:
        raise ValueError("源码不能为空")
    # 去掉 MySQL delimiter 包装(从 SHOW CREATE 拷贝时可能带上)
    if src.upper().startswith("DELIMITER"):
        lines = src.splitlines()
        body = [l for l in lines if not l.strip().upper().startswith("DELIMITER")]
        src = "\n".join(body).strip()
    if t == "mysql":
        eng = get_engine(ci)
        kw = {"Procedure": "PROCEDURE", "Function": "FUNCTION", "Trigger": "TRIGGER"}.get(kind, "PROCEDURE")
        with eng.connect() as conn:
            conn.execute(text("DROP %s IF EXISTS `%s`" % (kw, str(name).replace("`", "``"))))
            conn.commit()
        # CREATE 含 BEGIN...END 内部分号, 必须用驱动 multi 模式执行
        raw = eng.raw_connection()
        try:
            cur = raw.cursor()
            cur.execute(src, multi=True)
            for _ in cur:  # 消费多语句结果
                pass
            raw.commit()
        finally:
            raw.close()
    else:
        with get_engine(ci).connect() as conn:
            conn.execute(text(src))
            conn.commit()
    return {"ok": True}


def drop_routine(ci, schema, name, kind):
    """删除对象"""
    t = (ci.get("db_type") or "mysql").lower()
    if t == "mysql":
        kw = {"Procedure": "PROCEDURE", "Function": "FUNCTION", "Trigger": "TRIGGER"}.get(kind, "PROCEDURE")
        with get_engine(ci).connect() as conn:
            conn.execute(text("DROP %s IF EXISTS `%s`" % (kw, str(name).replace("`", "``"))))
            conn.commit()
    elif t == "postgresql":
        with get_engine(ci).connect() as conn:
            if kind == "Trigger":
                conn.execute(text("DROP TRIGGER IF EXISTS %s ON %s" % (
                    _qi("postgresql", name), _qi("postgresql", schema or "public"))))
            else:
                conn.execute(text("DROP %s IF EXISTS %s.%s" % (
                    "PROCEDURE" if kind == "Procedure" else "FUNCTION",
                    _qi("postgresql", schema or "public"), _qi("postgresql", name))))
            conn.commit()
    elif t == "mssql":
        with get_engine(ci).connect() as conn:
            conn.execute(text("DROP %s IF EXISTS %s.%s" % (
                "PROCEDURE" if kind == "Procedure" else "FUNCTION",
                _qi("mssql", schema or "dbo"), _qi("mssql", name))))
            conn.commit()
    return {"ok": True}


def execute_routine(ci, schema, name, kind, params=None):
    """执行对象: 过程 CALL / 函数 SELECT; params 为 {参数名: 值} 或位置数组; 返回结果集"""
    t = (ci.get("db_type") or "mysql").lower()
    params = params or {}
    engine = get_engine(ci)
    if t == "mysql":
        if kind == "Function":
            cols = ", ".join(":%s" % k for k in params.keys()) if params else ""
            sql = "SELECT `%s`(%s) AS result" % (str(name).replace("`", "``"), cols)
        else:
            cols = ", ".join(":%s" % k for k in params.keys()) if params else ""
            sql = "CALL `%s`(%s)" % (str(name).replace("`", "``"), cols)
    elif t == "postgresql":
        if kind == "Function":
            cols = ", ".join(":%s" % k for k in params.keys()) if params else ""
            sql = "SELECT %s.%s(%s)" % (_qi("postgresql", schema or "public"), _qi("postgresql", name), cols)
        else:
            cols = ", ".join(":%s" % k for k in params.keys()) if params else ""
            sql = "CALL %s.%s(%s)" % (_qi("postgresql", schema or "public"), _qi("postgresql", name), cols)
    elif t == "mssql":
        if kind == "Function":
            cols = ", ".join(":%s" % k for k in params.keys()) if params else ""
            sql = "SELECT %s.%s(%s)" % (_qi("mssql", schema or "dbo"), _qi("mssql", name), cols)
        else:
            sql = "EXEC %s.%s %s" % (_qi("mssql", schema or "dbo"), _qi("mssql", name),
                                     ", ".join(":%s = :%s" % (k, k) for k in params.keys()) if params else "")
    else:
        raise ValueError("该数据库类型不支持执行存储过程")
    with engine.connect() as conn:
        result = conn.execute(text(sql), params)
        if result.returns_rows:
            cols = list(result.keys())
            rows = [dict(r) for r in result.mappings().fetchmany(501)]
            truncated = len(rows) > 500
            return {"columns": [{"name": c} for c in cols], "rows": rows[:500],
                    "total": len(rows[:500]), "truncated": truncated, "affected": None}
        return {"columns": [], "rows": [], "total": 0, "affected": result.rowcount or 0}

