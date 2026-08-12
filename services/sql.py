# -*- coding: utf-8 -*-
"""dbmanager - ops SQL 控制台: 多语句拆分执行/只读校验/写模式事务/执行计划"""
import re

from sqlalchemy import text

from dbcore import get_engine
from services.core import SQL_BLOCKED, SQL_READ_ONLY, split_sql_statements

def run_sql(ci, sql, limit=500, write=False):
    """查询控制台: 支持多条分号分隔语句, 每条结果独立返回(前端各占一个 tab)。
    write=False(默认) 仅允许只读语句(SELECT/SHOW/EXPLAIN/DESC);
    write=True  允许任意语句(写模式), 整批语句事务包裹, 任一条失败整体回滚。
    注意: MySQL/MSSQL 的 DDL 会隐式提交, 无法回滚; DML 在事务内可回滚。"""
    if (ci.get("db_type") or "").lower() in ("mongodb", "redis"):
        raise ValueError("%s 不支持 SQL 查询，请在「数据」页打开%s浏览数据" % (
            "MongoDB" if ci.get("db_type") == "mongodb" else "Redis",
            "集合" if ci.get("db_type") == "mongodb" else "键"))
    limit = max(1, min(int(limit), 5000))
    s = (sql or "").strip()
    if not s:
        raise ValueError("SQL 不能为空")
    stmts = split_sql_statements(s)
    if not stmts:
        raise ValueError("SQL 不能为空")
    db_type = (ci.get("db_type") or "").lower()

    def _exec_one(conn, st):
        first = st.split(None, 1)[0].lower()
        sql_text = st
        # 防大表 SELECT 拖垮服务: 无 LIMIT 的 SELECT 自动追加(MySQL/PG/SQLite 支持;
        # MSSQL/Oracle 不支持 LIMIT 语法, 由下方 fetchmany 兜底截断)
        if first == "select" and db_type not in ("mssql", "oracle") \
                and not re.search(r"\blimit\b\s*[0-9?]", sql_text, re.I):
            sql_text = sql_text.rstrip().rstrip(";") + f" LIMIT {limit + 1}"
        result = conn.execute(text(sql_text))
        if result.returns_rows:
            cols = list(result.keys())
            # fetchmany 只物化 limit+1 行, 绝不把整表拉进内存
            rows = [dict(r) for r in result.mappings().fetchmany(limit + 1)]
            truncated = len(rows) > limit
            rows = rows[:limit]
            result.close()
            return {"sql": st, "columns": [{"name": c} for c in cols],
                    "rows": rows, "total": len(rows),
                    "truncated": truncated, "ok": True}
        affected = result.rowcount or 0
        result.close()
        return {"sql": st, "columns": [], "rows": [], "total": 0,
                "affected": affected, "ok": True}

    if not write:
        # 只读模式: 预校验全部语句都是只读才执行(一条违规则整批拒绝, 避免执行一半)
        for st in stmts:
            first = st.split(None, 1)[0].lower()
            if first in SQL_BLOCKED:
                raise ValueError("查询控制台仅支持只读查询, 已阻止语句: " + first.upper())
            if first not in SQL_READ_ONLY:
                raise ValueError("仅支持 SELECT / SHOW / EXPLAIN / DESC 开头的只读查询: " + st[:60])
            # SELECT INTO 绕过防护: MSSQL 的 SELECT...INTO 建表 / MySQL 的 INTO OUTFILE|DUMPFILE 写文件
            # 均可在只读模式下绕过高危操作; 仅放行 INTO @变量(MySQL 赋值)与 INTO DUAL(Oracle)
            if " INTO " in st.upper():
                rest = st.upper().split(" INTO ", 1)[1].strip()
                if not (rest.startswith("@") or rest.startswith("DUAL")):
                    raise ValueError("只读模式禁止 SELECT INTO(建表/写文件), 已阻止: " + st[:60])
        engine = get_engine(ci)
        results = []
        with engine.connect() as conn:
            for st in stmts:
                results.append(_exec_one(conn, st))
        return {"ok": True, "results": results, "readonly": True}

    # 写模式: 整批事务包裹, 任一条失败整体回滚(避免执行一半的脏状态)
    engine = get_engine(ci)
    results = []
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            for st in stmts:
                results.append(_exec_one(conn, st))
            tx.commit()
        except Exception:
            tx.rollback()
            raise
    return {"ok": True, "results": results, "readonly": False}


def explain_query(ci, sql):
    """执行计划: MySQL/PG 返回结构化行(前端树/表渲染), SQLite/MSSQL 返回文本行"""
    if (ci.get("db_type") or "").lower() in ("mongodb", "redis"):
        raise ValueError("Redis 无 SQL 执行计划" if ci.get("db_type") == "redis"
                         else "MongoDB 无 SQL 执行计划")
    db_type = (ci.get("db_type") or "mysql").lower()
    s = (sql or "").strip().rstrip(";").strip()
    if not s:
        raise ValueError("SQL 不能为空")
    engine = get_engine(ci)
    with engine.connect() as conn:
        if db_type == "mysql":
            result = conn.execute(text("EXPLAIN " + s))
            cols = [c for c in result.keys()]
            rows = [dict(r) for r in result.mappings()]
            return {"columns": [{"name": c} for c in cols], "rows": rows, "total": len(rows), "mode": "table"}
        if db_type == "postgresql":
            result = conn.execute(text("EXPLAIN (FORMAT JSON) " + s))
            plan = result.scalar()
            # 展平 JSON 树为行: 每层一个 node, 用缩进表达层级
            nodes = []
            def walk(p, depth):
                nodes.append({"depth": depth, "type": p.get("Node Type", ""),
                              "table": p.get("Relation Name", ""),
                              "rows": p.get("Plan Rows"), "cost": p.get("Total Cost"),
                              "detail": p.get("Filter") or p.get("Index Name") or ""})
                for ch in p.get("Plans", []):
                    walk(ch, depth + 1)
            if plan and isinstance(plan, list) and isinstance(plan[0], dict):
                walk(plan[0], 0)
            return {"columns": [{"name": "层级"}, {"name": "节点"}, {"name": "表"}, {"name": "行数"}, {"name": "成本"}],
                    "rows": [{"层级": "·" * (n["depth"] + 1) + " " + str(n["depth"]), "节点": n["type"],
                              "表": n["table"] or "", "行数": n["rows"], "成本": n["cost"]} for n in nodes],
                    "total": len(nodes), "mode": "table"}
        if db_type == "mssql":
            # MSSQL 限制: SHOWPLAN 开关必须是批次唯一语句(1067) -> 同连接分三次执行
            try:
                conn.execute(text("SET SHOWPLAN_ALL ON"))
                result = conn.execute(text(s))
                rows = [dict(r) for r in result.mappings().fetchmany(500)]
            finally:
                try:
                    conn.execute(text("SET SHOWPLAN_ALL OFF"))
                except Exception:
                    pass
            return {"columns": [{"name": c} for c in (list(rows[0].keys()) if rows else ["StmtText"])],
                    "rows": rows, "total": len(rows), "mode": "text"}
        if db_type == "oracle":
            # Oracle: EXPLAIN PLAN FOR 写入 PLAN_TABLE, 再读 DBMS_XPLAN 文本
            conn.execute(text("EXPLAIN PLAN FOR " + s))
            result = conn.execute(text("SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY(FORMAT=>'TYPICAL'))")).mappings()
            rows = [dict(r) for r in result.fetchmany(200)]
            txt = "\n".join(str(r.get(list(r.keys())[0]) or "") for r in rows)
            return {"columns": [{"name": "执行计划"}],
                    "rows": [{"执行计划": line} for line in txt.splitlines() if line.strip()],
                    "total": len(rows), "mode": "text"}
        # sqlite
        result = conn.execute(text("EXPLAIN QUERY PLAN " + s))
        rows = [dict(r) for r in result.mappings()]
        return {"columns": [{"name": c} for c in result.keys()], "rows": rows,
                "total": len(rows), "mode": "table"}

